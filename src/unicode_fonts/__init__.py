"""Unicode text formatting for plain-text-only platforms."""

from __future__ import annotations

from .registry import FONTS, Family, FontSpec, Slant, Weight
from .render import UnicodeFontsWarning, render

__version__ = "0.1.0"

__all__ = [
    "FONTS",
    "Family",
    "FontSpec",
    "Slant",
    "UnicodeFontsWarning",
    "Weight",
    "__version__",
    "render",
]
