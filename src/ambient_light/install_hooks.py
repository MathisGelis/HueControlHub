"""Installation/désinstallation des hooks dans ~/.claude/settings.json.

Fusionne sans écraser : nos entrées sont repérées par un marqueur dans la
commande ; les hooks existants ne sont jamais modifiés.
"""
from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

MARKER = "ambient_light hook"
EVENTS = ["PermissionRequest", "Notification", "Stop", "StopFailure",
          "UserPromptSubmit", "PostToolUse", "PostToolUseFailure",
          "PermissionDenied", "SessionEnd"]


def settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def command() -> str:
    return f"{shlex.quote(sys.executable)} -m {MARKER}"


def _is_ours(group: dict) -> bool:
    return any(MARKER in h.get("command", "") for h in group.get("hooks", []))


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} : objet JSON attendu")
    return data


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.with_suffix(".json.bak").write_text(path.read_text(encoding="utf-8"),
                                                 encoding="utf-8")
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def install(path: Path | None = None) -> list[str]:
    path = path or settings_path()
    data = _load(path)
    hooks = data.setdefault("hooks", {})
    cmd = command()
    for ev in EVENTS:
        groups = hooks.setdefault(ev, [])
        groups[:] = [g for g in groups if not _is_ours(g)]  # idempotent
        groups.append({"hooks": [{"type": "command", "command": cmd,
                                  "timeout": 5, "async": True}]})
    _write(path, data)
    return EVENTS


def uninstall(path: Path | None = None) -> int:
    path = path or settings_path()
    data = _load(path)
    removed = 0
    hooks = data.get("hooks", {})
    for ev in list(hooks):
        kept = [g for g in hooks[ev] if not _is_ours(g)]
        removed += len(hooks[ev]) - len(kept)
        if kept:
            hooks[ev] = kept
        else:
            del hooks[ev]
    if removed:
        _write(path, data)
    return removed
