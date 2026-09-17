"""Render Nexus Dashboard metadata diffs as plain text or Webex markdown."""

from __future__ import annotations

from checker import FIELDS

LABELS = list(FIELDS)


def _summary(diff: dict) -> str:
    if diff["first_run"]:
        return f"Nexus Dashboard metadata baseline: {len(diff['current'])} download(s)."
    parts = []
    for key, word in (("added", "new"), ("updated", "updated"), ("removed", "removed")):
        if diff[key]:
            parts.append(f"{len(diff[key])} {word}")
    if not parts:
        return f"Nexus Dashboard metadata unchanged: {len(diff['current'])} download(s)."
    return "Nexus Dashboard metadata change detected: " + ", ".join(parts) + "."


def _describe(row: dict) -> str:
    return f"{row.get('Name', '')} ({row.get('ReleaseDate', '')}) - {row.get('Description', '')}"


def to_text(diff: dict) -> str:
    lines = [_summary(diff), ""]

    if diff["first_run"] or not (diff["added"] or diff["updated"] or diff["removed"]):
        lines.extend(f"  {_describe(row)}" for row in diff["current"])
        return "\n".join(lines)

    for row in diff["added"]:
        lines.append(f"  [NEW] {_describe(row)}")
    for entry in diff["updated"]:
        changes = ", ".join(
            f"{f}: {entry['previous'].get(f, '')} -> {entry['current'].get(f, '')}"
            for f in entry["fields"]
        )
        lines.append(f"  [UPDATED] {entry['current'].get('Name', '')} ({changes})")
    for row in diff["removed"]:
        lines.append(f"  [REMOVED] {row.get('Name', '')}")
    return "\n".join(lines)


def to_markdown(diff: dict) -> str:
    lines = [f"**{_summary(diff)}**", ""]

    if not diff["first_run"]:
        for row in diff["added"]:
            lines.append(f"- **New:** `{row.get('Name', '')}` — released {row.get('ReleaseDate', '')}  \n  {row.get('Description', '')}")
        for entry in diff["updated"]:
            changes = "; ".join(
                f"{f} `{entry['previous'].get(f, '')}` → `{entry['current'].get(f, '')}`"
                for f in entry["fields"]
            )
            lines.append(f"- **Updated:** `{entry['current'].get('Name', '')}` — {changes}")
        for row in diff["removed"]:
            lines.append(f"- **Removed:** `{row.get('Name', '')}`")
        lines.append("")

    lines.append("Currently available:")
    lines.append("| " + " | ".join(LABELS) + " |")
    lines.append("| " + " | ".join("---" for _ in LABELS) + " |")
    for row in diff["current"]:
        lines.append("| " + " | ".join(str(row.get(label) or "") for label in LABELS) + " |")
    return "\n".join(lines)


def print_table(rows: list[dict]) -> None:
    cells = [[str(row.get(label) or "") for label in LABELS] for row in rows]
    widths = [
        max([len(LABELS[i])] + [len(cell[i]) for cell in cells])
        for i in range(len(LABELS))
    ]
    print("  ".join(name.ljust(widths[i]) for i, name in enumerate(LABELS)))
    print("  ".join("-" * w for w in widths))
    for cell in cells:
        print("  ".join(value.ljust(widths[i]) for i, value in enumerate(cell)))
