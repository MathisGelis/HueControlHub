import asyncio
import copy
import json

import pytest

from ambient_light import config as cfgmod
from ambient_light.events import teams_call_state
from ambient_light.state import StateManager
from ambient_light.teams.auth import Auth, TokenStore
from ambient_light.teams.http import TeamsError
from ambient_light.teams.source import TeamsSource, is_in_call, new_message_chats


def chat(cid, mid, sender="other", mtype="message"):
    return {"id": cid, "lastMessagePreview": {
        "id": mid, "messageType": mtype, "from": {"user": {"id": sender}}}}


def test_presence_mapping():
    assert is_in_call({"activity": "InACall"}, False)
    assert is_in_call({"activity": "InAConferenceCall"}, False)
    assert is_in_call({"activity": "InAMeeting"}, True)
    assert not is_in_call({"activity": "InAMeeting"}, False)
    assert not is_in_call({"activity": "Available"}, True)
    assert not is_in_call({}, True)


def test_new_messages_dedupe_own_and_system():
    seen = {}
    assert new_message_chats([chat("c1", "m1")], "me", seen) == ["c1"]
    assert new_message_chats([chat("c1", "m1")], "me", seen) == []  # doublon
    assert new_message_chats([chat("c1", "m2", sender="me")], "me", seen) == []  # envoyé par moi
    assert new_message_chats([chat("c2", "m9", mtype="systemEventMessage")], "me", seen) == []
    assert new_message_chats([chat("c1", "m3")], "me", seen) == ["c1"]
    assert new_message_chats([{"id": "x"}, {"lastMessagePreview": None}], "me", seen) == []


def make_source(responses):
    events = []
    cfg = copy.deepcopy(cfgmod.DEFAULTS)["teams"]

    def get(url, token):
        assert token == "tok"
        key = "presence" if "presence" in url else "chats" if "chats" in url else "me"
        r = responses[key]
        if isinstance(r, Exception):
            raise r
        return r

    class A:
        def access_token(self): return "tok"
        def refresh(self): return "tok"
    return TeamsSource(cfg, A(), events.append, get), events


def test_poll_chats_first_pass_seeds_then_alerts():
    resp = {"me": {"id": "me"}, "chats": {"value": [chat("c1", "m1")]}}
    src, events = make_source(resp)
    src.poll_chats()
    assert events == []  # état initial : pas d'alerte
    resp["chats"] = {"value": [chat("c1", "m2")]}
    src.poll_chats()
    assert len(events) == 1 and events[0].event_type == "message_received"
    assert "c1" not in events[0].session  # hash seulement


def test_presence_lifecycle_with_state_manager():
    resp = {"presence": {"activity": "InACall"}}
    src, events = make_source(resp)
    cfg = copy.deepcopy(cfgmod.DEFAULTS); cfg["sources"]["teams"] = True
    sm = StateManager(cfg)
    src.handle = lambda ev: (events.append(ev), sm.handle(ev))
    src.poll_presence(); src.poll_presence()
    assert sm.effective().reason == "call_ongoing" and len(sm.snapshot()) == 1
    resp["presence"] = {"activity": "Available"}
    src.poll_presence()
    assert sm.effective().reason == "idle"


def test_loop_survives_errors():
    src, _ = make_source({"presence": TeamsError("HTTP 403", 403)})
    async def go():
        stop = asyncio.Event()
        t = asyncio.create_task(src._loop(src.poll_presence, 5, stop))
        await asyncio.sleep(0.2)
        assert "erreur" in src.status
        stop.set(); await asyncio.wait_for(t, 2)
    asyncio.run(go())


def test_auth_device_flow_refresh_and_storage(tmp_path):
    now = [1000.0]
    calls = []

    def post(url, data):
        calls.append((url.rsplit("/", 1)[1], data.get("grant_type")))
        if url.endswith("devicecode"):
            return {"device_code": "dc", "user_code": "U", "verification_uri": "u",
                    "expires_in": 900, "interval": 1}
        if data["grant_type"].endswith("device_code"):
            if len([c for c in calls if c[0] == "token"]) < 2:
                raise TeamsError("HTTP 400 (authorization_pending)", 400)
            return {"access_token": "A1", "refresh_token": "R1", "expires_in": 3600}
        return {"access_token": "A2", "expires_in": 3600}  # refresh sans nouveau refresh_token

    def sleep(s): now[0] += s
    store = TokenStore(tmp_path / "t.json")
    auth = Auth("cid", "organizations", store, post, lambda: now[0], sleep)
    shown = []
    auth.login(shown.append)
    assert auth.access_token() == "A1"
    assert oct(store.path.stat().st_mode & 0o777) == "0o600"
    now[0] += 4000
    assert auth.access_token() == "A2"
    assert json.loads(store.path.read_text())["refresh_token"] == "R1"  # conservé
    with pytest.raises(TeamsError):
        Auth("", "t", store)


def test_daemon_with_teams_source(tmp_path):
    from ambient_light.controllers import FakeController
    from ambient_light.daemon import Daemon
    cfg = copy.deepcopy(cfgmod.DEFAULTS)
    cfg["sources"]["teams"] = True
    cfg["light"]["min_write_interval"] = 0.01
    ctrl = FakeController()
    src, _ = make_source({"presence": {"activity": "InACall"}})
    src.cfg = {**src.cfg, "messages": False, "poll_presence": 5}
    d = Daemon(cfg, ctrl, tmp_path / "s.sock")
    d.teams = src

    async def go():
        t = asyncio.create_task(d.run())
        await asyncio.sleep(0.5)
        assert ctrl.applied[-1].reason == "call_ongoing"
        assert d._dispatch({"cmd": "status"})["teams"] == "ok"
        d._stop.set(); await asyncio.wait_for(t, 3)
    asyncio.run(go())
