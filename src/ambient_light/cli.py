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
    try:
        asyncio.run(Daemon(cfg, ctrl).run())
    except RuntimeError as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 1
    return 0


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
