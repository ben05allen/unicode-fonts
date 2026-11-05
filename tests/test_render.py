"""Tests for parsing and rendering."""

from __future__ import annotations

import pytest

from unicode_fonts import UnicodeFontsWarning, render
from unicode_fonts.parser import Span, Text, parse
from unicode_fonts.registry import sample

# --- helpers ---------------------------------------------------------------


def plus_marks(text: str, *marks: str) -> str:
    """Append ``marks`` to every non-space character of ``text``."""
    suffix = "".join(marks)
    return "".join(char if char.isspace() else char + suffix for char in text)


# --- parsing ---------------------------------------------------------------


def test_plain_text_is_a_single_node() -> None:
    result = parse("hello")
    assert result.issues == []
    assert result.nodes == [Text("hello", 0)]


def test_bold_becomes_a_span() -> None:
    result = parse("**hi**")
    assert len(result.nodes) == 1
    node = result.nodes[0]
    assert isinstance(node, Span)
    assert node.attrs == {"weight": "bold"}
    assert node.children == [Text("hi", 2)]


def test_nesting_produces_nested_spans() -> None:
    result = parse("**a *b* c**")
    outer = result.nodes[0]
    assert isinstance(outer, Span)
    inner = [node for node in outer.children if isinstance(node, Span)]
    assert inner[0].attrs == {"slant": "italic"}


def test_unclosed_marker_stays_literal() -> None:
    assert parse("a **b").nodes == [Text("a ", 0), Text("**", 2), Text("b", 4)]


def test_escapes_suppress_markup() -> None:
    assert parse(r"\*x\*").nodes == [Text("*x*", 0)]


def test_code_spans_are_verbatim() -> None:
    result = parse("`**x**`")
    node = result.nodes[0]
    assert isinstance(node, Span)
    assert node.attrs == {"font": "monospace"}
    assert node.children == [Text("**x**", 1)]


def test_directive_sets_a_font() -> None:
    result = parse("{{circled}}ok{{/circled}}")
    node = result.nodes[0]
    assert isinstance(node, Span)
    assert node.attrs == {"font": "circled"}
    assert node.children == [Text("ok", 11)]


def test_unknown_font_is_reported_once() -> None:
    result = parse("{{nope}}x{{/nope}}")
    assert len(result.issues) == 1
    assert "unknown font" in result.issues[0].message


def test_unclosed_directive_is_reported() -> None:
    result = parse("{{circled}}x")
    assert len(result.issues) == 1
    assert "unclosed directive" in result.issues[0].message


# --- rendering: baseline ---------------------------------------------------


def test_unmarked_document_is_byte_identical() -> None:
    source = "Hello, world! 100% ~ascii~ \\ {braces} [brackets] 3 * 4\n\nNew ¶?"
    assert render(source) == source


def test_default_family_is_sans() -> None:
    assert render("**bold**") == "𝗯𝗼𝗹𝗱"
    assert render("*italic*") == "𝘪𝘵𝘢𝘭𝘪𝘤"
    assert render("***both***") == "𝙗𝙤𝙩𝙝"


def test_serif_family_switch() -> None:
    assert render("**bold**", family="serif") == "𝐛𝐨𝐥𝐝"
    assert render("*italic*", family="serif") == "𝑖𝑡𝑎𝑙𝑖𝑐"
    assert render("***both***", family="serif") == "𝒃𝒐𝒕𝒉"


def test_bold_inside_italic_composes() -> None:
    assert render("*a **b** c*") == "𝘢 𝙗 𝘤"


def test_code_span_uses_monospace() -> None:
    assert render("`code`") == "𝚌𝚘𝚍𝚎"


def test_bold_code_degrades_to_monospace_with_a_warning() -> None:
    with pytest.warns(UnicodeFontsWarning, match="bold is not available"):
        assert render("**`x`**") == "𝚡"


def test_monospace_family_drops_bold_and_italic() -> None:
    with pytest.warns(UnicodeFontsWarning) as record:
        assert render("**bold** *italic*", family="mono") == "𝚋𝚘𝚕𝚍 𝚒𝚝𝚊𝚕𝚒𝚌"
    assert len(record) == 2


def test_warnings_point_at_the_offending_line() -> None:
    # The bold wrapper starts at column 1, the code span that cannot be bold
    # at column 3; the warning points at the span that caused the compromise.
    with pytest.warns(UnicodeFontsWarning, match=r"line 2, col 3"):
        render("ok\n**`x`**")


# --- rendering: decorations ------------------------------------------------


def test_strike_uses_combining_marks() -> None:
    assert render("~~gone~~") == plus_marks("gone", "\u0336")


def test_underline_uses_combining_marks() -> None:
    assert render("__gone__") == plus_marks("gone", "\u0332")


def test_underline_and_strike_stack() -> None:
    assert render("~~__x__~~") == "x\u0332\u0336"


def test_decorations_compose_with_fonts() -> None:
    assert render("~~**x**~~") == sample("sansBold", "x") + "\u0336"


# --- rendering: fonts ------------------------------------------------------


def test_directive_selects_a_decorative_font() -> None:
    assert render("{{circled}}VIP{{/circled}}") == "ⓋⒾⓅ"
    assert render("{{script}}Dear{{/script}}") == "𝒟ℯ𝒶𝓇"


def test_directive_scopes_the_font() -> None:
    assert render("a {{circled}}b{{/circled}} c") == "a ⓑ c"


def test_weight_resolves_inside_the_locked_family() -> None:
    assert render("{{script}}**x**{{/script}}") == "𝔁"


def test_bold_inside_decorative_font_warns_and_keeps_the_font() -> None:
    with pytest.warns(UnicodeFontsWarning, match="not available in 'circled'"):
        assert render("{{circled}}**VIP**{{/circled}}") == "ⓋⒾⓅ"


def test_whole_document_font() -> None:
    assert render("Hello", font="fullwidth") == "Ｈｅｌｌｏ"
    assert render("Hello", font="smallCaps") == "Hᴇʟʟᴏ"


def test_whitespace_is_never_restyled() -> None:
    # "monospace" maps space to U+2002 in the source table; we skip it.
    assert render("a b", font="monospace") == "𝚊 𝚋"
    assert " " in render("a b", font="fullwidth")


# --- rendering: lossy fonts ------------------------------------------------


def test_lossy_font_is_refused_when_case_would_be_lost() -> None:
    with pytest.warns(UnicodeFontsWarning, match="cannot distinguish"):
        assert render("{{squared}}Box{{/squared}}") == "Box"


def test_lossy_font_is_allowed_on_unambiguous_text() -> None:
    assert render("{{squared}}123{{/squared}}") == "123"


def test_allow_lossy_permits_the_damage() -> None:
    assert render("{{squared}}Box{{/squared}}", allow_lossy=True) == "🄱🄾🅇"


def test_explicit_font_opts_into_lossiness() -> None:
    assert render("Box", font="squared") == "🄱🄾🅇"


# --- rendering: passthrough ------------------------------------------------


def test_non_ascii_is_never_touched() -> None:
    assert render("**café ☕ 日本**") == "𝗰𝗮𝗳é ☕ 日本"


def test_already_styled_text_is_not_double_styled() -> None:
    assert render("**𝗯𝗼𝗹𝗱**") == "𝗯𝗼𝗹𝗱"


def test_newlines_and_blank_lines_survive() -> None:
    assert render("**a**\n\n**b**") == "𝗮\n\n𝗯"


@pytest.mark.parametrize(
    "source",
    [
        "plain",
        "**bold**",
        "*italic*",
        "***both***",
        "~~strike~~",
        "{{circled}}x{{/circled}}",
    ],
)
def test_output_is_stable_under_a_second_pass(source: str) -> None:
    # Styled output contains no markup, so rendering it again is a no-op even
    # though the glyphs themselves are no longer ASCII.
    once = render(source)
    assert render(once) == once
