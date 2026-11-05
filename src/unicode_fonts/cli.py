"""Command line interface: ``unicode-fonts [FILE] [--flags]``."""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

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
        default="-",
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
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_fonts:
        _list_fonts(sys.stdout)
        return 0

    try:
        source = _read(args.path)
    except OSError as exc:
        print(f"{PROGRAM}: error: {exc}", file=sys.stderr)
        return 1

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", UnicodeFontsWarning)
        try:
            result = render(
                source,
                family=args.family,
                font=args.font,
                allow_lossy=args.allow_lossy,
            )
        except ValueError as exc:
            print(f"{PROGRAM}: error: {exc}", file=sys.stderr)
            return 2

    for entry in caught:
        if issubclass(entry.category, UnicodeFontsWarning):
            print(f"warning: {entry.message}", file=sys.stderr)

    if args.copy:
        _copy_to_clipboard(result)

    if args.output:
        try:
            Path(args.output).write_text(result, encoding="utf-8")
        except OSError as exc:
            print(f"{PROGRAM}: error: {exc}", file=sys.stderr)
            return 1
    elif not args.copy:
        sys.stdout.write(result)

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
