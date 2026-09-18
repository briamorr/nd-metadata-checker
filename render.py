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
    """Fallback text for clients that cannot render the Adaptive Card.

    Webex does not render markdown tables in messages, so this stays list-based.
    """
    lines = [f"**{_summary(diff)}**", ""]

    if not diff["first_run"]:
        for row in diff["added"]:
            lines.append(f"- **New:** {row.get('Name', '')} — released {row.get('ReleaseDate', '')}")
        for entry in diff["updated"]:
            changes = "; ".join(
                f"{f} {entry['previous'].get(f, '')} → {entry['current'].get(f, '')}"
                for f in entry["fields"]
            )
            lines.append(f"- **Updated:** {entry['current'].get('Name', '')} — {changes}")
        for row in diff["removed"]:
            lines.append(f"- **Removed:** {row.get('Name', '')} is no longer listed")
        lines.append("")

    lines.append("**Currently available**")
    for row in diff["current"]:
        lines.append(
            f"- **{row.get('Name', '')}** — version {row.get('Version', '')}, "
            f"released {row.get('ReleaseDate', '')}"
        )
        lines.append(f"  {row.get('Description', '')}")
    return "\n".join(lines)


def _text_block(text: str, **kwargs) -> dict:
    return {"type": "TextBlock", "text": text, "wrap": True, **kwargs}


def _change_blocks(diff: dict) -> list[dict]:
    blocks = []
    for row in diff["added"]:
        blocks.append(
            _text_block(f"**New** · {row.get('Name', '')} ({row.get('ReleaseDate', '')})", color="Good")
        )
    for entry in diff["updated"]:
        changes = ", ".join(
            f"{f}: {entry['previous'].get(f, '')} → {entry['current'].get(f, '')}"
            for f in entry["fields"]
        )
        blocks.append(
            _text_block(f"**Updated** · {entry['current'].get('Name', '')} — {changes}", color="Warning")
        )
    for row in diff["removed"]:
        blocks.append(
            _text_block(f"**Removed** · {row.get('Name', '')}", color="Attention")
        )
    return blocks


def to_card(diff: dict) -> dict:
    """Build an Adaptive Card payload for the Webex message attachment."""
    body: list[dict] = [
        _text_block(
            "Nexus Dashboard Metadata Update Available", size="Medium", weight="Bolder"
        ),
        _text_block(
            "Download at [https://www.intersight.com](https://www.intersight.com)",
            isSubtle=True,
            spacing="None",
        ),
    ]

    changes = _change_blocks(diff) if not diff["first_run"] else []
    if changes:
        body.append({"type": "Container", "separator": True, "items": changes})

    for index, row in enumerate(diff["current"]):
        body.append(
            {
                "type": "Container",
                "separator": True,
                "spacing": "ExtraLarge" if index else "Large",
                "items": [
                    _text_block(row.get("Name", ""), weight="Bolder", size="Medium"),
                    _text_block(row.get("Description", ""), isSubtle=True, spacing="Small"),
                    {
                        "type": "ColumnSet",
                        "spacing": "Medium",
                        "columns": [
                            {
                                "type": "Column",
                                "width": "stretch",
                                "items": [
                                    _text_block("RELEASED", isSubtle=True, size="Small", weight="Bolder"),
                                    _text_block(row.get("ReleaseDate", ""), spacing="None"),
                                ],
                            },
                            {
                                "type": "Column",
                                "width": "stretch",
                                "items": [
                                    _text_block("VERSION", isSubtle=True, size="Small", weight="Bolder"),
                                    _text_block(str(row.get("Version", "")), spacing="None"),
                                ],
                            },
                        ],
                    },
                ],
            }
        )

    return {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.3",
        "body": body,
    }



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
