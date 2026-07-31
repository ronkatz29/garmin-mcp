#!/usr/bin/env python3
"""
gist_token — sync the cached Garmin auth token with a secret GitHub gist.

The remote sync routine has no persistent storage between runs, and Garmin
rotates the refresh token on every use, so a token pushed once eventually
goes stale. The gist is the shared state that lets each run pick up where
the last one left off: `pull` fetches it into the local token store before
login, `push` writes the (possibly refreshed) token store back after.

Requires GARMIN_GIST_TOKEN (a GitHub PAT with the `gist` scope) in the
environment. No-ops silently if it's unset, so local/MCP usage (which
doesn't need the gist) is unaffected.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

GIST_ID = "d75c5db79f71392c36b8033a298ef27c"
GIST_FILENAME = "garmin_tokens.json"
TOKEN_FILE = Path(os.path.expanduser("~/.garminconnect/garmin_tokens.json"))


def _request(method: str, token: str, data: bytes | None = None) -> dict:
    req = urllib.request.Request(
        f"https://api.github.com/gists/{GIST_ID}",
        data=data,
        method=method,
        headers={
            "Authorization": f"token {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def pull() -> None:
    token = os.environ.get("GARMIN_GIST_TOKEN")
    if not token:
        return
    gist = _request("GET", token)
    content = gist["files"][GIST_FILENAME]["content"]
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(content)
    print(f"gist_token: pulled token into {TOKEN_FILE}", file=sys.stderr)


def push() -> None:
    token = os.environ.get("GARMIN_GIST_TOKEN")
    if not token or not TOKEN_FILE.exists():
        return
    content = TOKEN_FILE.read_text()
    body = json.dumps({"files": {GIST_FILENAME: {"content": content}}}).encode()
    _request("PATCH", token, data=body)
    print("gist_token: pushed refreshed token to gist", file=sys.stderr)


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("pull", "push"):
        sys.exit("Usage: python3 -m scripts.gist_token {pull|push}")
    {"pull": pull, "push": push}[sys.argv[1]]()


if __name__ == "__main__":
    main()
