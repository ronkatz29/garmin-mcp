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
                              └── scripts/gist_token.py   syncs the token
                                  with a secret gist so the routine stays
                                  authenticated across runs (see below)
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
and the previous approach (a static `GARMIN_TOKENS_B64` env var, hand
re-pasted whenever it expired) couldn't survive that rotation.

Instead, `scripts/fetch.py` syncs the token through a secret GitHub gist
(`scripts/gist_token.py`) on every invocation:

1. **Pull**: fetch the current token from the gist before login.
2. Login refreshes it if needed (rotating the refresh token in the process).
3. **Push**: write the (possibly refreshed) token back to the gist.

This makes the auth loop fully remote — the routine keeps itself
authenticated indefinitely without any local machine or manual re-paste.
It's gated on `GARMIN_GIST_TOKEN` (a GitHub PAT scoped to `gist` only)
being set; without it, `pull`/`push` no-op, so local/MCP usage is
unaffected.

**One-time setup for the routine:**

1. Create a classic GitHub PAT with only the `gist` scope (github.com →
   Settings → Developer settings → Personal access tokens → Tokens
   (classic)). No expiration, or a long one — it doesn't need frequent
   rotation like the Garmin token does.
2. Add it as `GARMIN_GIST_TOKEN` in the routine's environment variables.
3. The routine's Step 0 just needs to run `python3 -m scripts.fetch
   activities --limit N` (or another subcommand) — the gist sync happens
   automatically inside `fetch.py`. No `GARMIN_TOKENS_B64` decode step
   needed anymore.

If the routine ever does hit a 401 (e.g. Garmin invalidated the refresh
token entirely, or the gist got out of sync), refresh locally and reseed
the gist:

```bash
GARMIN_EMAIL=... GARMIN_PASSWORD=... .venv/bin/python3 auth_setup.py
gh gist edit d75c5db79f71392c36b8033a298ef27c -a ~/.garminconnect/garmin_tokens.json
```

## Notes

- This library is unofficial and reverse-engineered from Garmin's mobile app; it can break when Garmin changes internal endpoints.
- Credentials should only live in `~/.claude.json`'s local `env` block, the remote routine's own env var settings, or a local, gitignored `.env` — never committed to this repo. The Garmin token itself lives in a secret gist (`d75c5db79f71392c36b8033a298ef27c`), not in this repo.
