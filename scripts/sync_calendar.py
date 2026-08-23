#!/usr/bin/env python3
"""
sync_calendar — sync recent Garmin activities into Google Calendar.

No LLM involved: deterministic time-overlap matching against existing
calendar events, deterministic formatting. Designed to run unattended on
a daily GitHub Actions cron (see .github/workflows/garmin-calendar-sync.yml).

Auth:
    Garmin:  GARMIN_EMAIL / GARMIN_PASSWORD (see garmin_auth.py)
    Google:  GOOGLE_SERVICE_ACCOUNT_JSON (full service-account key JSON,
             as a string) + GOOGLE_CALENDAR_ID (the calendar to write to,
             which must be shared with the service account's email).

Convention (colorId/title/description) is fixed per Ron's standing
preference — see [[feedback_garmin_calendar_sync]] memory.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from garmin_auth import get_client  # noqa: E402

from google.oauth2.service_account import Credentials  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402

SCOPES = ["https://www.googleapis.com/auth/calendar"]
LOOKBACK_DAYS = 2
MATCH_WINDOW_MIN = 60
LOCAL_TZ = ZoneInfo("Asia/Jerusalem")
YELLOW_COLOR_ID = "5"

SWIMMING_TYPE_KEYS = {"lap_swimming", "open_water_swimming"}


def _google_calendar_service():
    creds_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    return build("calendar", "v3", credentials=creds)


def _format_pace(distance_km: float, duration_min: float, is_swim: bool) -> str:
    if distance_km <= 0 or duration_min <= 0:
        return "n/a"
    if is_swim:
        units = distance_km * 10  # 100m units
        pace_min_per_unit = duration_min / units if units else 0
        suffix = "/100m"
    else:
        pace_min_per_unit = duration_min / distance_km
        suffix = "/km"
    minutes = int(pace_min_per_unit)
    seconds = round((pace_min_per_unit - minutes) * 60)
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d}{suffix}"


def _activity_fields(activity: dict) -> dict:
    type_key = (activity.get("activityType") or {}).get("typeKey", "")
    is_swim = type_key in SWIMMING_TYPE_KEYS

    distance_km = (activity.get("distance") or 0) / 1000
    duration_sec = activity.get("duration") or 0
    duration_min = duration_sec / 60
    calories = activity.get("calories") or 0

    start_local_str = activity["startTimeLocal"]  # "YYYY-MM-DD HH:MM:SS"
    start_local = datetime.strptime(start_local_str, "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=LOCAL_TZ
    )
    end_local = start_local + timedelta(seconds=duration_sec)

    return {
        "name": activity.get("activityName", "Workout"),
        "distance_km": distance_km,
        "duration_min": duration_min,
        "calories": calories,
        "pace": _format_pace(distance_km, duration_min, is_swim),
        "start": start_local,
        "end": end_local,
    }


def _title(fields: dict) -> str:
    return f"{fields['name']} ({fields['distance_km']:.2f}km)"


def _description(fields: dict) -> str:
    return (
        f"Auto-added from Garmin: {fields['distance_km']:.2f}km, "
        f"{fields['duration_min']:.0f} min, pace {fields['pace']}, "
        f"{fields['calories']:.0f} cal"
    )


def _find_matching_event(service, calendar_id: str, fields: dict) -> dict | None:
    day_start = fields["start"].replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    resp = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=day_start.isoformat(),
            timeMax=day_end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    window = timedelta(minutes=MATCH_WINDOW_MIN)
    for event in resp.get("items", []):
        start_raw = event.get("start", {}).get("dateTime")
        if not start_raw:
            continue  # skip all-day events, nothing to time-match against
        event_start = datetime.fromisoformat(start_raw)
        if abs(event_start - fields["start"]) <= window:
            return event
    return None


def _sync_activity(service, calendar_id: str, activity: dict) -> None:
    fields = _activity_fields(activity)
    title = _title(fields)
    description = _description(fields)

    existing = _find_matching_event(service, calendar_id, fields)
    if existing:
        service.events().patch(
            calendarId=calendar_id,
            eventId=existing["id"],
            body={
                "summary": title,
                "description": description,
                "colorId": YELLOW_COLOR_ID,
            },
        ).execute()
        print(f"Matched + updated: {title}")
    else:
        service.events().insert(
            calendarId=calendar_id,
            body={
                "summary": title,
                "description": description,
                "colorId": YELLOW_COLOR_ID,
                "start": {
                    "dateTime": fields["start"].isoformat(),
                    "timeZone": str(LOCAL_TZ),
                },
                "end": {
                    "dateTime": fields["end"].isoformat(),
                    "timeZone": str(LOCAL_TZ),
                },
            },
        ).execute()
        print(f"Created: {title}")


def main() -> None:
    calendar_id = os.environ["GOOGLE_CALENDAR_ID"]
    service = _google_calendar_service()

    activities = get_client().get_activities(0, 50)
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

    recent = []
    for activity in activities:
        start_gmt = datetime.strptime(
            activity["startTimeGMT"], "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=timezone.utc)
        if start_gmt >= cutoff:
            recent.append(activity)

    print(f"Found {len(recent)} activities in the last {LOOKBACK_DAYS} days.")
    for activity in recent:
        _sync_activity(service, calendar_id, activity)


if __name__ == "__main__":
    main()
