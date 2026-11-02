# Contributing

Thanks for taking a look. This project is deliberately narrow: it converts images
to 1-bit dots and nothing else. Small, well-tested changes fit it best.

Before you start, read:

- [docs/PLAN.md](docs/PLAN.md) — what the app is for, and what it will never do
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the code is put together
- [AGENTS.md](AGENTS.md) — the same rules as a checklist

## Development setup

Requirements: Windows (tested), Python 3.11+, and optionally `uv`.

```powershell
uv venv .venv
uv pip install --python .venv\Scripts\python.exe -e ".[gui,dev]"
```

Without `uv`:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[gui,dev]"
```

Run it from source:

```powershell
.venv\Scripts\tdots.exe doctor
.venv\Scripts\tdots.exe convert sample.jpg
.venv\Scripts\tdots.exe gui
```

To run the standalone build instead (no Python, no venv):

```powershell
build\nuitka\tdots.dist\tdots.exe gui
```

Double-clicking `tdots.exe` opens the GUI; from a terminal, no arguments prints
help. Build it once with `build\build.ps1` if the folder is missing. Full launch
instructions: [README § Run](README.md#run).

## Quality gates

All four must pass before a pull request is ready:

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\ruff check src tests benchmarks
.venv\Scripts\mypy src
node --check src\thermaldots\ui\web\app.js
```

Current baseline: the whole suite runs in a few seconds with no lint or type
errors. The test count is whatever `pytest` reports — this document does not
repeat it, because stale numbers are worse than none.

If you touch the JavaScript, reload the GUI and confirm the preview still
renders — `node --check` only proves the file parses.

## What makes a good change

- **One concern per change.** A dither tweak and a CLI refactor in one commit are
  hard to review and harder to revert.
- **Tests with the fix.** Every bug fix gets a test that fails without it. Every
  new flag gets a CLI test and a line in `docs/USAGE.md`.
- **Numbers are measured.** If you claim a speed-up, include the before/after and
  the command that produced them.
- **Errors stay user-safe.** Raise a `ThermalDotsError` subclass with a `message`
  and a `hint`; no bare exceptions across the CLI or GUI boundary.
- **No new dependency without a reason** recorded in `docs/PLAN.md` §7.

## Changing dithering (read this first)

Dither output is pinned by 17 golden fingerprints. A changed kernel will fail
`tests/test_golden.py` — that is the test doing its job, not a broken test.

1. Make the change.
2. `pytest tests/test_dither.py`
3. Regenerate deliberately:
   ```powershell
   .venv\Scripts\python -m tests.golden.regen
   ```
4. Read the `tests/golden/hashes.json` diff. Every changed line means every
   user's output changes.
5. Re-run `benchmarks\bench.py --repeat 5` and update the performance table in
   `docs/PLAN.md` §9 and the summary in `README.md`.

Never "fix" a golden failure by loosening the test.

## Changing the bit format

`bits.py` and `exporters.py` are the highest-risk files in the project: a
polarity mistake produces a plausible-looking file that prints as a negative.

Requirements for any change there:

- Keep `pack_1bit` MSB-first with `1` = dot.
- Keep row padding bits `0` at every width.
- Keep the independent parser round-trip in `tests/test_exporters.py` green. It
  parses bytes from the specification, not with our own unpacker, so it catches
  a packer bug that a matching unpacker would hide.
- Test odd widths (1, 5, 13, 961, 2000 dots) and heights above 960 rows, where
  fragmentation happens.
- `upscale_ink` stays nearest-neighbour and runs after dithering. A `.bin` must
  be byte-identical at every `--upscale` value; only PNG/BMP grow.
- Native rendering (`render_width`) runs *before* dithering and changes
  `resolved_width()`. Test both `native` and an explicit width, and verify that
  `-f bin` and `-f txt` still refuse it.

## Changing the GUI

- The bridge (`ui/app.py`) is called positionally by pywebview. Do not make
  parameters keyword-only; `tests/test_ui_api.py` fails if you do.
- Return errors as `{ok: false, error, message, hint}`. Never let an exception
  cross into JavaScript — it appears in a console the user cannot see.
- Keep `MAX_SOURCES` (`app.py`) and `MAX_ITEMS` (`app.js`) equal.
- After editing `index.html`, `style.css` or `app.js`, launch `tdots gui` and
  confirm the change is visible. WebView2 caches aggressively; `private_mode=True`
  exists because a stale page was served after a rebuild.

## Documentation

Docs are tested, not decorative:

- `tests/test_docs.py` checks that every `--flag` in `docs/USAGE.md` exists in
  `tdots <command> --help`, and that every relative Markdown link resolves.
- Keep one fact in one place: flags in `USAGE.md`, decisions in `PLAN.md`,
  internals in `ARCHITECTURE.md`, vocabulary in `GLOSSARY.md`.
- Short sentences, plain words, no marketing adjectives.

## Commits and pull requests

- Commit subject: imperative, under 72 characters —
  `Fix FILL crop leaving a black edge on odd widths`.
- Body: what changed, why, and how you verified it (commands + results).
- A PR description should state the behaviour change and the tests that cover it.
- Do not commit build output (`build/nuitka/`, `dist/`, `.venv/`).

## Reporting bugs

Include:

1. The exact command or GUI steps.
2. The output of `tdots doctor`.
3. The source image's format and pixel size (`tdots info <file>`).
4. What you expected and what you got. For visible problems, attach the PNG and
   the `.json` sidecar.

## License

By contributing you agree that your work is licensed under the MIT license
([LICENSE](LICENSE)).
