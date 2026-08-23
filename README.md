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
   ├── server.py               MCP server (stdio) — used by local Claude Code sessions
   ├── scripts/fetch.py        plain CLI, no MCP — ad hoc data pulls
   └── scripts/sync_calendar.py  daily Garmin -> Google Calendar sync,
                                  run by .github/workflows/garmin-calendar-sync.yml
```

`scripts/fetch.py`:

```bash
python3 -m scripts.fetch activities [--limit N]
python3 -m scripts.fetch resting-hr [--date YYYY-MM-DD]
python3 -m scripts.fetch sleep [--date YYYY-MM-DD]
python3 -m scripts.fetch body-battery [--start YYYY-MM-DD] [--end YYYY-MM-DD]
```

## Garmin → Google Calendar sync

`scripts/sync_calendar.py` runs daily on a free GitHub Actions cron
(`.github/workflows/garmin-calendar-sync.yml`, `workflow_dispatch` also
available for manual runs). It's a plain deterministic script — no LLM
involved at runtime:

- Pulls Garmin activities from the last 2 days.
- Matches each one to an existing calendar event by time overlap (±60 min
  on the same day); creates a new event at the activity's real start/end
  time if nothing matches.
- Applies the standing convention: `colorId "5"` (yellow), title
  `{activityName} ({distance}km)`, description
  `Auto-added from Garmin: {distance}km, {duration} min, pace {pace}, {calories} cal`.

**Required GitHub repo secrets** (Settings → Secrets and variables → Actions):

- `GARMIN_EMAIL`, `GARMIN_PASSWORD` — same as local auth, no token needed.
- `GOOGLE_SERVICE_ACCOUNT_JSON` — full JSON key of a Google Cloud service
  account with the Calendar API enabled. Share the target calendar with
  the service account's email address (Settings and sharing → Add people
  → grant "Make changes to events").
- `GOOGLE_CALENDAR_ID` — the calendar to write to.

**Local test run:**

```bash
GARMIN_EMAIL=you@example.com \
GARMIN_PASSWORD=yourpassword \
GOOGLE_SERVICE_ACCOUNT_JSON="$(cat service-account.json)" \
GOOGLE_CALENDAR_ID=you@example.com \
.venv/bin/python3 scripts/sync_calendar.py
```

This replaced an earlier claude.ai scheduled routine that ran the same
logic as an inline, un-versioned prompt script. That approach depended on
a Garmin session token surviving between runs (via a `GARMIN_TOKENS_B64`
env var, later a dedicated git branch pushing/pulling the cached token
file) and kept breaking: Garmin's refresh token is single-use, so any
failed push left the next run stuck on an already-dead token. Since this
account has no MFA, `garmin_auth.py` just logs in fresh with plain
credentials every run instead — nothing cached, nothing to expire or
desync between runs or consumers.

If Garmin ever adds MFA to this account, plain credential login will stop
working unattended (no TTY to prompt for a code), and some form of token
caching + refresh will need to come back for this workflow.

## Credential rotation

If the Garmin password ever changes, update the `GARMIN_PASSWORD` GitHub
secret — no other file or token needs to change, since nothing is cached.

## Notes

- This library is unofficial and reverse-engineered from Garmin's mobile app; it can break when Garmin changes internal endpoints.
- Credentials live in `~/.claude.json`'s local `env` block, the remote routine's own env var settings, or a local, gitignored `.env` — never committed to `main`.
