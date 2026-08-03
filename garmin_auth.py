#!/usr/bin/env python3
"""
garmin_auth — shared Garmin Connect login logic.

Used by server.py (MCP server), auth_setup.py (interactive one-time login),
and scripts/fetch.py (plain CLI fetch, used by the remote sync routine).

Auth: a cached token at TOKEN_STORE (created via auth_setup.py) is enough
for normal use. GARMIN_EMAIL / GARMIN_PASSWORD are only used as a fallback
if the cache is missing or expired, and login() has no TTY here, so it
cannot prompt for MFA — use auth_setup.py interactively for that.

get_client() also syncs the token cache with the `claude/garmin-token-sync`
git branch (pull before login, push after) so every consumer — local MCP
server, this process, and the remote routine — shares one source of truth.
Garmin's refresh token is single-use: without this, a login from one
consumer silently invalidates the copy another consumer still has cached,
surfacing as a hard 401 later with no obvious cause.
"""

from __future__ import annotations

import os

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
)

from scripts import token_sync

TOKEN_STORE = os.path.expanduser("~/.garminconnect")

_client: Garmin | None = None


def get_client() -> Garmin:
    """Cached, non-interactive Garmin client backed by the token cache."""
    global _client
    if _client is None:
        token_sync.pull()
        email = os.environ.get("GARMIN_EMAIL")
        password = os.environ.get("GARMIN_PASSWORD")
        client = Garmin(email, password)
        try:
            client.login(TOKEN_STORE)
        except (GarminConnectAuthenticationError, GarminConnectConnectionError) as exc:
            raise RuntimeError(
                f"Garmin login failed ({exc}). Run auth_setup.py interactively "
                "(with GARMIN_EMAIL/GARMIN_PASSWORD set) to refresh the cached "
                "token or complete MFA."
            ) from exc
        finally:
            token_sync.push()
        _client = client
    return _client


def login_interactive(email: str, password: str) -> Garmin:
    """One-time interactive login (prompts for MFA if needed). Caches to TOKEN_STORE."""
    token_sync.pull()
    client = Garmin(email, password, prompt_mfa=lambda: input("Enter MFA code: "))
    try:
        client.login(TOKEN_STORE)
    finally:
        token_sync.push()
    return client
