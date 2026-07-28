#!/usr/bin/env python3
"""
garmin-mcp auth setup — one-time interactive Garmin Connect login.

Run this manually (with a real terminal, not from inside the MCP server)
whenever the cached token is missing or expired:

    GARMIN_EMAIL=you@example.com GARMIN_PASSWORD=yourpassword python3 auth_setup.py

If your account has MFA enabled you'll be prompted for a code here.
Tokens are cached at ~/.garminconnect and reused automatically by server.py.
"""

from __future__ import annotations

import os
import sys

from garmin_auth import TOKEN_STORE, login_interactive


def main() -> None:
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")

    if not email or not password:
        print(
            "Set GARMIN_EMAIL and GARMIN_PASSWORD environment variables first.",
            file=sys.stderr,
        )
        sys.exit(1)

    login_interactive(email, password)
    print(f"Login successful. Tokens cached at {TOKEN_STORE}")


if __name__ == "__main__":
    main()
