"""Conversion sRGB -> CIE xy (gamut Hue, formule Philips documentée)."""
from __future__ import annotations


def _gamma(c: float) -> float:
    return ((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92


def rgb_to_xy(rgb: tuple[int, int, int]) -> tuple[float, float]:
    r, g, b = (_gamma(c / 255) for c in rgb)
    X = r * 0.664511 + g * 0.154324 + b * 0.162028
    Y = r * 0.283881 + g * 0.668433 + b * 0.047685
    Z = r * 0.000088 + g * 0.072310 + b * 0.986039
    total = X + Y + Z
    if total == 0:
        return 0.3127, 0.3290  # blanc D65
    return round(X / total, 4), round(Y / total, 4)
