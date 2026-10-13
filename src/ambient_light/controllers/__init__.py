from .base import ControllerError, HueController
from .fake import FakeController

__all__ = ["ControllerError", "HueController", "FakeController", "create"]


def create(cfg: dict, verbose: bool = False) -> HueController:
    light = cfg["light"]
    if light["controller"] == "hueble":
        from .hueble import HueBleController
        return HueBleController(light["address"])
    return FakeController(verbose=verbose)
