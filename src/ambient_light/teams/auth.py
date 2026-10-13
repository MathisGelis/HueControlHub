"""OAuth2 device code flow (client public) + jeton de rafraîchissement local.

Le jeton est stocké dans un fichier séparé de la config (0600, hors Git) et
n'est jamais journalisé.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable

from . import http as _http
from .http import TeamsError

SCOPES = "Presence.Read Chat.Read offline_access"
AUTHORITY = "https://login.microsoftonline.com"


class TokenStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict | None:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, self.path)

    def delete(self) -> bool:
        try:
            self.path.unlink()
            return True
        except FileNotFoundError:
            return False


class Auth:
    def __init__(self, client_id: str, tenant: str, store: TokenStore,
                 post=_http.post_form, clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep):
        if not client_id:
            raise TeamsError("teams.client_id non configuré")
        self.client_id, self.tenant, self.store = client_id, tenant, store
        self._post, self._clock, self._sleep = post, clock, sleep
        self._token: dict | None = store.load()

    def _url(self, leaf: str) -> str:
        return f"{AUTHORITY}/{self.tenant}/oauth2/v2.0/{leaf}"

    def _store_response(self, resp: dict) -> None:
        self._token = {
            "access_token": resp["access_token"],
            "refresh_token": resp.get("refresh_token") or (self._token or {}).get("refresh_token"),
            "expires_at": self._clock() + int(resp.get("expires_in", 3600)) - 60,
        }
        self.store.save(self._token)

    def login(self, show: Callable[[str], None] = print) -> None:
        dc = self._post(self._url("devicecode"),
                        {"client_id": self.client_id, "scope": SCOPES})
        show(dc.get("message") or f"Ouvrir {dc['verification_uri']} et saisir {dc['user_code']}")
        deadline = self._clock() + int(dc.get("expires_in", 900))
        interval = int(dc.get("interval", 5))
        while self._clock() < deadline:
            self._sleep(interval)
            try:
                resp = self._post(self._url("token"), {
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "client_id": self.client_id, "device_code": dc["device_code"]})
            except TeamsError as exc:
                if exc.status == 400 and "authorization_pending" in str(exc):
                    continue
                if exc.status == 400 and "slow_down" in str(exc):
                    interval += 5
                    continue
                raise
            self._store_response(resp)
            return
        raise TeamsError("connexion expirée")

    def access_token(self) -> str:
        t = self._token
        if not t:
            raise TeamsError("non connecté : lancer `ambient-light teams-login`")
        if t["expires_at"] > self._clock():
            return t["access_token"]
        return self.refresh()

    def refresh(self) -> str:
        t = self._token
        if not t or not t.get("refresh_token"):
            raise TeamsError("session expirée : relancer `ambient-light teams-login`")
        try:
            resp = self._post(self._url("token"), {
                "grant_type": "refresh_token", "client_id": self.client_id,
                "refresh_token": t["refresh_token"], "scope": SCOPES})
        except TeamsError as exc:
            if exc.status in (400, 401):
                raise TeamsError("session expirée : relancer `ambient-light teams-login`") from None
            raise
        self._store_response(resp)
        return self._token["access_token"]
