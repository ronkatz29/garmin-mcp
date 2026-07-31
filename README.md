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
                              └── scripts/token_sync.py   syncs the token
                                  via a dedicated git branch so the routine
                                  stays authenticated across runs (see below)
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

Garmin's access token lasts ~23h, and `garminconnect` rotates the refresh
token on every use — so a token pushed to the routine once eventually goes
stale no matter what. The routine has no persistent storage between runs,
and two earlier approaches didn't survive that rotation:

- A static `GARMIN_TOKENS_B64` env var, hand re-pasted whenever it expired
  — no way to update it without a human in the loop.
- A secret GitHub gist, synced via the Gists API — routines are restricted
  to their attached repositories, so `api.github.com/gists/...` calls get
  a 403 regardless of which token signs the request.

What actually works: a dedicated branch, `claude/garmin-token-sync`, on
*this* repo. `claude/`-prefixed branches are always push-accepted for a
routine, and the repo is already attached, so `scripts/token_sync.py`
rides the same git credentials the routine already has — no separate
token or secret needed. `scripts/fetch.py` calls it on every invocation:

1. **Pull**: clone that branch, copy `garmin_tokens.json` into the local
   token store, before login.
2. Login refreshes it if needed (rotating the refresh token in the
   process).
3. **Push**: commit and push the (possibly refreshed) token store back to
   the branch.

This makes the auth loop fully remote — the routine keeps itself
authenticated indefinitely with no local machine involved and no manual
re-paste, ever.

**Nothing to configure on the routine for this** — it reuses the repo
access the routine already has. The routine's Step 0 just needs to run
`python3 -m scripts.fetch activities --limit N` (or another subcommand);
the sync happens automatically inside `fetch.py`.

If the routine ever does hit a 401 (e.g. Garmin invalidated the refresh
token entirely), refresh locally and push:

```bash
GARMIN_EMAIL=... GARMIN_PASSWORD=... .venv/bin/python3 auth_setup.py
.venv/bin/python3 -m scripts.token_sync push
```

## Notes

- This library is unofficial and reverse-engineered from Garmin's mobile app; it can break when Garmin changes internal endpoints.
- Credentials should only live in `~/.claude.json`'s local `env` block, the remote routine's own env var settings, or a local, gitignored `.env` — never committed to `main`. The Garmin token itself lives only on the `claude/garmin-token-sync` branch, not `main`.
