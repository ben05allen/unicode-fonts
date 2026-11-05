"""Command line interface: ``unicode-fonts [FILE] [--flags]``."""

from __future__ import annotations

import argparse
import sys
import warnings

from .registry import FAMILIES, FONTS, sample
from .render import UnicodeFontsWarning, render

PROGRAM = "unicode-fonts"

_EPILOG = """\
syntax:
  **bold**   *italic*   ***bold italic***   `code`
  ~~strike~~   __underline__   {{circled}}any font{{/circled}}
  backslash escapes any punctuation: \\*literal\\*

examples:
  echo '**shipping** it *today*' | unicode-fonts
  unicode-fonts post.md --family serif -o out.txt
  unicode-fonts post.md --font fullwidth --copy
  unicode-fonts --list-fonts
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description="Format plain text with Unicode for platforms without rich text.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="input file, or '-' to read standard input (default: stdin)",
    )
    parser.add_argument("-o", "--output", help="write to a file instead of stdout")
    style = parser.add_mutually_exclusive_group()
    style.add_argument(
        "--family",
        default="sans",
        metavar="FAMILY",
        help="family for bold/italic markup "
        f"(default: sans; one of: {', '.join(str(f) for f in FAMILIES)})",
    )
    style.add_argument(
        "--font",
        metavar="FONT",
        help="style the whole document with one font (see --list-fonts)",
    )
    parser.add_argument(
        "--allow-lossy",
        action="store_true",
        help="allow fonts that cannot distinguish some characters (case-destroying)",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="copy the result to the clipboard (requires the 'clipboard' extra)",
    )
    parser.add_argument(
        "--list-fonts",
        action="store_true",
        help="show every available font with a sample and exit",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_version()}")
    return parser


def _version() -> str:
    from . import __version__

    return __version__


def _list_fonts(stream) -> None:
    header = ("name", "family", "style", "lossless", "sample")
    rows = [
        (
            spec.name,
            str(spec.family),
            spec.request,
            "yes" if spec.lossless else "no",
            sample(spec.name, "Aa1"),
        )
        for spec in sorted(
            FONTS.values(), key=lambda s: (not s.has_axes, str(s.family), s.name)
        )
    ]
    table = [header, *rows]
    widths = [max(len(row[i]) for row in table) for i in range(len(header))]

    def line(row: tuple[str, ...]) -> str:
        return "  ".join(value.ljust(widths[i]) for i, value in enumerate(row)).rstrip()

    stream.write(line(header) + "\n")
    stream.write(line(tuple("-" * width for width in widths)) + "\n")
    for row in rows:
        stream.write(line(row) + "\n")


def _read(path: str) -> str:
    """Read UTF-8 without newline translation so CRLF documents stay CRLF."""
    if path == "-":
        # Bypass the text wrapper's universal-newline translation when the
        # stream provides bytes; fall back so tests and embedders can substitute
        # their own stdin.
        buffer = getattr(sys.stdin, "buffer", None)
        if buffer is not None:
            return buffer.read().decode("utf-8")
        return sys.stdin.read()
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _copy_to_clipboard(text: str) -> None:
    try:
        import pyperclip
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise SystemExit(
            "error: clipboard support needs the optional extra\n"
            "       uv tool install 'unicode-fonts[clipboard]'"
        ) from exc
    try:
        pyperclip.copy(text)
    except Exception as exc:  # pragma: no cover - platform dependent
        raise SystemExit(f"error: could not access the clipboard: {exc}") from exc


def _report(message: str) -> None:
    print(f"{PROGRAM}: error: {message}", file=sys.stderr)


def _read_error(path: str, exc: OSError | UnicodeDecodeError) -> str:
    if isinstance(exc, UnicodeDecodeError):
        where = "standard input" if path == "-" else path
        return f"{where} is not valid UTF-8 (byte {exc.start}: {exc.reason})"
    return str(exc)


def _render_capturing_warnings(source: str, args: argparse.Namespace) -> str:
    """Render ``source``, then replay the warnings that were held back.

    Font warnings are recorded so they can be printed as ``warning:`` lines;
    anything else is handed back to the ordinary filters.  Recording turns
    every warning into a list entry, so a category we do not own would
    otherwise vanish.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", UnicodeFontsWarning)
        result = render(
            source,
            family=args.family,
            font=args.font,
            allow_lossy=args.allow_lossy,
        )

    for entry in caught:
        if issubclass(entry.category, UnicodeFontsWarning):
            print(f"warning: {entry.message}", file=sys.stderr)
        else:
            warnings.warn_explicit(
                entry.message, entry.category, entry.filename, entry.lineno
            )
    return result


def _write_or_print(result: str, args: argparse.Namespace) -> int:
    """Send the result to ``-o`` if given, else to stdout unless ``--copy`` did."""
    if not args.output:
        if not args.copy:
            sys.stdout.write(result)
        return 0
    try:
        _write(args.output, result)
    except OSError as exc:
        _report(str(exc))
        return 1
    return 0


def _show_fonts(args: argparse.Namespace) -> int:
    """Handle ``--list-fonts``, which reads nothing and takes no input path."""
    if args.path is not None:
        _report(f"--list-fonts does not read {args.path}")
        return 2
    _list_fonts(sys.stdout)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    path = args.path if args.path is not None else "-"

    if args.list_fonts:
        return _show_fonts(args)

    try:
        source = _read(path)
    except (OSError, UnicodeDecodeError) as exc:
        _report(_read_error(path, exc))
        return 1

    try:
        result = _render_capturing_warnings(source, args)
    except ValueError as exc:
        _report(str(exc))
        return 2

    if args.copy:
        _copy_to_clipboard(result)

    return _write_or_print(result, args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
