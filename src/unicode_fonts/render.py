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
    loses_information,
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
    return _walk(result.nodes, style, (current,), context)


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
    fonts: tuple[str, ...],
    context: _Context,
) -> str:
    pieces: list[str] = []
    for node in nodes:
        if isinstance(node, Text):
            pieces.append(_render_text(node, fonts, context))
            continue
        child = _merge(style, node)
        child_font = _font_for(child, context, node.offset)
        body = _walk(node.children, child, (*fonts, child_font), context)
        # Decorations are applied to the finished span rather than per text
        # run, so that a nested span in the middle of the text cannot break the
        # continuity of the line.
        pieces.append(_decorate(body, _marks_added(style, child)))
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
    fonts: tuple[str, ...],
    context: _Context,
) -> str:
    value = node.value
    font = fonts[-1]
    if not context.allow_lossy:
        ambiguous = ambiguous_chars(font, value)
        if ambiguous:
            char, partner = ambiguous[0]
            context.warn(
                f"{font!r} cannot distinguish {char!r} from {partner!r}; "
                f"leaving text unstyled (override with allow_lossy=True "
                f"or --allow-lossy)",
                node.offset,
            )
            font = _lossless_ancestor(fonts, value)

    chars = CHAR_MAPS[font]
    return "".join(chars.get(char, char) for char in value)


def _lossless_ancestor(fonts: tuple[str, ...], value: str) -> str:
    """Nearest enclosing font that can still tell ``value``'s characters apart.

    Falling back to the immediate parent is not enough: the parent may be a
    case-destroying font too, which would style the text anyway while claiming
    to leave it alone.  ``fonts`` is ordered outermost first, so walk it
    backwards and stop at the first font that keeps ``value`` readable.
    """
    for candidate in reversed(fonts):
        if not loses_information(candidate, value):
            return candidate
    return "normal"


def _marks_added(outer: _Style, inner: _Style) -> str:
    """Decorations this span introduces, in a fixed order."""
    marks = ""
    if inner.underline and not outer.underline:
        marks += UNDERLINE
    if inner.strike and not outer.strike:
        marks += STRIKE
    return marks


def _decorate(text: str, marks: str) -> str:
    """Attach ``marks`` to ``text``, from the first to the last visible character.

    Interior spaces are marked so a strikethrough reads as one continuous line;
    leading and trailing whitespace is left bare so no mark floats unanchored,
    and tabs or newlines are never marked because a combining mark after one
    lands at the start of the following line.
    """
    if not marks or not text:
        return text

    visible = [index for index, char in enumerate(text) if not char.isspace()]
    if not visible:
        return text
    first, last = visible[0], visible[-1]

    out: list[str] = []
    for index, char in enumerate(text):
        out.append(char)
        if not first <= index <= last:
            continue
        if char.isspace() and char != " ":
            continue
        if unicodedata.combining(char):
            continue
        out.append(marks)
    return "".join(out)


__all__ = ["UnicodeFontsWarning", "render"]
