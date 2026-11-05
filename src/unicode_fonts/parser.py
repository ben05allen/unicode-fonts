"""Inline parser for the Markdown-subset dialect.

The grammar is deliberately smaller than CommonMark.  A construct is only
special when it is *closed*: an unmatched ``**`` stays on the page as two
literal asterisks, which keeps ASCII art and stray punctuation safe to paste.

Supported constructs::

    **bold**        *italic*        ***bold italic***
    `code`          ~~strike~~      __underline__
    {{circled}}...{{/circled}}      \\*  (backslash escapes any ASCII punctuation)

Delimiters only ever match their own kind, so ``**a *b** c*`` does not try to
reinterpret itself the way CommonMark would: the inner ``*b`` simply loses its
partner and stays literal.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from .registry import coerce_font, squash

#: ``delimiter -> attributes it contributes``.  Longest delimiters first.
_EMPHASIS: dict[str, dict[str, str]] = {
    "***": {"weight": "bold", "slant": "italic"},
    "**": {"weight": "bold"},
    "*": {"slant": "italic"},
    "~~": {"strike": "true"},
    "__": {"underline": "true"},
}

#: Backslash escapes any ASCII punctuation character.
_ESCAPABLE: frozenset[str] = frozenset("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")

_DIRECTIVE = re.compile(r"\{\{\s*(/?)\s*([^{}\n]*?)\s*\}\}")

#: A blank line ends a paragraph, and no span may cross one.
_BLANK_LINE = re.compile(r"\n[ \t\r]*\n")

#: Code spans are rendered with this font.
CODE_FONT = "monospace"


@dataclass(slots=True)
class Text:
    """A literal run of characters."""

    value: str
    offset: int


@dataclass(slots=True)
class Span:
    """Text carrying extra attributes, e.g. ``weight=bold`` or ``font=circled``."""

    attrs: dict[str, str]
    children: list[Node]
    offset: int


Node = Text | Span


@dataclass(slots=True)
class ParseIssue:
    """A non-fatal problem found while parsing, reported as a warning."""

    offset: int
    message: str


@dataclass(slots=True)
class ParseResult:
    nodes: list[Node] = field(default_factory=list)
    issues: list[ParseIssue] = field(default_factory=list)
    #: Names already reported as crossing a paragraph break, so their dangling
    #: closing directive is not also reported as stray.
    crossed: set[str] = field(default_factory=set)


def parse(text: str) -> ParseResult:
    """Parse ``text`` into a list of nodes plus any recoverable issues."""
    result = ParseResult()
    result.nodes, _ = _parse_until(result, text, 0, len(text), None)
    return result


def _parse_until(
    result: ParseResult,
    text: str,
    i: int,
    end: int,
    closer: str | None,
) -> tuple[list[Node], int]:
    """Parse nodes from ``i`` up to ``closer``, or to ``end`` when there is none."""
    nodes: list[Node] = []
    buf: list[str] = []
    run_start = i

    while i < end:
        if closer is not None and _matches(text, i, end, closer, closing=True):
            break
        start = i
        node, i = _next_node(result, text, i, end)
        if isinstance(node, Text):
            # Escapes and unmatched delimiters are ordinary text; keeping them
            # in the same run means one node per literal stretch.
            if not buf:
                run_start = start
            buf.append(node.value)
            continue
        if buf:
            nodes.append(Text("".join(buf), run_start))
            buf = []
        nodes.append(node)

    if buf:
        nodes.append(Text("".join(buf), run_start))
    return nodes, i


def _next_node(result: ParseResult, text: str, i: int, end: int) -> tuple[Node, int]:
    """Parse one construct at ``i``, falling back to a single literal character.

    Constructs are tried tightest-binding first, so a backtick protects
    everything that follows it.
    """
    if text[i] == "\\":
        escaped = _parse_escape(text, i, end)
        if escaped is not None:
            return escaped
    if text[i] == "`":
        code = _parse_code_span(text, i, end)
        if code is not None:
            return code
    if text[i] == "{" and text.startswith("{{", i):
        directive = _parse_directive(result, text, i, end)
        if directive is not None:
            return directive
    emphasis = _parse_emphasis(result, text, i, end)
    if emphasis is not None:
        return emphasis
    return Text(text[i], i), i + 1


def _parse_escape(text: str, i: int, end: int) -> tuple[Text, int] | None:
    if i + 1 >= end or text[i + 1] not in _ESCAPABLE:
        return None
    # The node starts at the escaped character, not at the backslash that
    # produced it, so its offset stays honest if a warning ever points at it.
    return Text(text[i + 1], i + 1), i + 2


def _parse_code_span(text: str, i: int, end: int) -> tuple[Span, int] | None:
    close = text.find("`", i + 1, end)
    if close == -1:
        return None
    content = text[i + 1 : close]
    # CommonMark strips one flanking space pair, which lets `` `**x**` ``
    # survive intact.
    if len(content) >= 2 and content[0] == " " and content[-1] == " ":
        content = content[1:-1]
    return Span({"font": CODE_FONT}, [Text(content, i + 1)], i), close + 1


def _parse_directive(
    result: ParseResult, text: str, i: int, end: int
) -> tuple[Node, int] | None:
    match = _DIRECTIVE.match(text, i, end)
    if match is None:
        return None
    if match.group(1) == "/":
        return _closing_directive(result, match), match.end()
    return _opening_directive(result, text, match, end)


def _closing_directive(result: ParseResult, match: re.Match[str]) -> Text:
    raw_name = match.group(2)
    # A name already reported as crossing a paragraph is not reported again.
    if squash(raw_name) in result.crossed:
        result.crossed.discard(squash(raw_name))
    else:
        result.issues.append(
            ParseIssue(match.start(), f"stray closing directive {raw_name!r}")
        )
    return Text(match.group(0), match.start())


def _opening_directive(
    result: ParseResult, text: str, match: re.Match[str], end: int
) -> tuple[Node, int] | None:
    raw_name = match.group(2)
    start = match.end()
    close = _find_directive_close(text, start, end, raw_name)
    if close is None:
        _report_directive_without_close(
            result, text, start, end, raw_name, match.start()
        )
        return None
    after = text.index("}}", close) + 2
    try:
        font = coerce_font(raw_name)
    except ValueError as exc:
        result.issues.append(ParseIssue(match.start(), str(exc)))
        # Keep the whole construct verbatim so its closing tag is not also
        # reported as stray.
        return Text(text[match.start() : after], match.start()), after
    children, _ = _parse_until(result, text, start, close, None)
    return Span({"font": font}, children, match.start()), after


def _report_directive_without_close(
    result: ParseResult,
    text: str,
    start: int,
    end: int,
    raw_name: str,
    opener: int,
) -> None:
    def find(from_index: int) -> int | None:
        return _find_directive_close(
            text, from_index, end, raw_name, bound_paragraph=False
        )

    if _crosses_paragraph(text, start, end, find):
        result.issues.append(
            ParseIssue(
                opener,
                f"directive {{{{{raw_name}}}}} crosses a blank line "
                f"and was left as text",
            )
        )
        result.crossed.add(squash(raw_name))
    else:
        result.issues.append(
            ParseIssue(opener, f"unclosed directive {{{{{raw_name}}}}}")
        )


def _parse_emphasis(
    result: ParseResult, text: str, i: int, end: int
) -> tuple[Node, int] | None:
    delim = _match_opener(text, i, end)
    if delim is None:
        return None
    close = _find_closer(text, i + len(delim), end, delim)
    if close is None:
        _report_emphasis_without_close(result, text, i, end, delim)
        # Unclosed: emit the delimiter verbatim and continue past it.
        return Text(delim, i), i + len(delim)
    children, _ = _parse_until(result, text, i + len(delim), close, delim)
    return Span(dict(_EMPHASIS[delim]), children, i), close + len(delim)


def _report_emphasis_without_close(
    result: ParseResult, text: str, i: int, end: int, delim: str
) -> None:
    def find(from_index: int) -> int | None:
        return _find_closer(text, from_index, end, delim, bound_paragraph=False)

    if _crosses_paragraph(text, i + len(delim), end, find):
        result.issues.append(
            ParseIssue(i, f"{delim} span crosses a blank line and was left as text")
        )


def _match_opener(text: str, i: int, end: int) -> str | None:
    """Return the longest delimiter starting at ``i`` that may open a span."""
    for delim in _EMPHASIS:
        if not _matches(text, i, end, delim, closing=False):
            continue
        return delim
    return None


def _matches(text: str, i: int, end: int, delim: str, *, closing: bool) -> bool:
    """Check ``delim`` at ``i``, including run boundaries and flanking whitespace."""
    if not text.startswith(delim, i):
        return False
    char = delim[0]
    before = text[i - 1] if i > 0 else ""
    after = text[i + len(delim)] if i + len(delim) < end else ""

    # The delimiter must be a complete run: no adjacent copies of its own
    # character, otherwise ``**`` would match inside ``***``.
    if before == char or after == char:
        return False

    if closing:
        return bool(before) and not before.isspace()
    return bool(after) and not after.isspace()


def _paragraph_limit(text: str, start: int, end: int) -> int:
    """Offset of the first blank line at or after ``start``, else ``end``."""
    match = _BLANK_LINE.search(text, start, end)
    return match.start() if match is not None else end


def _crosses_paragraph(
    text: str, start: int, end: int, find: Callable[[int], int | None]
) -> bool:
    """True when ``find`` locates a closer beyond the current paragraph."""
    limit = _paragraph_limit(text, start, end)
    if limit >= end:
        return False
    return find(limit) is not None


def _find_closer(
    text: str, start: int, end: int, delim: str, *, bound_paragraph: bool = True
) -> int | None:
    """Find the matching closer for ``delim``, skipping escapes and code spans."""
    if bound_paragraph:
        end = _paragraph_limit(text, start, end)
    i = start
    while i < end:
        ch = text[i]
        if ch == "\\" and i + 1 < end:
            i += 2
            continue
        if ch == "`":
            close = text.find("`", i + 1, end)
            i = close + 1 if close != -1 else i + 1
            continue
        if _matches(text, i, end, delim, closing=True):
            return i
        i += 1
    return None


def _find_directive_close(
    text: str,
    start: int,
    end: int,
    raw_name: str,
    *,
    bound_paragraph: bool = True,
) -> int | None:
    """Return the offset of the ``{{/name}}`` matching the opener, if any."""
    if bound_paragraph:
        end = _paragraph_limit(text, start, end)
    wanted = squash(raw_name)
    depth = 1
    pos = start
    while True:
        match = _DIRECTIVE.search(text, pos, end)
        if match is None:
            return None
        if squash(match.group(2)) == wanted:
            depth += -1 if match.group(1) == "/" else 1
            if depth == 0:
                return match.start()
        pos = match.end()
