# Contributing

Working notes for changing the code. If you only want to *use* the tool, the
[README](README.md) is the document you want; this one covers setup, the gates
a commit has to pass, the module map, and how to add a font.

## Setup

The package supports Python 3.12 and newer. The development environment pins
3.15 in `.python-version`, so the hooks and the test runs below use it; the
suite is expected to pass on 3.12 as well.

```console
git clone https://github.com/ben05allen/unicode-fonts
cd unicode-fonts
uv sync                # creates .venv and installs the dev group
uv run prek install    # installs the git hook (once per clone)
```

There is nothing else to configure: every tool below runs through `uv run`, so
the locked environment is the only one in play.

## Commands

| command | what it does |
| --- | --- |
| `uv run pytest` | the test suite (no network, runs in well under a second) |
| `uv run ruff check .` | lint (`--fix` to apply) |
| `uv run ruff format --check .` | formatting |
| `uv run ty check` | type checking over the whole project |
| `uv run complexipy src tests` | cognitive complexity, limit 15 per function |
| `uv run deptry .` | declared dependencies vs. actual imports |
| `uv run prek run --all-files` | every gate at once |

`uv run prek run <hook>` runs a single hook, and `SKIP=pytest git commit` skips
one for a single commit.

## Layout

| path | contents |
| --- | --- |
| `src/unicode_fonts/fonts.py` | the glyph tables as data, one 95-character string per font; excluded from ruff |
| `src/unicode_fonts/registry.py` | typed metadata over those tables: families, weight/slant axes, name coercion, lossless detection |
| `src/unicode_fonts/parser.py` | the Markdown-subset parser: nodes, spans, escapes, paragraph bounds |
| `src/unicode_fonts/render.py` | nodes to Unicode text: font resolution, decorations, warnings |
| `src/unicode_fonts/cli.py` | argument parsing and I/O; a thin layer over `render()` |
| `tests/` | parser/render behaviour, registry invariants, CLI and encoding |

`tests/test_render.py` doubles as the specification: every rule in the README's
syntax and whitespace sections has a case there, including the ones that assert
a warning fires and where it points.

## Adding a font

Every table is aligned to the same 95-character alphabet, in table order — not
codepoint order, since `"` and `\` are hoisted to the front — so a table is
matched to input by `zip`, never by `ord`.

1. Add the table to `fonts_dict` in `fonts.py`: 95 characters, position for
   position with `BASE_ALPHABET`.
2. If the font has weight or slant variants, register each name in `_AXES` in
   `registry.py` with its `(family, weight, slant)`. Anything not in `_AXES` is
   treated as a decorative font automatically, so a self-contained alphabet
   needs only step 1.
3. Update `tests/test_registry.py`: the table count is pinned, and a font whose
   glyphs are not injective must be added to `EXPECTED_LOSSY`. The test fails
   until the flag matches the data, which is the point — the `lossless` flag is
   derived, not declared.

Whitespace is dropped from every table when `CHAR_MAPS` is built, so the space
character's entry is never used. Keep the column anyway so the alignment holds.

## Gates

Hooks live in `.pre-commit-config.yaml` and are driven by
[prek](https://github.com/j178/prek), a Rust pre-commit replacement. Every hook
is `language: system` and runs through `uv run`, so it uses the same locked
environment as the commands above — `uv sync` is the only setup step.

| hook | enforces |
| --- | --- |
| `ruff-check` | lint, with `--fix` |
| `ruff-format` | formatting |
| `ty` | type checking over the whole project |
| `deptry` | declared dependencies vs. actual imports (missing, unused, transitive) |
| `complexipy` | cognitive complexity ≤ 15 per function |
| `pytest` | the test suite |

`ty`, `deptry` and `pytest` analyse the project rather than individual files,
so they set `pass_filenames: false` and `always_run: true`: a commit that only
touches `pyproject.toml` or the lockfile still gets type-checked and tested.
Trusting the staged file list would silently skip them exactly when a
dependency changed. All three together cost well under a second.

`deptry` catches an import with no matching declaration (`DEP001`) and a
declaration nothing imports (`DEP002`); unused *dev* dependencies are not
reported, which is what you want for tools that are only ever invoked.

The complexity limit is enforced rather than aspirational, and it has already
paid for itself twice: `_parse_until` sat at 66 until it became a dispatcher
over one handler per construct (12), and `cli.main` reached 18 once the encoding
and `--list-fonts` checks landed, until the read, render and output paths were
given their own reporting (5).

`.pre-commit-config.yaml` is used rather than `prek.toml` so the same file also
works for anyone running upstream `pre-commit`.

## Design notes

Behavioural decisions and their rationale live in the README's
[design decisions](README.md#design-decisions), where users can see them. They
are recorded so they are not relitigated by accident — if a change needs to
break one, change the entry in the same commit.

Two invariants are easy to break without noticing:

- **Unmarked text is byte-identical.** Styling happens only inside a marked
  span, and nothing may rewrite whitespace, line endings or non-ASCII.
- **Always emit valid, re-renderable text.** A second pass over the output must
  be a no-op; that property is asserted in `tests/test_render.py`.
