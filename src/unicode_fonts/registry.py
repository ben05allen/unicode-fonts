"""Typed metadata for the glyph tables in :mod:`unicode_fonts.fonts`.

Every table in ``fonts_dict`` is a 95 character string aligned to the same
printable ASCII alphabet.  Note that the alphabet is *not* in codepoint order
(``"`` and ``\\`` are hoisted to the front), so maps are always built with
``zip`` and never by indexing with :func:`ord`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import cache

from .fonts import fonts_dict

#: The reference alphabet: 95 printable ASCII characters, in table order.
BASE_ALPHABET: str = fonts_dict["normal"]


class Family(StrEnum):
    SERIF = "serif"
    SANS = "sans"
    MONO = "monospace"
    SCRIPT = "script"
    FRAKTUR = "fraktur"
    DOUBLE_STRUCK = "double-struck"
    DECORATIVE = "decorative"


class Weight(StrEnum):
    NORMAL = "normal"
    BOLD = "bold"


class Slant(StrEnum):
    ROMAN = "roman"
    ITALIC = "italic"


@dataclass(frozen=True, slots=True)
class FontSpec:
    """One entry of ``fonts_dict`` described along the (family, weight, slant) axes."""

    name: str
    family: Family
    weight: Weight
    slant: Slant
    lossless: bool
    has_axes: bool

    @property
    def request(self) -> str:
        """Human readable weight/slant description, e.g. ``"bold italic"``."""
        if self.weight == Weight.BOLD and self.slant == Slant.ITALIC:
            return "bold italic"
        if self.weight == Weight.BOLD:
            return "bold"
        if self.slant == Slant.ITALIC:
            return "italic"
        return "regular"


# Fonts that participate in the weight/slant matrix.  Everything else is a
# self-contained decorative alphabet that cannot be combined with bold/italic.
_AXES: dict[str, tuple[Family, Weight, Slant]] = {
    # Unicode treats plain ASCII as the serif regular alphabet, so "normal"
    # is the identity member of the serif family.
    "normal": (Family.SERIF, Weight.NORMAL, Slant.ROMAN),
    "serifBold": (Family.SERIF, Weight.BOLD, Slant.ROMAN),
    "serifItalic": (Family.SERIF, Weight.NORMAL, Slant.ITALIC),
    "serifBoldItalic": (Family.SERIF, Weight.BOLD, Slant.ITALIC),
    "sans": (Family.SANS, Weight.NORMAL, Slant.ROMAN),
    "sansBold": (Family.SANS, Weight.BOLD, Slant.ROMAN),
    "sansItalic": (Family.SANS, Weight.NORMAL, Slant.ITALIC),
    "sansBoldItalic": (Family.SANS, Weight.BOLD, Slant.ITALIC),
    # Unicode ships no bold or italic monospace alphabet.
    "monospace": (Family.MONO, Weight.NORMAL, Slant.ROMAN),
    "script": (Family.SCRIPT, Weight.NORMAL, Slant.ROMAN),
    "boldScript": (Family.SCRIPT, Weight.BOLD, Slant.ROMAN),
    "fraktur": (Family.FRAKTUR, Weight.NORMAL, Slant.ROMAN),
    "boldFraktur": (Family.FRAKTUR, Weight.BOLD, Slant.ROMAN),
    "doubleStruck": (Family.DOUBLE_STRUCK, Weight.NORMAL, Slant.ROMAN),
}

_DECORATIVE: dict[str, str] = {
    "circled": "circled letters and digits",
    "circledNegative": "negative (filled) circled letters - loses case",
    "squared": "squared letters - loses case",
    "squaredNegative": "negative (filled) squared letters - loses case",
    "parenthesized": "parenthesised letters - loses case",
    "smallCaps": "lowercase rendered as small capitals",
    "subscript": "subscript letters and digits - approximate",
    "superscript": "superscript letters and digits - approximate",
    "fullwidth": "fullwidth CJK forms",
    "inverted": "upside-down lookalikes",
    "mirrored": "mirrored lookalikes",
    "rotatedLeft": "quarter-turn lookalikes",
    "rotatedRight": "quarter-turn lookalikes",
}

WHITESPACE: frozenset[str] = frozenset(" \t\n\r\f\v")

#: ``name -> {input char: output char}`` for every table.
#:
#: Whitespace is deliberately left untranslated.  The ``monospace`` table maps
#: space to U+2002 EN SPACE and ``fullwidth`` to U+3000, both invisible and
#: hostile to search, diffing and word wrap, so the space key is dropped.
CHAR_MAPS: dict[str, dict[str, str]] = {
    name: {
        char: glyph
        for char, glyph in zip(BASE_ALPHABET, glyphs, strict=True)
        if char not in WHITESPACE
    }
    for name, glyphs in fonts_dict.items()
}


def _build_specs() -> dict[str, FontSpec]:
    specs: dict[str, FontSpec] = {}
    for name in fonts_dict:
        chars = CHAR_MAPS[name]
        # A table is lossless when it is injective: distinct input characters
        # never collapse onto the same output glyph (case-destroying tables
        # such as "squared" map both "B" and "b" to the same boxed letter).
        lossless = len(set(chars.values())) == len(chars)
        if name in _AXES:
            family, weight, slant = _AXES[name]
            specs[name] = FontSpec(name, family, weight, slant, lossless, True)
        else:
            specs[name] = FontSpec(
                name, Family.DECORATIVE, Weight.NORMAL, Slant.ROMAN, lossless, False
            )
    return specs


#: Metadata for every font, keyed by its canonical name.
FONTS: dict[str, FontSpec] = _build_specs()

#: ``(family, weight, slant) -> font name`` for every representable combination.
AXIS_TABLE: dict[tuple[Family, Weight, Slant], str] = {
    (spec.family, spec.weight, spec.slant): spec.name
    for spec in FONTS.values()
    if spec.has_axes
}

#: Families that can be combined with bold/italic markup.
FAMILIES: tuple[Family, ...] = tuple(
    dict.fromkeys(spec.family for spec in FONTS.values() if spec.has_axes)
)

_FAMILY_ALIASES: dict[str, Family] = {
    "sans": Family.SANS,
    "sans-serif": Family.SANS,
    "sansserif": Family.SANS,
    "serif": Family.SERIF,
    "mono": Family.MONO,
    "monospace": Family.MONO,
    "script": Family.SCRIPT,
    "fraktur": Family.FRAKTUR,
    "double-struck": Family.DOUBLE_STRUCK,
    "doublestruck": Family.DOUBLE_STRUCK,
    "blackboard": Family.DOUBLE_STRUCK,
}

_FONT_ALIASES: dict[str, str] = {
    **{name.casefold(): name for name in FONTS},
    "sansserif": "sans",
    "mono": "monospace",
    "doublestruck": "doubleStruck",
    "blackboard": "doubleStruck",
}


def squash(raw: str) -> str:
    """Normalise a font name for matching: ``"Bold-Script" -> "boldscript"``."""
    return "".join(ch for ch in raw.casefold() if ch.isalnum())


def coerce_family(raw: str | Family) -> Family:
    """Resolve a user supplied family name, raising :class:`ValueError` if unknown."""
    if isinstance(raw, Family):
        return raw
    family = _FAMILY_ALIASES.get(raw.strip().casefold())
    if family is None:
        valid = ", ".join(sorted({alias for alias in _FAMILY_ALIASES}))
        raise ValueError(f"unknown family {raw!r}; choose from: {valid}")
    return family


def coerce_font(raw: str | FontSpec) -> str:
    """Resolve a user supplied font name to its canonical form."""
    if isinstance(raw, FontSpec):
        return raw.name
    key = raw.strip()
    name = FONTS[key].name if key in FONTS else _FONT_ALIASES.get(squash(key))
    if name is None:
        raise ValueError(
            f"unknown font {raw!r}; choose from: {', '.join(sorted(FONTS))}"
        )
    return name


def resolve_axes(
    family: Family, weight: Weight, slant: Slant
) -> tuple[str, tuple[str, ...]]:
    """Find the closest available font for a requested weight/slant.

    Returns the font name and the attributes that had to be dropped.  Family is
    always preserved: it carries the most visual identity, so ``bold`` in the
    monospace family degrades to plain ``monospace`` rather than to a bold
    sans-serif.
    """
    # StrEnum members compare equal to their values, so use equality rather
    # than identity throughout.
    attempts: list[tuple[Weight, Slant]] = [(weight, slant)]
    if slant != Slant.ROMAN:
        attempts.append((weight, Slant.ROMAN))
    if weight != Weight.NORMAL:
        attempts.append((Weight.NORMAL, slant))
    attempts.append((Weight.NORMAL, Slant.ROMAN))

    for candidate_weight, candidate_slant in attempts:
        name = AXIS_TABLE.get((family, candidate_weight, candidate_slant))
        if name is not None:
            dropped: list[str] = []
            if candidate_weight != weight:
                dropped.append("bold")
            if candidate_slant != slant:
                dropped.append("italic")
            return name, tuple(dropped)

    raise ValueError(f"family {family} has no regular alphabet")


@cache
def colliding_pairs(font: str) -> dict[str, str]:
    """Map each character whose glyph is shared with another input to that partner.

    ``colliding_pairs("squared")["H"] == "h"``: a boxed capital H and a boxed
    lowercase h are the same glyph, so case cannot be recovered.
    """
    partners: dict[str, list[str]] = {}
    for char, glyph in CHAR_MAPS[font].items():
        partners.setdefault(glyph, []).append(char)
    pairs: dict[str, str] = {}
    for chars in partners.values():
        if len(chars) > 1:
            for char in chars:
                pairs[char] = next(c for c in chars if c != char)
    return pairs


def ambiguous_chars(font: str, text: str) -> list[tuple[str, str]]:
    """Return the ``(char, partner)`` pairs ``font`` cannot tell apart in ``text``.

    A single ``"H"`` is enough to flag the font: the output glyph would be
    identical to the one produced for ``"h"``, so the case is not recoverable.
    """
    pairs = colliding_pairs(font)
    seen: dict[str, str] = {}
    for char in text:
        partner = pairs.get(char)
        if partner is not None and char not in seen:
            seen[char] = partner
    return list(seen.items())


def loses_information(font: str, text: str) -> bool:
    """True when ``font`` cannot distinguish some characters of ``text``."""
    return bool(ambiguous_chars(font, text))


def sample(font: str, text: str = "Aa1") -> str:
    """Render ``text`` with ``font``, for docs and ``--list-fonts``."""
    chars = CHAR_MAPS[font]
    return "".join(chars.get(ch, ch) for ch in text)
