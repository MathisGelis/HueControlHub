"""CLI : ambient-light <commande>."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from . import config as cfgmod
from .client import send
from .config import EVENT_TYPES, ConfigError
from .teams.http import TeamsError


def _cfg(args):
    return cfgmod.load(Path(args.config) if args.config else None)


def cmd_run(args) -> int:
    from .controllers import create
    from .daemon import Daemon
    cfg = _cfg(args)
    if args.simulate:
        cfg["light"]["controller"] = "fake"
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ctrl = create(cfg, verbose=args.simulate)
    daemon = Daemon(cfg, ctrl)
    if cfg["sources"]["teams"]:
        try:
            daemon.teams = _teams_source(cfg, lambda ev: None)
        except TeamsError as exc:
            print(f"Teams désactivé : {exc}", file=sys.stderr)
    try:
        asyncio.run(daemon.run())
    except RuntimeError as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 1
    return 0


def _teams_auth(cfg):
    from .teams.auth import Auth, TokenStore
    t = cfg["teams"]
    return Auth(t["client_id"], t["tenant"], TokenStore(cfgmod.teams_token_path()))


def _teams_source(cfg, handle):
    from .teams.source import TeamsSource
    auth = _teams_auth(cfg)
    if auth.store.load() is None:
        raise TeamsError("non connecté : lancer `ambient-light teams-login`")
    return TeamsSource(cfg["teams"], auth, handle)


def cmd_teams_login(args) -> int:
    try:
        _teams_auth(_cfg(args)).login()
    except TeamsError as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 1
    print("connecté (jeton stocké localement, permissions 0600)")
    return 0


def cmd_teams_logout(args) -> int:
    from .teams.auth import TokenStore
    print("jeton supprimé" if TokenStore(cfgmod.teams_token_path()).delete() else "aucun jeton")
    return 0


def cmd_teams_check(args) -> int:
    """Un appel réel à Graph : affiche uniquement des états, jamais de contenu."""
    from .teams.source import CHATS_URL, GRAPH, is_in_call
    cfg = _cfg(args)
    try:
        src = _teams_source(cfg, lambda ev: None)
        presence = src._call(f"{GRAPH}/me/presence")
        print(f"presence.activity = {presence.get('activity')} "
              f"-> appel/réunion : {is_in_call(presence, cfg['teams']['meeting_counts_as_call'])}")
        if cfg["teams"]["messages"]:
            print(f"chats lisibles : {len(src._call(CHATS_URL).get('value', []))}")
    except TeamsError as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_doctor(args) -> int:
    from . import install_hooks as ih
    ok = True

    def line(good, label, detail=""):
        nonlocal ok
        ok &= good
        print(f"[{'OK' if good else 'KO'}] {label}{(' — ' + detail) if detail else ''}")
    try:
        cfg = _cfg(args)
        line(True, "configuration", cfg["light"]["controller"])
    except ConfigError as exc:
        line(False, "configuration", str(exc))
        return 1
    import importlib.util
    if cfg["light"]["controller"] == "hueble":
        line(importlib.util.find_spec("HueBLE") is not None, "HueBLE installé")
    try:
        text = ih.settings_path().read_text(encoding="utf-8")
        missing = [e for e in ih.EVENTS if ih.MARKER not in json.dumps(json.loads(text).get("hooks", {}).get(e, []))]
        line(not missing, "hooks Claude Code", f"manquants : {missing}" if missing else "")
    except (OSError, ValueError):
        line(False, "hooks Claude Code", "settings.json absent/illisible (install-hooks)")
    st = send({"cmd": "status"}, timeout=1)
    line(st is not None, "daemon", "" if st is None else f"ampoule {st['link']}, teams {st.get('teams')}")
    if cfg["sources"]["teams"]:
        from .teams.auth import TokenStore
        line(bool(cfg["teams"]["client_id"]), "teams.client_id")
        line(TokenStore(cfgmod.teams_token_path()).load() is not None, "jeton Teams")
    return 0 if ok else 1


def cmd_check_config(args) -> int:
    cfg = _cfg(args)
    print(f"configuration valide ({args.config or cfgmod.default_config_path()})")
    print(f"contrôleur : {cfg['light']['controller']}")
    return 0


def cmd_scan(args) -> int:
    from .controllers.base import ControllerError
    from .controllers.hueble import discover
    try:
        found = asyncio.run(discover(args.timeout))
    except ControllerError as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 1
    if not found:
        print("aucune ampoule Hue détectée")
        return 1
    for addr, name in found:
        print(f"{addr}  {name}")
    return 0


def cmd_color(args) -> int:
    """Test direct d'une couleur sur l'ampoule (sans daemon)."""
    from .controllers import create
    from .controllers.base import ControllerError
    from .state import LightState
    cfg = _cfg(args)
    rgb = cfgmod.parse_color(args.color)

    async def go():
        ctrl = create(cfg, verbose=True)
        await ctrl.connect()
        try:
            await ctrl.apply(LightState(rgb, cfg["light"]["brightness"], "test"))
            await asyncio.sleep(args.hold)
        finally:
            await ctrl.disconnect()
    try:
        asyncio.run(go())
    except ControllerError as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 1
    return 0


def _daemon_call(msg) -> int:
    reply = send(msg, timeout=2)
    if reply is None:
        print("daemon injoignable (lancer : ambient-light run)", file=sys.stderr)
        return 1
    print(json.dumps(reply, indent=2))
    return 0 if reply.get("ok") else 1


def cmd_simulate(args) -> int:
    return _daemon_call({"cmd": "sim", "source": args.source, "type": args.event})


def cmd_status(args) -> int:
    return _daemon_call({"cmd": "status"})


def cmd_ack(args) -> int:
    return _daemon_call({"cmd": "ack"})


def cmd_stop(args) -> int:
    return _daemon_call({"cmd": "quit"})


def cmd_install_hooks(args) -> int:
    from . import install_hooks as ih
    evs = ih.install()
    print(f"hooks installés dans {ih.settings_path()} : {', '.join(evs)}")
    return 0


def cmd_uninstall_hooks(args) -> int:
    from . import install_hooks as ih
    print(f"{ih.uninstall()} entrée(s) retirée(s)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ambient-light")
    p.add_argument("--config", help="chemin du fichier TOML")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("run", help="démarrer le daemon")
    s.add_argument("--simulate", action="store_true", help="sans ampoule réelle")
    s.set_defaults(fn=cmd_run)
    sub.add_parser("check-config").set_defaults(fn=cmd_check_config)
    s = sub.add_parser("scan", help="détecter les ampoules Hue BLE")
    s.add_argument("--timeout", type=int, default=10)
    s.set_defaults(fn=cmd_scan)
    s = sub.add_parser("color", help="tester une couleur (#RRGGBB)")
    s.add_argument("color")
    s.add_argument("--hold", type=float, default=3)
    s.set_defaults(fn=cmd_color)
    s = sub.add_parser("simulate", help="injecter un événement dans le daemon")
    s.add_argument("event", choices=sorted(EVENT_TYPES))
    s.add_argument("--source", default="claude")
    s.set_defaults(fn=cmd_simulate)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("ack", help="acquitter tous les événements").set_defaults(fn=cmd_ack)
    sub.add_parser("stop", help="arrêter le daemon").set_defaults(fn=cmd_stop)
    sub.add_parser("teams-login", help="connexion Teams (device code)").set_defaults(fn=cmd_teams_login)
    sub.add_parser("teams-logout").set_defaults(fn=cmd_teams_logout)
    sub.add_parser("teams-check", help="test réel de Graph (sans contenu)").set_defaults(fn=cmd_teams_check)
    sub.add_parser("doctor", help="santé des intégrations").set_defaults(fn=cmd_doctor)
    sub.add_parser("install-hooks").set_defaults(fn=cmd_install_hooks)
    sub.add_parser("uninstall-hooks").set_defaults(fn=cmd_uninstall_hooks)
    return p


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["hook"]:  # chemin rapide, sans argparse
        from .hook import run
        return run()
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except ConfigError as exc:
        print(f"configuration invalide : {exc}", file=sys.stderr)
        return 2
