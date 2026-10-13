"""Source d'événements Teams via Microsoft Graph (polling local, sans webhook).

Couvre : appel/réunion en cours (presence) et nouveaux messages de chats 1:1
et de groupe (lastMessagePreview). NE couvre PAS : sonnerie d'appel entrant,
messages de canaux (droits administrateur), mentions.
Aucun contenu de message n'est lu, stocké ni journalisé.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable

from ..events import Event, teams_call_state, teams_message
from .auth import Auth
from .http import TeamsError, get_json

log = logging.getLogger("ambient_light.teams")
GRAPH = "https://graph.microsoft.com/v1.0"
CALL_ACTIVITIES = {"InACall", "InAConferenceCall", "Presenting"}
CHATS_URL = (f"{GRAPH}/me/chats?$expand=lastMessagePreview"
             "&$orderby=lastMessagePreview/createdDateTime desc&$top=20")


def is_in_call(presence: dict, meeting_counts: bool) -> bool:
    activity = presence.get("activity")
    return activity in CALL_ACTIVITIES or (meeting_counts and activity == "InAMeeting")


def new_message_chats(chats: list[dict], me_id: str, seen: dict[str, str]) -> list[str]:
    """Retourne les ids de chats avec un nouveau message d'autrui. Met `seen` à jour
    (chat id -> id du dernier message vu) : un même message n'alerte qu'une fois."""
    fresh = []
    for chat in chats:
        prev = chat.get("lastMessagePreview")
        cid = chat.get("id")
        if not isinstance(prev, dict) or not isinstance(cid, str) or not prev.get("id"):
            continue
        if seen.get(cid) == prev["id"]:
            continue
        seen[cid] = prev["id"]
        sender = ((prev.get("from") or {}).get("user") or {}).get("id")
        if prev.get("messageType", "message") != "message" or prev.get("isDeleted"):
            continue
        if sender and sender == me_id:  # message envoyé par l'utilisateur
            continue
        fresh.append(cid)
    return fresh


class TeamsSource:
    def __init__(self, tcfg: dict, auth: Auth, handle: Callable[[Event], None],
                 get=get_json):
        self.cfg, self.auth, self.handle, self._get = tcfg, auth, handle, get
        self.status = "starting"
        self._me_id: str | None = None
        self._seen: dict[str, str] = {}
        self._seeded = False
        self._in_call: bool | None = None

    def _call(self, url: str) -> dict:
        try:
            return self._get(url, self.auth.access_token())
        except TeamsError as exc:
            if exc.status != 401:
                raise
            return self._get(url, self.auth.refresh())

    def poll_presence(self) -> None:
        in_call = is_in_call(self._call(f"{GRAPH}/me/presence"), self.cfg["meeting_counts_as_call"])
        # on réémet à chaque poll tant que l'appel dure (persistant, sans doublon : même clé)
        if in_call or in_call != self._in_call:
            self.handle(teams_call_state(in_call))
        self._in_call = in_call

    def poll_chats(self) -> None:
        if self._me_id is None:
            self._me_id = self._call(f"{GRAPH}/me?$select=id").get("id", "")
        chats = self._call(CHATS_URL).get("value", [])
        fresh = new_message_chats(chats, self._me_id, self._seen)
        if not self._seeded:  # premier passage : état initial, pas d'alerte
            self._seeded = True
            return
        for cid in fresh:
            self.handle(teams_message(cid))

    async def run(self, stop: asyncio.Event) -> None:
        loops = [self._loop(self.poll_presence, self.cfg["poll_presence"], stop)]
        if self.cfg["messages"]:
            loops.append(self._loop(self.poll_chats, self.cfg["poll_chats"], stop))
        await asyncio.gather(*loops)

    async def _loop(self, fn, interval: float, stop: asyncio.Event) -> None:
        failures = 0
        while not stop.is_set():
            delay = interval
            try:
                await asyncio.to_thread(fn)
                self.status, failures = "ok", 0
            except TeamsError as exc:
                failures += 1
                self.status = f"erreur: {exc}"
                log.warning("teams %s : %s", fn.__name__, exc)
                delay = exc.retry_after or min(interval * 2 ** min(failures, 5), 300)
                if exc.status in (400, 401, 403):  # consentement/session : inutile d'insister
                    delay = max(delay, 300)
            except Exception as exc:  # jamais fatal
                failures += 1
                self.status = f"erreur: {type(exc).__name__}"
                log.warning("teams %s : %s", fn.__name__, type(exc).__name__)
                delay = min(interval * 2 ** min(failures, 5), 300)
            try:
                await asyncio.wait_for(stop.wait(), delay)
            except asyncio.TimeoutError:
                pass
