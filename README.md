# unicode-fonts

Format plain documents with **Unicode** so they carry emphasis on platforms that
have no rich text — Instagram captions, X posts, LinkedIn, SMS, YAML comments,
GitHub issue titles, anywhere a bold or italic button is missing.

Write ordinary Markdown, get styled text out:

```console
$ printf 'We shipped **v2.0** *today* — it is ***fast***.\n' | uv run unicode-fonts
We shipped 𝘃𝟮.𝟬 𝘁𝗼𝗱𝗮𝘆 — it is 𝙛𝙖𝙨𝙩.
```

Unmarked text is emitted byte for byte, so a document with no markup round-trips
unchanged and `diff` shows exactly what was styled.

> **Caveat, stated once:** these are Unicode lookalike characters, not real
> styling. Screen readers may announce them oddly and most search engines will
> not match `𝗯𝗼𝗹𝗱` against `bold`. Use them for display text, not for content
> people need to find later.

## Install

```console
uv tool install unicode-fonts        # or: uv add unicode-fonts
uv tool install 'unicode-fonts[clipboard]'   # adds --copy support
```

## Usage

```console
$ unicode-fonts post.md                      # file -> stdout
$ unicode-fonts post.md -o out.txt           # file -> file
$ cat post.md | unicode-fonts                # stdin -> stdout
$ unicode-fonts post.md --copy               # put it on the clipboard
$ unicode-fonts post.md --family serif       # change the bold/italic family
$ unicode-fonts post.md --font fullwidth     # style the whole document
$ unicode-fonts --list-fonts                 # explore the palette
$ unicode-fonts post.md --allow-lossy        # permit case-destroying fonts
```

`--family` and `--font` are mutually exclusive: `--family` changes what
`**bold**` resolves to, `--font` imposes one font on everything.

## Syntax

| Markup | Result | Mechanism |
| --- | --- | --- |
| `**bold**` | `𝗯𝗼𝗹𝗱` | bold alphabet of the active family |
| `*italic*` | `𝘪𝘵𝘢𝘭𝘪𝘤` | italic alphabet of the active family |
| `***both***` | `𝙗𝙤𝙩𝙝` | bold-italic alphabet |
| `` `code` `` | `𝚌𝚘𝚍𝚎` | `monospace` |
| `~~strike~~` | `s̶t̶r̶i̶k̶e̶` | U+0336 on every character |
| `__under__` | `u̲n̲d̲e̲r̲` | U+0332 on every character |
| `{{circled}}text{{/circled}}` | `ⓣⓔⓧⓣ` | any font from `--list-fonts` |
| `\*` `\` `\{` | literal characters | backslash escapes any ASCII punctuation |

Rules that follow from being a *subset* of Markdown rather than an
implementation of it:

- **Unclosed markers stay literal.** `a **b` renders as `a **b`; nothing is
  silently swallowed.
- **A delimiter only matches its own kind.** `**a *b** c*` does not reinterpret
  itself the way CommonMark would — the inner `*b` loses its partner and stays
  as text. Predictability beats cleverness in a one-shot posting tool.
- **Only `__` underlines.** A single `_` is always literal, so `snake_case`
  and `file_name.py` are safe.
- **Code spans are verbatim.** `` `**x**` `` keeps its asterisks; backticks
  bind tighter than any other construct.
- **Spans stop at a blank line.** `**start\n\nend**` stays literal — with a
  warning — instead of bolding the next paragraph, so a forgotten closer is
  visible rather than plausible-looking. A single line break is fine.
- **Escaped output is not re-parseable.** `\*x\*` produces `*x*`, which a second
  pass would read as italic. That is inherent to escaping, exactly as in
  Markdown.

## Whitespace

Whitespace is load-bearing in plain-text documents, so it is handled
conservatively:

| Concern | Behaviour |
| --- | --- |
| Runs of spaces, tabs, indentation, trailing spaces | preserved exactly — an unmarked document is never reflowed |
| Line endings | preserved verbatim: CRLF in, CRLF out, and `-o` output is byte-identical to the input wherever nothing was styled |
| Spaces inside a span | never restyled — the `monospace` table's U+2002 and `fullwidth`'s U+3000 entries are dropped |
| `~~strike~~` / `__under__` | interior spaces carry the combining mark so the line is continuous; leading and trailing spaces stay bare, and tabs or newlines are never marked |
| Blank lines | end a paragraph, and no span may cross one |

```console
$ printf 'a **b**\r\nc\r\n' > post.md && unicode-fonts post.md -o out.md
$ cmp post.md out.md   # differs only where 'b' was styled

$ printf '~~see you~~\n' | unicode-fonts
s̶e̶e̶ ̶y̶o̶u̶
```

## Families

`--family` picks the alphabet used for bold, italic and bold-italic. Coverage is
uneven because Unicode only defines so many combinations:

| family | regular | bold | italic | bold italic |
| --- | --- | --- | --- | --- |
| `sans` (default) | `𝖺` | `𝗮` | `𝘢` | `𝙖` |
| `serif` | `a` | `𝐚` | `𝑎` | `𝒂` |
| `monospace` | `𝚊` | — | — | — |
| `script` | `𝒶` | `𝓪` | — | — |
| `fraktur` | `𝔞` | `𝖆` | — | — |
| `double-struck` | `𝕒` | — | — | — |

## When a combination does not exist

The tool never fails on a style it cannot express. It picks the closest
representation, **preserves the family** (it carries the most visual identity)
and warns on stderr:

```console
$ printf '**`bold code`**' | unicode-fonts
warning: line 1, col 3: bold is not available in the monospace family; using 'monospace' (bold dropped)
𝚋𝚘𝚕𝚍 𝚌𝚘𝚍𝚎
```

| request | resolved | dropped |
| --- | --- | --- |
| bold monospace | `monospace` | bold |
| bold italic monospace | `monospace` | bold, italic |
| italic script | `script` | italic |
| bold italic script | `boldScript` | italic |
| bold double-struck | `doubleStruck` | bold |
| bold `{{circled}}` | `circled` | bold (font wins) |

Degradation always drops weight or slant, never the family, and always warns.
Silently changing the look of your text is the one thing this tool refuses
to do.

## Decorative fonts

The other 13 tables are self-contained alphabets with no weight or slant. They
are reachable inline (`{{squared}}…{{/squared}}`) or document-wide
(`--font squared`).

Some of them **cannot round-trip**: they map uppercase and lowercase letters to
the same glyph, so `H` and `h` are indistinguishable afterwards. Those are
gated. Without `--allow-lossy` the affected text is left unstyled and a warning
explains why; text that happens to contain no ambiguous characters (e.g.
`{{squared}}123{{/squared}}`) renders normally.

```console
$ printf '{{squared}}Box{{/squared}}' | unicode-fonts
warning: line 1, col 12: 'squared' cannot distinguish 'B' from 'b'; leaving text unstyled (use --allow-lossy to override)
Box

$ printf '{{squared}}Box{{/squared}}' | unicode-fonts --allow-lossy
🄱🄾🅇
```

Lossless: `circled`, `fullwidth`, `smallCaps`, `inverted`, `mirrored`,
`subscript`. Lossy: `squared`, `squaredNegative`, `parenthesized`,
`circledNegative`, `superscript`, `rotatedLeft`, `rotatedRight`.

## Library

```python
from unicode_fonts import UnicodeFontsWarning, render

render("**hello**")                       # '𝗵𝗲𝗹𝗹𝗼'
render("**hello**", family="serif")       # '𝐡𝐞𝐥𝐥𝐨'
render("hello", font="fullwidth")         # 'ｈｅｌｌｏ'
render("**hello**", allow_lossy=False)

import warnings
warnings.simplefilter("ignore", UnicodeFontsWarning)
```

`render()` always returns a `str`. Compromises are reported through
`UnicodeFontsWarning`, so the standard `warnings` filters control them and
`pytest.warns` can assert on them. Each message carries a `line L, col C`
prefix.

Also exported: `FONTS` (name → `FontSpec` with `family`, `weight`, `slant`,
`lossless`) and the `Family` / `Weight` / `Slant` enums, for building your own
UI on top.

## Design decisions

Recorded so they are not relitigated by accident:

1. **Markdown subset, not CommonMark.** `**`, `*`, `***`, `` ` ``, `~~`, `__`,
   plus `\` escapes and a `{{font}}` directive. Familiar to humans and LLMs,
   and it degrades to literal text instead of raising.
2. **Degrade and warn, never fail.** Missing glyph combinations resolve to the
   nearest font with the family held constant.
3. **Library plus CLI**, one thin entry point over a pure `render()` function.
4. **Non-ASCII passes through untouched.** `é`, emoji and CJK are never
   rebuilt, decomposed or restyled.
5. **Sans is the default family.** It renders most evenly at caption sizes;
   `--family serif` is one flag away.
6. **Inline directives for the decorative fonts**, with a lossless gate.
7. **Unmarked text is byte-identical.** Styling happens only where marked;
   `--font` is the explicit opt-in for whole-document styling.
8. **Warnings, not result objects.** `render()` returns text, and
   `warnings.warn()` carries the caveats.

Three more that followed from asking how whitespace should behave:

9. **Line endings are preserved verbatim.** Documents are read and written with
   newline translation disabled, so a CRLF file stays CRLF and file input
   matches stdin.
10. **Spans are paragraph-bounded.** A closer must appear before the next blank
    line, otherwise the opener stays literal and a single warning explains why.
11. **Decoration covers interior spaces, not edges.** Marks go on spaces
    between words so the rule is continuous, but never on leading or trailing
    whitespace (where they would float) or on tabs and newlines (where they
    would land at the start of the next line).

And one more worth knowing: **font names are matched loosely.** `bold-script`,
`BoldScript` and `bold script` all resolve to `boldScript`.

## Development

```console
uv sync                                    # dev tools: pytest, ruff, prek, ty, complexipy
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run ty check                            # type checker
uv run complexipy --failed src tests       # cognitive complexity (limit: 15)
```

### Git hooks

Hooks live in `.pre-commit-config.yaml` and are driven by
[prek](https://github.com/j178/prek), a Rust pre-commit replacement. Every hook
is `language: system` and runs through `uv run`, so it uses the same locked
environment as the commands above — `uv sync` is the only setup step.

```console
uv run prek install              # once per clone
uv run prek run --all-files      # run every hook now
uv run prek run ruff-check       # run one hook
uv run prek list                 # show the configured hooks
SKIP=pytest git commit           # skip a hook for a single commit
```

| hook | enforces |
| --- | --- |
| `ruff-check` | lint, with `--fix` |
| `ruff-format` | formatting |
| `ty` | type checking over the whole project (`pass_filenames: false`, since inference needs every module) |
| `complexipy` | cognitive complexity ≤ 15 per function |
| `pytest` | the test suite |

The complexity limit is enforced rather than aspirational: `_parse_until` sat at
66 until it was split into a dispatcher plus one handler per construct, which
brought it to 12.

`.pre-commit-config.yaml` is used rather than `prek.toml` so the same file also
works for anyone running upstream `pre-commit`.
