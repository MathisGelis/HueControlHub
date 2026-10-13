"""Client synchrone du socket du daemon (rapide, borné par un timeout)."""
from __future__ import annotations

import json
import socket

from .config import socket_path


def send(msg: dict, timeout: float = 0.5) -> dict | None:
    """Envoie un message ; None si le daemon est injoignable."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(str(socket_path()))
            s.sendall((json.dumps(msg) + "\n").encode())
            data = s.makefile("rb").readline()
        return json.loads(data)
    except (OSError, ValueError):
        return None
