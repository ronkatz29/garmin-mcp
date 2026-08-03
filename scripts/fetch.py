#!/usr/bin/env python3
"""
garmin-fetch — plain CLI for Garmin Connect data, no MCP required.

Same auth (garmin_auth.py) and garminconnect calls as server.py's MCP
tools, exposed as subcommands so non-MCP consumers (e.g. the remote
Garmin -> Calendar sync routine) can call the same reviewed code instead
of re-implementing login + fetch logic inline.

Usage:
    python3 -m scripts.fetch activities [--limit N]
    python3 -m scripts.fetch resting-hr [--date YYYY-MM-DD]
    python3 -m scripts.fetch sleep [--date YYYY-MM-DD]
    python3 -m scripts.fetch body-battery [--start YYYY-MM-DD] [--end YYYY-MM-DD]

Prints JSON to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from garmin_auth import get_client  # noqa: E402


def _today() -> str:
    return date.today().isoformat()


def cmd_activities(args: argparse.Namespace) -> object:
    return get_client().get_activities(0, args.limit)


def cmd_resting_hr(args: argparse.Namespace) -> object:
    return get_client().get_heart_rates(args.date or _today())


def cmd_sleep(args: argparse.Namespace) -> object:
    return get_client().get_sleep_data(args.date or _today())


def cmd_body_battery(args: argparse.Namespace) -> object:
    return get_client().get_body_battery(args.start or _today(), args.end)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Garmin Connect data as JSON.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("activities", help="Recent workouts/activities")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_activities)

    p = sub.add_parser("resting-hr", help="Resting + all-day heart rate data for a date")
    p.add_argument("--date", dest="date", default=None)
    p.set_defaults(func=cmd_resting_hr)

    p = sub.add_parser("sleep", help="Sleep data for a date")
    p.add_argument("--date", dest="date", default=None)
    p.set_defaults(func=cmd_sleep)

    p = sub.add_parser("body-battery", help="Body battery levels for a date range")
    p.add_argument("--start", dest="start", default=None)
    p.add_argument("--end", dest="end", default=None)
    p.set_defaults(func=cmd_body_battery)

    args = parser.parse_args()
    result = args.func(args)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
