"""Turn parsed markup into Unicode text."""

from __future__ import annotations

import unicodedata
import warnings
from dataclasses import dataclass, replace

from .parser import Node, Span, Text, parse
from .registry import (
    CHAR_MAPS,
    FONTS,
    Family,
    Slant,
    Weight,
    ambiguous_chars,
    coerce_family,
    coerce_font,
    resolve_axes,
)

#: Combining marks used for the two decorations Unicode has no alphabet for.
UNDERLINE = "\u0332"  # COMBINING LOW LINE
STRIKE = "\u0336"  # COMBINING LONG STROKE OVERLAY


class UnicodeFontsWarning(UserWarning):
    """A style that could not be represented exactly, resolved to a substitute."""


def render(
    text: str,
    *,
    family: str | Family = Family.SANS,
    font: str | None = None,
    allow_lossy: bool = False,
) -> str:
    """Render Markdown-subset ``text`` as styled Unicode.

    Args:
        text: Source document.
        family: Family that ``**bold**``/``*italic*`` resolve against.  Only
            governs marked spans; unmarked text stays byte-identical ASCII.
        font: Style the whole document with one font, bypassing ``family``.
            Explicitly naming a font opts into its quirks, including the
            case-destroying tables.
        allow_lossy: Permit fonts that cannot distinguish some characters
            (see :data:`~unicode_fonts.registry.FONTS`), e.g. ``squared``,
            where ``"H"`` and ``"h"`` share a glyph.
    """
    resolved_family = coerce_family(family)
    if font is not None:
        root_font = coerce_font(font)
        style = _Style(font=root_font, locked=True)
    else:
        root_font = "normal"
        style = _Style()

    result = parse(text)
    context = _Context(text, resolved_family, allow_lossy or font is not None)
    for issue in result.issues:
        context.warn(issue.message, issue.offset)

    current = _font_for(style, context, 0)
    return _walk(result.nodes, style, current, current, context)


@dataclass(frozen=True, slots=True)
class _Style:
    """Attributes accumulated from the enclosing spans."""

    font: str = "normal"
    weight: Weight = Weight.NORMAL
    slant: Slant = Slant.ROMAN
    strike: bool = False
    underline: bool = False
    #: True when ``font`` came from an explicit directive or ``font=`` argument,
    #: which makes that font's family the one weight/slant resolve against.
    locked: bool = False


class _Context:
    """Per-render state: where warnings point and what was already reported."""

    def __init__(self, source: str, family: Family, allow_lossy: bool) -> None:
        self.source = source
        self.family = family
        self.allow_lossy = allow_lossy
        self.reported: set[str] = set()

    def warn(self, message: str, offset: int) -> None:
        location = self.locate(offset)
        full = f"{location}: {message}"
        if full in self.reported:
            return
        self.reported.add(full)
        warnings.warn(UnicodeFontsWarning(full), stacklevel=3)

    def locate(self, offset: int) -> str:
        line = self.source.count("\n", 0, offset) + 1
        line_start = self.source.rfind("\n", 0, offset) + 1
        return f"line {line}, col {offset - line_start + 1}"


def _walk(
    nodes: list[Node],
    style: _Style,
    font: str,
    parent_font: str,
    context: _Context,
) -> str:
    pieces: list[str] = []
    for node in nodes:
        if isinstance(node, Text):
            pieces.append(_render_text(node, style, font, parent_font, context))
            continue
        child = _merge(style, node)
        child_font = _font_for(child, context, node.offset)
        pieces.append(_walk(node.children, child, child_font, font, context))
    return "".join(pieces)


def _merge(style: _Style, span: Span) -> _Style:
    changes: dict[str, object] = {}
    attrs = span.attrs
    if "font" in attrs:
        changes["font"] = attrs["font"]
        changes["locked"] = True
    if "weight" in attrs:
        changes["weight"] = Weight(attrs["weight"])
    if "slant" in attrs:
        changes["slant"] = Slant(attrs["slant"])
    if "strike" in attrs:
        changes["strike"] = True
    if "underline" in attrs:
        changes["underline"] = True
    return replace(style, **changes) if changes else style


def _font_for(style: _Style, context: _Context, offset: int) -> str:
    """Pick the concrete font for a style, warning about any compromise."""
    spec = FONTS[style.font]
    if style.weight == Weight.NORMAL and style.slant == Slant.ROMAN:
        return style.font

    requested = _describe(style.weight, style.slant)
    if not spec.has_axes:
        context.warn(
            f"{requested} is not available in {spec.name!r}; text stays as is",
            offset,
        )
        return style.font

    family = spec.family if style.locked else context.family
    font, dropped = resolve_axes(family, style.weight, style.slant)
    if dropped:
        context.warn(
            f"{requested} is not available in the {family} family; "
            f"using {font!r} ({', '.join(dropped)} dropped)",
            offset,
        )
    return font


def _describe(weight: Weight, slant: Slant) -> str:
    if weight == Weight.BOLD and slant == Slant.ITALIC:
        return "bold italic"
    return "italic" if slant == Slant.ITALIC else "bold"


def _render_text(
    node: Text,
    style: _Style,
    font: str,
    parent_font: str,
    context: _Context,
) -> str:
    value = node.value
    if not context.allow_lossy:
        ambiguous = ambiguous_chars(font, value)
        if ambiguous:
            char, partner = ambiguous[0]
            context.warn(
                f"{font!r} cannot distinguish {char!r} from {partner!r}; "
                f"leaving text unstyled (use --allow-lossy to override)",
                node.offset,
            )
            font = parent_font

    chars = CHAR_MAPS[font]
    marks = _marks(style)
    out: list[str] = []
    for char in value:
        out.append(chars.get(char, char))
        if marks and not char.isspace() and not unicodedata.combining(char):
            out.append(marks)
    return "".join(out)


def _marks(style: _Style) -> str:
    marks = ""
    if style.underline:
        marks += UNDERLINE
    if style.strike:
        marks += STRIKE
    return marks


__all__ = ["UnicodeFontsWarning", "render"]
