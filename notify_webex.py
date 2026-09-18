"""Fan out Nexus Dashboard metadata alerts as individual Webex 1:1 messages.

The recipient list is read from Webex at send time (the bot's direct rooms), so no
customer identity is ever stored locally.
"""

from __future__ import annotations

import os
import time

import requests

API_BASE = "https://webexapis.com/v1"
OPT_OUT_WORDS = {"stop", "unsubscribe", "quiet", "mute"}
OPT_IN_WORDS = {"start", "subscribe", "resume"}
TIMEOUT = 30
MAX_RETRIES = 3


class WebexError(RuntimeError):
    pass


class WebexClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        for attempt in range(MAX_RETRIES):
            response = self.session.request(method, url, timeout=TIMEOUT, **kwargs)
            if response.status_code == 429 and attempt < MAX_RETRIES - 1:
                time.sleep(min(int(response.headers.get("Retry-After", 5)), 60))
                continue
            if not response.ok:
                raise WebexError(f"{method} {url} -> {response.status_code}")
            return response
        raise WebexError(f"{method} {url} -> rate limited after {MAX_RETRIES} attempts")

    def _paginate(self, url: str, params: dict) -> list[dict]:
        items: list[dict] = []
        while url:
            response = self._request("GET", url, params=params)
            items.extend(response.json().get("items", []))
            url = response.links.get("next", {}).get("url", "")
            params = {}
        return items

    def my_person_id(self) -> str:
        return self._request("GET", f"{API_BASE}/people/me").json()["id"]

    def rooms(self) -> list[dict]:
        """Every space the bot belongs to, 1:1 and group."""
        return self._paginate(f"{API_BASE}/rooms", {"max": 100})

    def last_inbound_message(self, room_id: str, bot_person_id: str) -> str:
        items = self._request(
            "GET", f"{API_BASE}/messages", params={"roomId": room_id, "max": 5}
        ).json().get("items", [])
        for message in items:
            if message.get("personId") != bot_person_id:
                return (message.get("text") or "").strip().lower()
        return ""

    def send_markdown(self, room_id: str, markdown: str, card: dict | None = None) -> None:
        payload: dict = {"roomId": room_id, "markdown": markdown}
        if card:
            payload["attachments"] = [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": card,
                }
            ]
        self._request("POST", f"{API_BASE}/messages", json=payload)


def _opted_out(client: WebexClient, room_id: str, bot_person_id: str) -> bool:
    # Group-space mentions arrive as "BotName stop", so match on words, not the whole string.
    words = set(
        client.last_inbound_message(room_id, bot_person_id).replace(",", " ").split()
    )
    if words & OPT_IN_WORDS:
        return False
    return bool(words & OPT_OUT_WORDS)


def notify(
    markdown: str,
    *,
    card: dict | None = None,
    dry_run: bool = False,
    token: str | None = None,
) -> dict:
    """Send `markdown` to every space the bot is in that has not opted out."""
    token = token or os.environ.get("WEBEX_BOT_TOKEN")
    if not token:
        raise WebexError("WEBEX_BOT_TOKEN is not set")

    client = WebexClient(token)
    bot_person_id = client.my_person_id()
    rooms = client.rooms()

    sent = skipped = failed = 0
    for room in rooms:
        room_id = room["id"]
        if _opted_out(client, room_id, bot_person_id):
            skipped += 1
            continue
        if dry_run:
            sent += 1
            continue
        try:
            client.send_markdown(room_id, markdown, card)
            sent += 1
        except WebexError:
            failed += 1

    return {"rooms": len(rooms), "sent": sent, "skipped": skipped, "failed": failed}


def notify_person(email: str, markdown: str, token: str | None = None) -> None:
    """Send a direct message to one address, used for maintainer failure alerts."""
    token = token or os.environ.get("WEBEX_BOT_TOKEN")
    if not token:
        raise WebexError("WEBEX_BOT_TOKEN is not set")
    WebexClient(token)._request(
        "POST", f"{API_BASE}/messages", json={"toPersonEmail": email, "markdown": markdown}
    )
