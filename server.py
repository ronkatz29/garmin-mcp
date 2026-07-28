#!/usr/bin/env python3
"""
garmin-mcp — Garmin Connect data as MCP tools
==============================================
Exposes activities, sleep, resting heart rate, and body battery from
Garmin Connect (via the unofficial `garminconnect` library).

Auth: run `auth_setup.py` once (interactively, handles MFA) to create a
cached token at ~/.garminconnect. This server reuses that cache — it has
no TTY, so it cannot prompt for MFA itself. If the cache is missing or
expired, tools return an error telling you to re-run auth_setup.py.

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


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
