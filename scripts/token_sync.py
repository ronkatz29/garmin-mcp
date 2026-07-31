#!/usr/bin/env python3
"""
token_sync — sync the cached Garmin auth token via a dedicated git branch.

The remote sync routine has no persistent storage between runs, and Garmin
rotates the refresh token on every use, so a token pushed once eventually
goes stale. `claude/garmin-token-sync` (a branch on this repo) is the
shared state that lets each run pick up where the last one left off:
`pull` fetches it into the local token store before login, `push` writes
the (possibly refreshed) token store back after.

Uses a plain git clone of this repo's own remote, so it rides the same
credentials the routine already has for this repo — no separate token or
secret needed. A `claude/`-prefixed branch is always push-accepted per
Claude Code's routine push rules, unlike arbitrary branches or third-party
APIs (e.g. the GitHub Gists API), which a routine's scoped GitHub access
can't reach.

No-ops silently if the clone fails (e.g. running fully offline locally),
so local/MCP usage is unaffected.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_URL = "https://github.com/ronkatz29/garmin-mcp.git"
BRANCH = "claude/garmin-token-sync"
FILENAME = "garmin_tokens.json"
TOKEN_FILE = Path(os.path.expanduser("~/.garminconnect/garmin_tokens.json"))


def _clone(dest: str) -> bool:
    result = subprocess.run(
        ["git", "clone", "--quiet", "--branch", BRANCH, "--single-branch",
         "--depth", "1", REPO_URL, dest],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"token_sync: clone failed: {result.stderr.strip()}", file=sys.stderr)
        return False
    return True


def pull() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        if not _clone(tmp):
            return
        src = Path(tmp) / FILENAME
        if not src.exists():
            return
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, TOKEN_FILE)
        print(f"token_sync: pulled token into {TOKEN_FILE}", file=sys.stderr)


def push() -> None:
    if not TOKEN_FILE.exists():
        return
    with tempfile.TemporaryDirectory() as tmp:
        if not _clone(tmp):
            return
        shutil.copy(TOKEN_FILE, Path(tmp) / FILENAME)
        subprocess.run(["git", "-C", tmp, "add", FILENAME], check=True)
        diff = subprocess.run(["git", "-C", tmp, "diff", "--cached", "--quiet"])
        if diff.returncode == 0:
            return  # nothing changed
        subprocess.run(
            ["git", "-C", tmp, "-c", "user.email=garmin-mcp@local",
             "-c", "user.name=garmin-mcp bot", "commit", "--quiet",
             "-m", "Update cached Garmin token"],
            check=True,
        )
        result = subprocess.run(
            ["git", "-C", tmp, "push", "--quiet", "origin", f"HEAD:{BRANCH}"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"token_sync: push failed: {result.stderr.strip()}", file=sys.stderr)
            return
        print("token_sync: pushed refreshed token", file=sys.stderr)


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("pull", "push"):
        sys.exit("Usage: python3 -m scripts.token_sync {pull|push}")
    {"pull": pull, "push": push}[sys.argv[1]]()


if __name__ == "__main__":
    main()
