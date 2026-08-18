#!/usr/bin/env python3
"""
garmin-mcp — Garmin Connect data as MCP tools
==============================================
Exposes activities, sleep, resting heart rate, and body battery from
Garmin Connect (via the unofficial `garminconnect` library).

Auth: set GARMIN_EMAIL / GARMIN_PASSWORD env vars (see garmin_auth.py).

Transport: stdio (Claude Code / Claude Desktop MCP config)
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date

from fastmcp import FastMCP

from garmin_auth import get_client

logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

mcp = FastMCP(
    name="garmin-mcp",
    instructions="""
Garmin Connect data tools. All date args are ISO format (YYYY-MM-DD);
omit them to default to today.

  get_activities            Recent workouts/activities
  get_resting_heart_rate    Resting + all-day heart rate data for a date
  get_sleep                 Sleep data for a date
  get_body_battery          Body battery levels for a date
  create_activity           Manually log a private activity (no GPS/sensor data)
""",
)

def _today() -> str:
    return date.today().isoformat()


@mcp.tool
def get_activities(limit: int = 10) -> str:
    """
    Get recent Garmin activities/workouts.

    Args:
        limit: Max number of activities to return (default 10)
    """
    result = get_client().get_activities(0, limit)
    return json.dumps(result, indent=2)


@mcp.tool
def get_resting_heart_rate(cdate: str | None = None) -> str:
    """
    Get heart rate data (including resting HR) for a date.

    Args:
        cdate: Date in YYYY-MM-DD format. Defaults to today.
    """
    result = get_client().get_heart_rates(cdate or _today())
    return json.dumps(result, indent=2)


@mcp.tool
def get_sleep(cdate: str | None = None) -> str:
    """
    Get sleep data for a date.

    Args:
        cdate: Date in YYYY-MM-DD format. Defaults to today.
    """
    result = get_client().get_sleep_data(cdate or _today())
    return json.dumps(result, indent=2)


@mcp.tool
def get_body_battery(startdate: str | None = None, enddate: str | None = None) -> str:
    """
    Get body battery levels for a date range.

    Args:
        startdate: Start date in YYYY-MM-DD format. Defaults to today.
        enddate:   End date in YYYY-MM-DD format. Defaults to startdate.
    """
    result = get_client().get_body_battery(startdate or _today(), enddate)
    return json.dumps(result, indent=2)


@mcp.tool
def create_activity(
    activity_name: str,
    type_key: str,
    start_datetime: str,
    distance_km: float,
    duration_min: int,
    time_zone: str = "Asia/Jerusalem",
) -> str:
    """
    Manually log a private activity on Garmin Connect (no GPS/sensor data).

    Args:
        activity_name: Title of the activity, e.g. "Evening Run".
        type_key: Garmin activity type key, e.g. "running", "cycling", "hiking",
            "open_water_swimming", "strength_training". See the "activity_type_*"
            keys at https://connect.garmin.com/modern/main/js/properties/activity_types/activity_types.properties
            (use the key without the "activity_type_" prefix).
        start_datetime: Local start time, ISO format "YYYY-MM-DDTHH:MM:SS.000".
        distance_km: Distance in kilometers (use 0 for non-distance activities).
        duration_min: Duration in minutes.
        time_zone: IANA timezone of the activity. Defaults to Asia/Jerusalem.
    """
    result = get_client().create_manual_activity(
        start_datetime=start_datetime,
        time_zone=time_zone,
        type_key=type_key,
        distance_km=distance_km,
        duration_min=duration_min,
        activity_name=activity_name,
    )
    return json.dumps(result, indent=2)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
