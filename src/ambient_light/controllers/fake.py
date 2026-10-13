"""Faux contrôleur : simulation et tests, aucune écriture matérielle."""
from __future__ import annotations

import sys

from ..state import LightState
from .base import ControllerError, HueController


class FakeController(HueController):
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.connected = False
        self.applied: list[LightState] = []
        self.fail_next = 0  # nombre d'appels qui échoueront (tests)

    async def connect(self) -> None:
        if self.fail_next:
            self.fail_next -= 1
            raise ControllerError("connexion simulée en échec")
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    def is_available(self) -> bool:
        return self.connected

    async def apply(self, state: LightState) -> None:
        if not self.connected:
            raise ControllerError("non connecté")
        if self.fail_next:
            self.fail_next -= 1
            self.connected = False
            raise ControllerError("déconnexion simulée")
        self.applied.append(state)
        if self.verbose:
            print(f"[sim] lumière -> {state.reason} rgb={state.rgb}", file=sys.stderr)
