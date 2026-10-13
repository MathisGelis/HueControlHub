"""Configuration : valeurs par défaut + surcharge par un fichier TOML."""
from __future__ import annotations

import copy
import os
import tomllib
from pathlib import Path

# duration : secondes ; 0 = persistant jusqu'à résolution/acquittement.
DEFAULTS: dict = {
    "light": {
        "controller": "fake",  # "fake" (simulation) ou "hueble"
        "address": "",  # adresse BLE ; vide = découverte automatique
        "neutral_color": "off",  # "off" ou "#RRGGBB"
        "brightness": 254,
        "min_write_interval": 0.3,  # secondes entre deux écritures sur l'ampoule
        "on_disconnect": "retry",  # retry | ignore
        "reconnect_max_delay": 60,
    },
    "sources": {"claude": True, "teams": False},
    "events": {
        "permission_required": {"color": "#FF0000", "priority": 100, "duration": 0},
        "call_incoming": {"color": "#FF0000", "priority": 90, "duration": 0},
        "call_ongoing": {"color": "#0000FF", "priority": 70, "duration": 0},
        "input_required": {"color": "#FF0000", "priority": 60, "duration": 0},
        "task_error": {"color": "#FF00FF", "priority": 55, "duration": 10},
        "message_received": {"color": "#FF6A00", "priority": 50, "duration": 5},
        "task_completed": {"color": "#00FF00", "priority": 40, "duration": 3},
    },
}

EVENT_TYPES = frozenset(DEFAULTS["events"])


class ConfigError(ValueError):
    pass


def runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or os.environ.get("TMPDIR") or "/tmp"
    path = Path(base) / f"ambient-light-{os.getuid()}"
    path.mkdir(mode=0o700, exist_ok=True)
    return path


def socket_path() -> Path:
    return runtime_dir() / "ambient.sock"


def default_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "ambient-light" / "config.toml"


def _merge(base: dict, override: dict, path: str = "") -> None:
    for key, value in override.items():
        if key not in base:
            raise ConfigError(f"clé inconnue : {path}{key}")
        if isinstance(base[key], dict):
            if not isinstance(value, dict):
                raise ConfigError(f"{path}{key} doit être une table")
            _merge(base[key], value, f"{path}{key}.")
        else:
            if type(value) is not type(base[key]) and not (
                isinstance(base[key], (int, float)) and isinstance(value, (int, float))
                and not isinstance(value, bool)
            ):
                raise ConfigError(f"{path}{key} : type invalide ({type(value).__name__})")
            base[key] = value


def parse_color(value: str) -> tuple[int, int, int] | None:
    """'#RRGGBB' -> (r, g, b) ; 'off' -> None."""
    if value.lower() == "off":
        return None
    v = value.lstrip("#")
    if len(v) != 6:
        raise ConfigError(f"couleur invalide : {value!r}")
    try:
        return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
    except ValueError:
        raise ConfigError(f"couleur invalide : {value!r}") from None


def validate(cfg: dict) -> None:
    light = cfg["light"]
    if light["controller"] not in ("fake", "hueble"):
        raise ConfigError("light.controller : 'fake' ou 'hueble'")
    if light["on_disconnect"] not in ("retry", "ignore"):
        raise ConfigError("light.on_disconnect : 'retry' ou 'ignore'")
    if not 1 <= light["brightness"] <= 254:
        raise ConfigError("light.brightness : 1..254")
    parse_color(light["neutral_color"])
    for name, rule in cfg["events"].items():
        if parse_color(rule["color"]) is None:
            raise ConfigError(f"events.{name}.color ne peut pas être 'off'")
        if rule["duration"] < 0:
            raise ConfigError(f"events.{name}.duration doit être >= 0")


def load(path: Path | None = None) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    path = path or default_config_path()
    if path.exists():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{path} : {exc}") from exc
        _merge(cfg, data)
    validate(cfg)
    return cfg
