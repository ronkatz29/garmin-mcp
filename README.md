# garmin-mcp

> Garmin Connect data (activities, sleep, heart rate, body battery) as MCP tools.

An MCP server built on the unofficial [`garminconnect`](https://pypi.org/project/garminconnect/) library, which authenticates via the same SSO flow as the Garmin Connect mobile app. There's no official public API for personal Garmin data, so this reverse-engineered client is the standard approach.

## Setup

### 1. Install dependencies

```bash
cd /Users/ronkatz/tools/garmin-mcp
uv pip install -e .
```

### 2. One-time login (handles MFA if enabled)

```bash
GARMIN_EMAIL=you@example.com GARMIN_PASSWORD=yourpassword python3 auth_setup.py
```

This caches a token at `~/.garminconnect`. Re-run it any time the token expires.

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
garmin_auth.py  (TOKEN_STORE, get_client(), login_interactive())
   ├── server.py           MCP server (stdio) — used by local Claude Code sessions
   ├── auth_setup.py       one-time interactive login (handles MFA)
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

## Refreshing the token used by the remote routine

The remote routine reads Garmin auth from its own `GARMIN_TOKENS_B64` env
var (base64 of `~/.garminconnect/garmin_tokens.json`), decoded into its
sandbox at the start of each run. It drifts out of sync whenever the local
token is refreshed and the routine's copy isn't updated — this is what
caused a prior 401 failure.

When the routine fails with a 401:

```bash
./scripts/print_token_b64.sh
```

This verifies the local token still logs in (refresh first via
`auth_setup.py` if not), then prints the base64 value to paste into the
routine's `GARMIN_TOKENS_B64` env var in claude.ai routine settings.
There's no known API to update a routine's env vars remotely, so this
paste step stays manual.

## Notes

- This library is unofficial and reverse-engineered from Garmin's mobile app; it can break when Garmin changes internal endpoints.
- Credentials should only live in `~/.claude.json`'s local `env` block, the remote routine's own env var settings, or a local, gitignored `.env` — never committed to this repo.
