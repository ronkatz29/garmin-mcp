# garmin-mcp

> Garmin Connect data (activities, sleep, heart rate, body battery) as MCP tools.

An MCP server built on the unofficial [`garminconnect`](https://pypi.org/project/garminconnect/) library, which authenticates via the same SSO flow as the Garmin Connect mobile app. There's no official public API for personal Garmin data, so this reverse-engineered client is the standard approach.

## Setup

### 1. Install dependencies

```bash
cd /Users/ronkatz/tools/garmin-mcp
uv pip install -e .
```

### 2. Set credentials

This account has no MFA, so there's no token setup step — every consumer
just logs in with plain credentials on first use:

```bash
export GARMIN_EMAIL=you@example.com
export GARMIN_PASSWORD=yourpassword
```

### 3. Register with Claude

Add to `~/.claude.json` under `mcpServers` (same pattern as `google-docs`):

```json
"garmin": {
  "command": "uvx",
  "args": ["--from", "/Users/ronkatz/tools/garmin-mcp", "garmin-mcp"],
  "env": {
    "GARMIN_EMAIL": "you@example.com",
    "GARMIN_PASSWORD": "yourpassword"
  }
}
```

Restart Claude Code / Claude Desktop after adding this.

## Tools

- `get_activities(limit=10)` — recent workouts/activities
- `get_resting_heart_rate(cdate=None)` — heart rate data for a date (defaults to today)
- `get_sleep(cdate=None)` — sleep data for a date (defaults to today)
- `get_body_battery(startdate=None, enddate=None)` — body battery levels for a date range (defaults to today)

## Architecture

Auth and login logic (`garmin_auth.py`) is shared by every consumer in this repo:

```
garmin_auth.py  (get_client())
   ├── server.py           MCP server (stdio) — used by local Claude Code sessions
   └── scripts/fetch.py    plain CLI, no MCP — same data, used by the
                            remote Garmin → Calendar sync routine (claude.ai)
```

`scripts/fetch.py` exists so the remote routine can clone this repo and call
real, reviewed code instead of carrying its own copy-pasted fetch logic:

```bash
python3 -m scripts.fetch activities [--limit N]
python3 -m scripts.fetch resting-hr [--date YYYY-MM-DD]
python3 -m scripts.fetch sleep [--date YYYY-MM-DD]
python3 -m scripts.fetch body-battery [--start YYYY-MM-DD] [--end YYYY-MM-DD]
```

## How the remote routine stays authenticated

It just logs in fresh every run with `GARMIN_EMAIL`/`GARMIN_PASSWORD` set as
env vars on the routine (claude.ai Settings → Scheduled Tasks). No cached
token, no shared state between consumers, nothing to expire or resync.

Two earlier approaches were tried and dropped because they depended on a
persisted token surviving between runs, which this account's no-MFA login
doesn't need:

- A static `GARMIN_TOKENS_B64` env var, hand re-pasted whenever it expired
  — no way to update it without a human in the loop.
- A dedicated git branch (`claude/garmin-token-sync`) that pulled/pushed a
  cached token around every consumer — fragile in practice: Garmin's
  refresh token is single-use, so any two consumers refreshing close
  together (or the routine's push silently failing in its sandbox) would
  invalidate each other's copy, reliably producing 401s the next day with
  no obvious trigger.

If Garmin ever does add MFA to this account, plain credential login will
stop working for the routine (no TTY to prompt for a code), and some form
of token caching will need to come back.

## Notes

- This library is unofficial and reverse-engineered from Garmin's mobile app; it can break when Garmin changes internal endpoints.
- Credentials live in `~/.claude.json`'s local `env` block, the remote routine's own env var settings, or a local, gitignored `.env` — never committed to `main`.
