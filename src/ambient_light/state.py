"""State Manager : états indépendants, arbitrage déterministe, expiration."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from . import config as cfgmod
from .events import Event


@dataclass(frozen=True)
class LightState:
    """État lumineux effectif. rgb=None => ampoule éteinte (soft off)."""
    rgb: tuple[int, int, int] | None
    brightness: int = 254
    reason: str = "idle"  # type d'événement affiché, ou "idle"


@dataclass
class _Active:
    event: Event
    priority: int
    rgb: tuple[int, int, int]
    expires_at: float | None  # None = persistant
    seq: int


class StateManager:
    def __init__(self, cfg: dict, clock: Callable[[], float] = time.monotonic):
        self._cfg = cfg
        self._clock = clock
        self._active: dict[str, _Active] = {}
        self._seq = 0
        self._neutral = cfgmod.parse_color(cfg["light"]["neutral_color"])
        self._brightness = cfg["light"]["brightness"]

    def handle(self, event: Event) -> None:
        if not self._cfg["sources"].get(event.source, True):
            return
        if event.action == "clear":
            for key in [k for k, a in self._active.items()
                        if a.event.source == event.source
                        and a.event.session == event.session
                        and (not event.clear_types or a.event.event_type in event.clear_types)]:
                del self._active[key]
            return
        rule = self._cfg["events"].get(event.event_type)
        if rule is None:
            return
        self._seq += 1
        dur = rule["duration"]
        self._active[event.key] = _Active(
            event=event,
            priority=rule["priority"],
            rgb=cfgmod.parse_color(rule["color"]),
            expires_at=self._clock() + dur if dur > 0 else None,
            seq=self._seq,
        )

    def expire(self) -> None:
        now = self._clock()
        for key in [k for k, a in self._active.items()
                    if a.expires_at is not None and a.expires_at <= now]:
            del self._active[key]

    def acknowledge(self) -> int:
        """Acquitte tous les événements actifs (CLI). Retourne leur nombre."""
        n = len(self._active)
        self._active.clear()
        return n

    def next_expiry(self) -> float | None:
        times = [a.expires_at for a in self._active.values() if a.expires_at is not None]
        return min(times) if times else None

    def effective(self) -> LightState:
        """Plus haute priorité ; à égalité, le plus récent. Déterministe."""
        self.expire()
        if not self._active:
            return LightState(self._neutral, self._brightness, "idle")
        top = max(self._active.values(), key=lambda a: (a.priority, a.seq))
        return LightState(top.rgb, self._brightness, top.event.event_type)

    def snapshot(self) -> list[dict]:
        now = self._clock()
        return [
            {"source": a.event.source, "session": a.event.session,
             "type": a.event.event_type, "priority": a.priority,
             "expires_in": None if a.expires_at is None else round(a.expires_at - now, 1)}
            for a in sorted(self._active.values(), key=lambda a: (-a.priority, -a.seq))
        ]
