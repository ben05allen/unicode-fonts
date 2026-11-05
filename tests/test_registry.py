"""Tests for the registry: table invariants and weight/slant resolution."""

from __future__ import annotations

import pytest

from unicode_fonts.fonts import fonts_dict
from unicode_fonts.registry import (
    AXIS_TABLE,
    BASE_ALPHABET,
    CHAR_MAPS,
    FAMILIES,
    FONTS,
    WHITESPACE,
    Family,
    Slant,
    Weight,
    ambiguous_chars,
    coerce_family,
    coerce_font,
    resolve_axes,
)

EXPECTED_LOSSY = {
    "circledNegative",
    "parenthesized",
    "rotatedLeft",
    "rotatedRight",
    "squared",
    "squaredNegative",
    "superscript",
}


def test_every_table_is_aligned_to_the_base_alphabet() -> None:
    assert len(fonts_dict) == 27
    for name, glyphs in fonts_dict.items():
        assert len(glyphs) == len(BASE_ALPHABET) == 95, name


def test_char_maps_drop_whitespace() -> None:
    for name, chars in CHAR_MAPS.items():
        assert not WHITESPACE & set(chars), name
        assert len(chars) == 95 - 1


def test_lossless_flags_match_the_data() -> None:
    lossy = {name for name, spec in FONTS.items() if not spec.lossless}
    assert lossy == EXPECTED_LOSSY


def test_case_destroying_fonts_collapse_upper_and_lower() -> None:
    for char, partner in ambiguous_chars("squared", "Aa"):
        assert char.lower() == partner.lower()


def test_every_font_is_reachable_from_the_axis_table_or_is_decorative() -> None:
    axis_fonts = set(AXIS_TABLE.values())
    decorative = {name for name, spec in FONTS.items() if not spec.has_axes}
    assert axis_fonts | decorative == set(fonts_dict)
    assert not axis_fonts & decorative


def test_axis_families_are_complete_or_documented() -> None:
    available = {(spec.family, spec.weight, spec.slant) for spec in FONTS.values()}
    # Presented as a table in the README; anything missing must degrade.
    assert (Family.SANS, Weight.BOLD, Slant.ITALIC) in available
    assert (Family.SERIF, Weight.BOLD, Slant.ITALIC) in available
    assert (Family.MONO, Weight.BOLD, Slant.ROMAN) not in available
    assert (Family.DOUBLE_STRUCK, Weight.BOLD, Slant.ROMAN) not in available
    assert (Family.SCRIPT, Weight.NORMAL, Slant.ITALIC) not in available


@pytest.mark.parametrize("family", FAMILIES)
def test_every_family_can_render_regular_text(family: Family) -> None:
    name, dropped = resolve_axes(family, Weight.NORMAL, Slant.ROMAN)
    assert dropped == ()
    assert FONTS[name].family is family


def test_monospace_preserves_family_and_drops_weight() -> None:
    assert resolve_axes(Family.MONO, Weight.BOLD, Slant.ROMAN) == (
        "monospace",
        ("bold",),
    )


def test_script_bold_italic_drops_only_italic() -> None:
    assert resolve_axes(Family.SCRIPT, Weight.BOLD, Slant.ITALIC) == (
        "boldScript",
        ("italic",),
    )


def test_double_struck_bold_drops_bold() -> None:
    assert resolve_axes(Family.DOUBLE_STRUCK, Weight.BOLD, Slant.ROMAN) == (
        "doubleStruck",
        ("bold",),
    )


def test_coerce_family_accepts_aliases() -> None:
    assert coerce_family("mono") is Family.MONO
    assert coerce_family("sans-serif") is Family.SANS
    assert coerce_family("SERIF") is Family.SERIF
    assert coerce_family(Family.SCRIPT) is Family.SCRIPT


def test_coerce_font_accepts_loose_spelling() -> None:
    assert coerce_font("bold-script") == "boldScript"
    assert coerce_font("BoldScript") == "boldScript"
    assert coerce_font("sans bold") == "sansBold"
    assert coerce_font("doublestruck") == "doubleStruck"


def test_coerce_rejects_unknown_names() -> None:
    with pytest.raises(ValueError, match="unknown family"):
        coerce_family("comic")
    with pytest.raises(ValueError, match="unknown font"):
        coerce_font("comic")
