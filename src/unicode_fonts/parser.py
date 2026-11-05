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
    nodes: list[Node] = []
    buf: list[str] = []
    run_start = i

    def flush() -> None:
        if buf:
            nodes.append(Text("".join(buf), run_start))
            buf.clear()

    while i < end:
        if closer is not None and _matches(text, i, end, closer, closing=True):
            flush()
            return nodes, i

        ch = text[i]

        # Escapes.
        if ch == "\\" and i + 1 < end and text[i + 1] in _ESCAPABLE:
            if not buf:
                run_start = i
            buf.append(text[i + 1])
            i += 2
            continue

        # Code spans bind tighter than anything else and take their content
        # verbatim, so a backtick can protect asterisks.
        if ch == "`":
            close = text.find("`", i + 1, end)
            if close != -1:
                flush()
                content = text[i + 1 : close]
                # CommonMark strips one flanking space pair, which lets
                # `` `**x**` `` survive intact.
                if len(content) >= 2 and content[0] == " " and content[-1] == " ":
                    content = content[1:-1]
                nodes.append(Span({"font": CODE_FONT}, [Text(content, i + 1)], i))
                i = close + 1
                run_start = i
                continue

        # {{font}} ... {{/font}}
        if ch == "{" and text.startswith("{{", i):
            match = _DIRECTIVE.match(text, i, end)
            if match is not None:
                closing, raw_name = match.group(1) == "/", match.group(2)
                if closing:
                    result.issues.append(
                        ParseIssue(i, f"stray closing directive {raw_name!r}")
                    )
                    flush()
                    buf.append(match.group(0))
                    run_start = i
                    i = match.end()
                    continue

                close = _find_directive_close(text, match.end(), end, raw_name)
                if close is None:
                    result.issues.append(
                        ParseIssue(i, f"unclosed directive {{{{{raw_name}}}}}")
                    )
                else:
                    after = text.index("}}", close) + 2
                    try:
                        font = coerce_font(raw_name)
                    except ValueError as exc:
                        result.issues.append(ParseIssue(i, str(exc)))
                    else:
                        flush()
                        children, _ = _parse_until(
                            result, text, match.end(), close, None
                        )
                        nodes.append(Span({"font": font}, children, i))
                        i = after
                        run_start = i
                        continue
                    # Unknown font: keep the whole construct verbatim so the
                    # closing tag is not reported twice.
                    flush()
                    nodes.append(Text(text[i:after], i))
                    i = after
                    run_start = i
                    continue

        # Emphasis-style delimiters.
        delim = _match_opener(text, i, end)
        if delim is not None:
            close = _find_closer(text, i + len(delim), end, delim)
            if close is not None:
                flush()
                children, _ = _parse_until(result, text, i + len(delim), close, delim)
                nodes.append(Span(dict(_EMPHASIS[delim]), children, i))
                i = close + len(delim)
                run_start = i
                continue
            # Unclosed: emit the delimiter verbatim and continue past it.
            flush()
            nodes.append(Text(delim, i))
            i += len(delim)
            run_start = i
            continue

        if not buf:
            run_start = i
        buf.append(ch)
        i += 1

    flush()
    return nodes, i


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


def _find_closer(text: str, start: int, end: int, delim: str) -> int | None:
    """Find the matching closer for ``delim``, skipping escapes and code spans."""
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


def _find_directive_close(text: str, start: int, end: int, raw_name: str) -> int | None:
    """Return the offset of the ``{{/name}}`` matching the opener, if any."""
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
