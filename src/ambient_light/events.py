"""Événements normalisés + traduction des hooks Claude Code."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from .config import EVENT_TYPES

_SESSION_RE = re.compile(r"[^A-Za-z0-9_.-]")


@dataclass(frozen=True)
class Event:
    source: str  # claude | teams | ...
    session: str  # identifiant de session/conversation (assaini)
    action: str  # "raise" | "clear"
    event_type: str = ""  # type levé (raise)
    clear_types: tuple[str, ...] = ()  # types à lever (clear) ; () = tous de la session
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.session}:{self.event_type}"


def _session(payload: dict) -> str:
    sid = payload.get("session_id")
    sid = sid if isinstance(sid, str) else "unknown"
    return _SESSION_RE.sub("_", sid)[:64] or "unknown"


def _raise(session: str, etype: str, **meta) -> Event:
    return Event("claude", session, "raise", event_type=etype, metadata=meta)


def _clear(session: str, *types: str) -> Event:
    return Event("claude", session, "clear", clear_types=types)


_BLOCKING = ("permission_required", "input_required", "task_error")


def from_claude_hook(payload: object) -> list[Event]:
    """Traduit le JSON d'un hook Claude Code. Types inconnus -> liste vide.

    Seuls les champs d'une liste blanche sont lus ; rien du contenu des
    messages/outils n'est conservé.
    """
    if not isinstance(payload, dict):
        return []
    name = payload.get("hook_event_name")
    sid = _session(payload)

    if name == "PermissionRequest":
        return [_raise(sid, "permission_required")]
    if name == "Notification":
        ntype = payload.get("notification_type")
        if ntype == "permission_prompt":
            return [_raise(sid, "permission_required")]
        if ntype in ("idle_prompt", "elicitation_dialog", "elicitation_url_dialog",
                     "agent_needs_input"):
            return [_raise(sid, "input_required", notification=ntype)]
        return []
    if name == "Stop":
        # Fin normale : résout les attentes, signal vert bref.
        return [_clear(sid, *_BLOCKING), _raise(sid, "task_completed")]
    if name == "StopFailure":
        err = payload.get("error")
        return [_clear(sid, *_BLOCKING),
                _raise(sid, "task_error", error=err if isinstance(err, str) else "unknown")]
    if name in ("UserPromptSubmit", "PostToolUse", "PostToolUseFailure", "PermissionDenied"):
        # L'utilisateur a répondu / l'outil s'est exécuté : l'attente est résolue.
        types = _BLOCKING if name == "UserPromptSubmit" else ("permission_required",)
        return [_clear(sid, *types)]
    if name == "SessionEnd":
        return [_clear(sid)]
    return []


def simulated(source: str, event_type: str, session: str = "sim") -> Event:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"type inconnu : {event_type}")
    return Event(source, session, "raise", event_type=event_type)
