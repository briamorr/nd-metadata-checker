# nd-metadata-checker

Watches Cisco Intersight for new **Nexus Dashboard air-gap metadata** downloads and
notifies Webex subscribers when something changes. Runs entirely on GitHub Actions —
no server, no public endpoint, no stored customer data.

## Why

Intersight emails customers about other software updates, but has no email
notification for Nexus Dashboard metadata packages. This fills that gap.

## How it works

```
GitHub Actions cron (nightly)
  └─ checker.py      → Intersight /api/v1/search/SearchItems (signed HTTP request)
  └─ diff vs state/nd_metadata_state.json
       ├─ no change → exit silently
       └─ changed   → render.py builds an Adaptive Card
                    → notify_webex.py posts to every Webex space the bot is in
                    → state committed back to the repo
```

### Authentication

Intersight uses HTTP Signature auth. `checker.py` detects whether the secret key is
RSA (`rsa-sha256`) or ECDSA (`hs2019` with `ECDSA_MODE_FIPS_186_3`) and configures the
SDK accordingly. In CI the PEM comes from a secret and is written to a mode-`0600`
temp file that is deleted in a `finally` block.

### Change detection

Results are keyed by `Name` and compared on `ReleaseDate`, `Version`, and
`Description`. `diff_downloads()` returns added / removed / updated entries. The
previous run's results live in `state/nd_metadata_state.json`, committed to the repo —
that's the only persistence layer.

State is written **after** a successful notification, so a Webex outage doesn't
silently swallow an alert; the next run re-detects the change and retries.
`state/last_run.txt` is touched on every run so the repository never goes 60 days
idle, which would cause GitHub to disable the schedule.

### Recipients

There is no subscriber database. At send time the bot asks Webex which spaces it
belongs to (`GET /v1/rooms`) and posts to each one. Customers subscribe by DMing the
bot once, or by adding it to a space. Webex owns the roster; this repo stores no
names, emails, or IDs.

Opt out by sending the bot `stop`, `unsubscribe`, `quiet`, or `mute` (in a group
space, @mention it). Opt back in with `start`, `subscribe`, or `resume`. Only the most
recent inbound message is examined.

## Files

| File | Purpose |
|---|---|
| `nd_metadata_checker.py` | CLI entry point and orchestration |
| `checker.py` | Intersight client, fetch, and diff |
| `render.py` | Plain-text, markdown, and Adaptive Card renderers |
| `notify_webex.py` | Webex space discovery and message fan-out |
| `state/nd_metadata_state.json` | Last seen results (committed) |
| `state/last_run.txt` | Heartbeat keeping the scheduled workflow enabled |
| `.github/workflows/check.yml` | Nightly schedule and manual dispatch |

## Local use

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# ApiKey.txt and SecretKey.txt live in the repo root (both gitignored)
.venv/bin/python nd_metadata_checker.py            # print current downloads
.venv/bin/python nd_metadata_checker.py --force    # print even if unchanged
.venv/bin/python nd_metadata_checker.py --json     # machine-readable diff

export WEBEX_BOT_TOKEN='...'
.venv/bin/python nd_metadata_checker.py --force --notify webex --dry-run
```

| Flag | Effect |
|---|---|
| `--force` | Report even when nothing changed |
| `--notify webex` | Send to Webex in addition to stdout |
| `--dry-run` | Count recipients without sending; does not consume the change |
| `--state-file` | Override the state file path |
| `--json` | Emit the raw diff |

## Deployment

Schedule: `0 2 * * *` (02:00 UTC = 9 PM EST, 10 PM EDT). Cron is UTC-only, so the
local time shifts by an hour across DST.

Required repository secrets:

| Secret | Value |
|---|---|
| `INTERSIGHT_API_KEY_ID` | Contents of `ApiKey.txt` |
| `INTERSIGHT_SECRET_KEY` | Full PEM from `SecretKey.txt` |
| `WEBEX_BOT_TOKEN` | Bot token from developer.webex.com |
| `MAINTAINER_WEBEX_EMAIL` | Address for failure alerts |

Set `ALWAYS_FORCE: "true"` in the workflow to notify on every run (useful for
testing); `"false"` is change-only. Failures trigger a DM to the maintainer so a
broken run never looks like "no changes".

## Tests

```bash
.venv/bin/python -m pytest tests -q
```
