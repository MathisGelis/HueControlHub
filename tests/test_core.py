import asyncio
import copy
import json

import pytest

from ambient_light import config as cfgmod
from ambient_light import install_hooks as ih
from ambient_light.colors import rgb_to_xy
from ambient_light.controllers import FakeController
from ambient_light.daemon import Daemon
from ambient_light.events import from_claude_hook, simulated
from ambient_light.state import StateManager


class Clock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t


def mk():
    clock = Clock()
    cfg = copy.deepcopy(cfgmod.DEFAULTS)
    cfg["sources"]["teams"] = True
    return StateManager(cfg, clock), clock


def feed(sm, payload):
    for ev in from_claude_hook(payload):
        sm.handle(ev)


def hook(name, sid="s1", **kw):
    return {"hook_event_name": name, "session_id": sid, **kw}


# --- normalisation
def test_normalize_permission_and_unknown():
    assert from_claude_hook(hook("PermissionRequest"))[0].event_type == "permission_required"
    assert from_claude_hook(hook("Notification", notification_type="auth_success")) == []
    assert from_claude_hook(hook("Whatever")) == []
    assert from_claude_hook("garbage") == []
    assert from_claude_hook(None) == []


def test_session_sanitized_and_no_content_kept():
    ev = from_claude_hook(hook("PermissionRequest", sid="../../x y", tool_input={"command": "rm"}))[0]
    assert "/" not in ev.session and " " not in ev.session
    assert ev.metadata == {}


# --- priorités
def test_task_completed_does_not_override_permission():
    sm, _ = mk()
    feed(sm, hook("PermissionRequest", sid="a"))
    feed(sm, hook("Stop", sid="b"))  # autre session : vert
    assert sm.effective().reason == "permission_required"


def test_green_expires_without_clearing_persistent():
    sm, clock = mk()
    feed(sm, hook("PermissionRequest", sid="a"))
    sm.handle(simulated("teams", "message_received"))
    clock.t = 6
    assert sm.effective().reason == "permission_required"
    assert [e["type"] for e in sm.snapshot()] == ["permission_required"]


def test_stop_flashes_green_then_idle():
    sm, clock = mk()
    feed(sm, hook("Stop"))
    assert sm.effective().reason == "task_completed"
    clock.t = 3.1
    assert sm.effective().reason == "idle"


def test_permission_cleared_by_posttooluse_and_stop_clears_blocking():
    sm, _ = mk()
    feed(sm, hook("PermissionRequest"))
    feed(sm, hook("PostToolUse"))
    assert sm.effective().reason == "idle"
    feed(sm, hook("Notification", notification_type="idle_prompt"))
    assert sm.effective().reason == "input_required"
    feed(sm, hook("UserPromptSubmit"))
    assert sm.effective().reason == "idle"


def test_error_is_not_completion_nor_permission():
    sm, _ = mk()
    feed(sm, hook("StopFailure", error="rate_limit"))
    assert sm.effective().reason == "task_error"


def test_teams_ordering_and_determinism():
    sm, _ = mk()
    sm.handle(simulated("teams", "call_ongoing"))
    sm.handle(simulated("teams", "call_incoming"))
    assert sm.effective().reason == "call_incoming"
    sm.handle(simulated("teams", "message_received"))
    assert sm.effective().reason == "call_incoming"


def test_duplicates_refresh_not_stack():
    sm, clock = mk()
    sm.handle(simulated("teams", "message_received"))
    clock.t = 4
    sm.handle(simulated("teams", "message_received"))
    assert len(sm.snapshot()) == 1
    clock.t = 8
    assert sm.effective().reason == "message_received"


def test_ack_and_session_end():
    sm, _ = mk()
    feed(sm, hook("PermissionRequest", sid="a"))
    feed(sm, hook("SessionEnd", sid="a"))
    assert sm.effective().reason == "idle"
    feed(sm, hook("PermissionRequest", sid="a"))
    assert sm.acknowledge() == 1


def test_disabled_source_ignored():
    cfg = copy.deepcopy(cfgmod.DEFAULTS)
    sm = StateManager(cfg, Clock())
    sm.handle(simulated("teams", "call_incoming"))  # teams=False par défaut
    assert sm.effective().reason == "idle"


# --- config
def test_config_override_and_errors(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('[events.task_completed]\ncolor = "#00FFAA"\nduration = 1\n')
    cfg = cfgmod.load(p)
    assert cfg["events"]["task_completed"]["color"] == "#00FFAA"
    assert cfg["events"]["permission_required"]["color"] == "#FF0000"
    p.write_text("[light]\nbogus = 1\n")
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.load(p)
    p.write_text('[events.task_completed]\ncolor = "red"\n')
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.load(p)


def test_colors_distinct():
    xy = {n: rgb_to_xy(c) for n, c in
          dict(r=(255, 0, 0), o=(255, 106, 0), g=(0, 255, 0), b=(0, 0, 255)).items()}
    assert len(set(xy.values())) == 4


# --- install hooks
def test_install_preserves_existing_and_is_idempotent(tmp_path):
    p = tmp_path / "settings.json"
    existing = {"model": "x", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo hi"}]}]}}
    p.write_text(json.dumps(existing))
    ih.install(p); ih.install(p)
    data = json.loads(p.read_text())
    assert data["model"] == "x"
    assert len(data["hooks"]["Stop"]) == 2
    assert data["hooks"]["Stop"][0]["hooks"][0]["command"] == "echo hi"
    assert ih.uninstall(p) == len(ih.EVENTS)
    assert json.loads(p.read_text())["hooks"] == {"Stop": existing["hooks"]["Stop"]}


# --- intégration daemon (faux contrôleur, vrai socket)
def test_daemon_end_to_end(tmp_path, monkeypatch):
    sock = tmp_path / "s.sock"
    cfg = copy.deepcopy(cfgmod.DEFAULTS)
    cfg["light"]["min_write_interval"] = 0.01
    ctrl = FakeController()

    async def call(msg):
        r, w = await asyncio.open_unix_connection(str(sock))
        w.write((json.dumps(msg) + "\n").encode()); await w.drain()
        out = json.loads(await r.readline()); w.close(); return out

    async def scenario():
        d = Daemon(cfg, ctrl, sock)
        t = asyncio.create_task(d.run())
        await asyncio.sleep(0.2)
        await call({"cmd": "claude_hook", "payload": hook("PermissionRequest")})
        await asyncio.sleep(0.2)
        assert ctrl.applied[-1].reason == "permission_required"
        # perte de connexion puis reprise : l'état est réappliqué
        ctrl.fail_next = 1
        await call({"cmd": "claude_hook", "payload": hook("PermissionRequest", sid="s2")})
        await call({"cmd": "sim", "source": "claude", "type": "input_required"})
        await asyncio.sleep(2.5)
        assert ctrl.connected and ctrl.applied[-1].reason == "permission_required"
        assert (await call({"cmd": "bogus"}))["ok"] is False
        await call({"cmd": "claude_hook", "payload": hook("SessionEnd")})
        await call({"cmd": "claude_hook", "payload": hook("SessionEnd", sid="s2")})
        await call({"cmd": "ack"})
        await asyncio.sleep(0.2)
        assert ctrl.applied[-1].reason == "idle"
        await call({"cmd": "quit"})
        await asyncio.wait_for(t, 3)
        assert ctrl.applied[-1].rgb is None and not sock.exists()

    asyncio.run(scenario())
