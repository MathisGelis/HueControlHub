"""Interface Hue Controller, indépendante de toute bibliothèque Bluetooth."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..state import LightState


class ControllerError(Exception):
    """Toute erreur de pilotage (Bluetooth, connexion, timeout)."""


class HueController(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    async def apply(self, state: LightState) -> None:
        """Applique l'état ; lève ControllerError en cas d'échec."""
