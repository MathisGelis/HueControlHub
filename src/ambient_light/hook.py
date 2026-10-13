"""Hook Claude Code : lit le JSON sur stdin, le transmet au daemon.

Rapide, silencieux, ne bloque jamais Claude Code : exit 0 dans tous les cas
(timeout socket 0,5 s ; aucune opération Bluetooth ici). Aucune sortie sur
stdout/stderr (stdout pourrait être interprété par Claude Code).
"""
from __future__ import annotations

import json
import sys


def run() -> int:
    try:
        raw = sys.stdin.read(65536)
        payload = json.loads(raw)
        from .client import send
        send({"cmd": "claude_hook", "payload": payload}, timeout=0.5)
    except Exception:
        pass
    return 0
