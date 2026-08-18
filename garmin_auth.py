#!/usr/bin/env python3
"""
garmin_auth — shared Garmin Connect login logic.

Used by server.py (MCP server) and scripts/fetch.py (plain CLI fetch, used
by the remote sync routine).

Auth: plain GARMIN_EMAIL / GARMIN_PASSWORD env vars, logged in fresh on
first use per process. This account has no MFA, so there's no cached
token, no shared token store, and no token-refresh race between
consumers (local CLI, MCP server, remote routine) to worry about.
"""

from __future__ import annotations

import os

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
)

_client: Garmin | None = None


def get_client() -> Garmin:
    """Cached Garmin client, logged in with GARMIN_EMAIL/GARMIN_PASSWORD."""
    global _client
    if _client is None:
        email = os.environ.get("GARMIN_EMAIL")
        password = os.environ.get("GARMIN_PASSWORD")
        if not email or not password:
            raise RuntimeError(
                "Set GARMIN_EMAIL and GARMIN_PASSWORD environment variables."
            )
        client = Garmin(email, password)
        try:
            client.login()
        except (GarminConnectAuthenticationError, GarminConnectConnectionError) as exc:
            raise RuntimeError(f"Garmin login failed ({exc}).") from exc
        _client = client
    return _client
