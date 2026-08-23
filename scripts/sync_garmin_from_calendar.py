#!/usr/bin/env python3
"""
sync_garmin_from_calendar — log CrossFit W.O.D / Weightlifting calendar
events into Garmin Connect as manual strength_training activities.

This is the reverse direction of scripts/sync_calendar.py (Garmin ->
Calendar). No LLM involved: deterministic title matching against calendar
events, deterministic duplicate detection against existing Garmin
activities. Designed to run unattended on a daily GitHub Actions cron
(see .github/workflows/garmin-from-calendar-sync.yml).

Auth:
    Garmin:  GARMIN_EMAIL / GARMIN_PASSWORD (see garmin_auth.py)
    Google:  GOOGLE_SERVICE_ACCOUNT_JSON (full service-account key JSON,
             as a string) + GOOGLE_CALENDAR_ID (the calendar to read from,
             which must be shared with the service account's email).

Convention: only events whose title (stripped, case-insensitive) is
exactly "w.o.d" or "weightlifting" are logged, matching Ron's manual
logging convention (title logged as-is, type_key strength_training).
See [[log-garmin-workout]] skill / [[feedback_garmin_calendar_sync]] memory.
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

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
LOOKBACK_DAYS = int(os.environ.get("SYNC_LOOKBACK_DAYS", "2"))
LOCAL_TZ = ZoneInfo("Asia/Jerusalem")

WORKOUT_TITLES = {"w.o.d", "weightlifting"}
GARMIN_TYPE_KEY = "strength_training"
DEFAULT_DURATION_MIN = 60


def _google_calendar_service():
    creds_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    return build("calendar", "v3", credentials=creds)


def _workout_events(service, calendar_id: str) -> list[dict]:
    now = datetime.now(timezone.utc)
    time_min = now - timedelta(days=LOOKBACK_DAYS)

    resp = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min.isoformat(),
            timeMax=now.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = []
    for event in resp.get("items", []):
        title = (event.get("summary") or "").strip().lower()
        if title not in WORKOUT_TITLES:
            continue
        start_raw = event.get("start", {}).get("dateTime")
        end_raw = event.get("end", {}).get("dateTime")
        if not start_raw:
            continue  # skip all-day events
        start = datetime.fromisoformat(start_raw)
        if start > now:
            continue  # event hasn't happened yet
        end = datetime.fromisoformat(end_raw) if end_raw else start + timedelta(
            minutes=DEFAULT_DURATION_MIN
        )
        duration_min = max(1, round((end - start).total_seconds() / 60))
        events.append(
            {
                "title": event.get("summary").strip(),
                "start": start.astimezone(LOCAL_TZ),
                "duration_min": duration_min,
            }
        )
    return events


def _already_logged(existing_activities: list[dict], title: str, start: datetime) -> bool:
    for activity in existing_activities:
        name = (activity.get("activityName") or "").strip().lower()
        if name != title.lower():
            continue
        start_local_str = activity.get("startTimeLocal")
        if not start_local_str:
            continue
        activity_start = datetime.strptime(
            start_local_str, "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=LOCAL_TZ)
        if activity_start.date() == start.date():
            return True
    return False


def main() -> None:
    calendar_id = os.environ["GOOGLE_CALENDAR_ID"]
    service = _google_calendar_service()

    events = _workout_events(service, calendar_id)
    print(f"Found {len(events)} workout event(s) in the last {LOOKBACK_DAYS} days.")
    if not events:
        return

    client = get_client()
    existing_activities = client.get_activities(0, 50)

    for event in events:
        if _already_logged(existing_activities, event["title"], event["start"]):
            print(f"Skipped (already in Garmin): {event['title']} @ {event['start']}")
            continue
        client.create_manual_activity(
            start_datetime=event["start"].strftime("%Y-%m-%dT%H:%M:%S.000"),
            time_zone=str(LOCAL_TZ),
            type_key=GARMIN_TYPE_KEY,
            distance_km=0,
            duration_min=event["duration_min"],
            activity_name=event["title"],
        )
        print(f"Created in Garmin: {event['title']} @ {event['start']}")


if __name__ == "__main__":
    main()
