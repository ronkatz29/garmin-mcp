#!/usr/bin/env bash
# Verifies the locally cached Garmin token still logs in, then prints its
# base64 encoding, ready to paste into the remote sync routine's
# GARMIN_TOKENS_B64 env var (claude.ai routine settings -> this routine ->
# environment variables). There is no known API to update a routine's env
# vars, so this last paste step stays manual.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOKEN_FILE="$HOME/.garminconnect/garmin_tokens.json"

"$REPO_DIR/.venv/bin/python3" -c "
from garmin_auth import get_client
get_client()
print('Local token OK', file=__import__('sys').stderr)
" || {
    echo "Local Garmin token is missing or expired." >&2
    echo "Run: GARMIN_EMAIL=... GARMIN_PASSWORD=... $REPO_DIR/.venv/bin/python3 $REPO_DIR/auth_setup.py" >&2
    exit 1
}

base64 -i "$TOKEN_FILE" | tr -d '\n'
echo
