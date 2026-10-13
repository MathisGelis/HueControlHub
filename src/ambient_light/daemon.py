"""Daemon local : socket Unix (0600) -> StateManager -> HueController."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal

from . import config as cfgmod
from .controllers import ControllerError, HueController
from .events import Event, from_claude_hook, simulated
from .state import LightState, StateManager

log = logging.getLogger("ambient_light")
MAX_LINE = 64 * 1024


class Daemon:
    def __init__(self, cfg: dict, controller: HueController, sock_path=None):
        self.cfg = cfg
        self.controller = controller
        self.state = StateManager(cfg)
        self.sock_path = sock_path or cfgmod.socket_path()
        self._dirty = asyncio.Event()
        self._stop = asyncio.Event()
        self._last_applied: LightState | None = None
        self.link_status = "disconnected"
        self._failures = 0

    # --- réception -------------------------------------------------------
    def _dispatch(self, msg: dict) -> dict:
        cmd = msg.get("cmd")
        if cmd == "claude_hook":
            for ev in from_claude_hook(msg.get("payload")):
                self.state.handle(ev)
            self._dirty.set()
            return {"ok": True}
        if cmd == "sim":
            try:
                ev = simulated(str(msg.get("source", "sim")), str(msg.get("type")))
            except ValueError as exc:
                return {"ok": False, "error": str(exc)}
            self.state.handle(ev)
            self._dirty.set()
            return {"ok": True}
        if cmd == "ack":
            n = self.state.acknowledge()
            self._dirty.set()
            return {"ok": True, "acknowledged": n}
        if cmd == "status":
            eff = self.state.effective()
            return {"ok": True, "link": self.link_status,
                    "effective": {"reason": eff.reason, "rgb": eff.rgb},
                    "active": self.state.snapshot()}
        if cmd == "quit":
            self._stop.set()
            return {"ok": True}
        return {"ok": False, "error": "commande inconnue"}

    async def _client(self, reader, writer):
        try:
            line = await asyncio.wait_for(reader.readline(), 2)
            if len(line) > MAX_LINE:
                raise ValueError("message trop long")
            msg = json.loads(line)
            reply = self._dispatch(msg) if isinstance(msg, dict) else {"ok": False}
        except Exception:  # entrée invalide : jamais fatal
            reply = {"ok": False, "error": "requête invalide"}
        try:
            writer.write((json.dumps(reply) + "\n").encode())
            await writer.drain()
        finally:
            writer.close()

    # --- boucle lumière --------------------------------------------------
    async def _ensure_connected(self) -> bool:
        if self.controller.is_available():
            return True
        try:
            await self.controller.connect()
            self.link_status = "connected"
            self._failures = 0
            self._last_applied = None  # réappliquer l'état après reconnexion
            log.info("ampoule connectée")
            return True
        except ControllerError as exc:
            self._failures += 1
            self.link_status = "disconnected"
            log.warning("connexion échouée (%d) : %s", self._failures, exc)
            return False

    async def _light_loop(self):
        interval = self.cfg["light"]["min_write_interval"]
        max_delay = self.cfg["light"]["reconnect_max_delay"]
        retry = self.cfg["light"]["on_disconnect"] == "retry"
        while not self._stop.is_set():
            target = self.state.effective()
            if target != self._last_applied:
                if await self._ensure_connected():
                    try:
                        await self.controller.apply(target)
                        self._last_applied = target
                        await asyncio.sleep(interval)  # anti-saturation
                        continue
                    except ControllerError as exc:
                        self.link_status = "disconnected"
                        self._failures += 1
                        log.warning("écriture échouée : %s", exc)
                if not retry:
                    self._last_applied = target  # abandon de cet état
                else:
                    delay = min(2 ** min(self._failures, 6), max_delay)
                    await self._wait(delay)
                    continue
            # attendre un changement ou la prochaine expiration
            nxt = self.state.next_expiry()
            timeout = None if nxt is None else max(0.05, nxt - self.state._clock())
            await self._wait(timeout)

    async def _wait(self, timeout):
        self._dirty.clear()
        try:
            await asyncio.wait_for(self._dirty.wait(), timeout)
        except asyncio.TimeoutError:
            pass

    # --- cycle de vie ----------------------------------------------------
    async def run(self):
        path = str(self.sock_path)
        if os.path.exists(path):
            if await _alive(path):
                raise RuntimeError("un daemon tourne déjà")
            os.unlink(path)
        old = os.umask(0o177)
        try:
            server = await asyncio.start_unix_server(self._client, path=path)
        finally:
            os.umask(old)
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._stop.set)
        task = asyncio.create_task(self._light_loop())
        log.info("daemon démarré (%s)", path)
        await self._stop.wait()
        self._dirty.set()
        task.cancel()
        server.close()
        try:
            await self.controller.apply(LightState(None, reason="shutdown"))
        except Exception:
            pass
        await self.controller.disconnect()
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        log.info("daemon arrêté")


async def _alive(path: str) -> bool:
    try:
        r, w = await asyncio.wait_for(asyncio.open_unix_connection(path), 0.5)
        w.close()
        return True
    except Exception:
        return False
