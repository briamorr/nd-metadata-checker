"""Report Nexus Dashboard metadata downloads from Intersight when they change."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import intersight

import render
from checker import DEFAULT_HOST, build_client, diff_downloads, fetch_downloads

DEFAULT_STATE_FILE = Path("state/nd_metadata_state.json")


def load_state(state_file: Path) -> list[dict] | None:
    try:
        return json.loads(state_file.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_state(state_file: Path, rows: list[dict]) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(rows, indent=2) + "\n")


def write_heartbeat(state_dir: Path) -> None:
    """Touch a file every run so the repo stays active and the cron isn't disabled."""
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "last_run.txt").write_text(
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") + "\n"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-key-file", type=Path, default=Path("ApiKey.txt"))
    parser.add_argument("--secret-key-file", type=Path, default=Path("SecretKey.txt"))
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--json", action="store_true", help="output raw JSON")
    parser.add_argument(
        "--state-file",
        type=Path,
        default=DEFAULT_STATE_FILE,
        help="file holding the last seen results",
    )
    parser.add_argument(
        "--force", action="store_true", help="report even when nothing changed"
    )
    parser.add_argument(
        "--notify",
        choices=("none", "webex"),
        default="none",
        help="also send the report to Webex subscribers",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="with --notify webex, count recipients without sending",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        client = build_client(args.host, args.api_key_file, args.secret_key_file)
        current = fetch_downloads(client)
    except FileNotFoundError as exc:
        print(f"Missing credential file: {exc.filename}", file=sys.stderr)
        return 1
    except intersight.OpenApiException as exc:
        print(f"Intersight API error: {exc}", file=sys.stderr)
        return 1

    diff = diff_downloads(load_state(args.state_file), current)
    write_heartbeat(args.state_file.parent)

    if not diff["changed"] and not args.force:
        return 0

    if args.json:
        print(json.dumps(diff, indent=2))
    else:
        print(render.to_text(diff))

    if args.notify == "webex":
        import notify_webex

        try:
            result = notify_webex.notify(
                render.to_markdown(diff),
                card=render.to_card(diff),
                dry_run=args.dry_run,
            )
        except notify_webex.WebexError as exc:
            # State is left untouched so the next run retries this alert.
            print(f"Webex notification failed: {exc}", file=sys.stderr)
            return 1
        print(
            f"Webex: {result['sent']} sent, {result['skipped']} opted out, "
            f"{result['failed']} failed of {result['rooms']} spaces"
            + (" (dry run)" if args.dry_run else ""),
            file=sys.stderr,
        )
        if result["failed"]:
            return 1
        if args.dry_run:
            return 0

    save_state(args.state_file, current)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
