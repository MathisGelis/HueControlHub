"""Contrôleur HueBLE (bibliothèque HueBLE 2.x, basée sur bleak).

NON VALIDÉ sur matériel réel à ce stade : écrit d'après le code source de
HueBLE 2.2.3 (discover_lights, HueBleLight.connect/set_power/set_brightness/
set_colour_xy/available/disconnect).
"""
from __future__ import annotations

from ..colors import rgb_to_xy
from ..state import LightState
from .base import ControllerError, HueController

_IO_TIMEOUT = 15  # secondes


def _import():
    try:
        import HueBLE
    except ImportError as exc:  # pragma: no cover
        raise ControllerError(
            "HueBLE non installé : pip install 'ambient-light[hue]'") from exc
    return HueBLE


async def discover(timeout: int = 10) -> list[tuple[str, str]]:
    """Retourne [(adresse, nom)] des ampoules Hue BLE détectées."""
    hb = _import()
    try:
        devices = await hb.discover_lights(timeout=timeout)
    except Exception as exc:
        raise ControllerError(f"scan Bluetooth impossible : {exc}") from exc
    return [(d.address, d.name or "?") for d in devices]


class HueBleController(HueController):
    def __init__(self, address: str = ""):
        self._address = address
        self._light = None

    async def _resolve(self):
        hb = _import()
        from bleak import BleakScanner
        if self._address:
            dev = await BleakScanner.find_device_by_address(self._address, timeout=10)
        else:
            found = await hb.discover_lights(timeout=10)
            dev = found[0] if found else None
        if dev is None:
            raise ControllerError("ampoule introuvable (allumée, à portée, appairée ?)")
        return hb.HueBleLight(dev)

    async def connect(self) -> None:
        try:
            if self._light is None:
                self._light = await self._resolve()
            await self._light.connect()
        except ControllerError:
            raise
        except Exception as exc:
            raise ControllerError(f"connexion échouée : {exc}") from exc

    async def disconnect(self) -> None:
        if self._light is not None:
            try:
                await self._light.disconnect()
            except Exception:
                pass

    def is_available(self) -> bool:
        return bool(self._light is not None and self._light.available)

    async def apply(self, state: LightState) -> None:
        import asyncio
        if self._light is None:
            raise ControllerError("non connecté")
        try:
            async with asyncio.timeout(_IO_TIMEOUT):
                if state.rgb is None:
                    await self._light.set_power(False)
                    return
                x, y = rgb_to_xy(state.rgb)
                await self._light.set_power(True)
                await self._light.set_brightness(state.brightness)
                await self._light.set_colour_xy(x, y)
        except Exception as exc:
            raise ControllerError(f"écriture échouée : {exc}") from exc
