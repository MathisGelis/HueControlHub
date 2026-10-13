"""HTTP minimal (stdlib). Les erreurs ne contiennent jamais de jeton."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


class TeamsError(Exception):
    def __init__(self, message: str, status: int | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


def _open(req: urllib.request.Request) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        body = {}
        try:
            body = json.loads(exc.read() or b"{}")
        except ValueError:
            pass
        code = body.get("error") if isinstance(body.get("error"), str) else None
        ra = exc.headers.get("Retry-After") if exc.headers else None
        raise TeamsError(f"HTTP {exc.code}" + (f" ({code})" if code else ""), exc.code,
                         float(ra) if ra and ra.isdigit() else None) from None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        raise TeamsError(f"réseau : {type(exc).__name__}") from None


def post_form(url: str, data: dict) -> dict:
    req = urllib.request.Request(url, urllib.parse.urlencode(data).encode(), method="POST")
    return _open(req)


def get_json(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    return _open(req)
