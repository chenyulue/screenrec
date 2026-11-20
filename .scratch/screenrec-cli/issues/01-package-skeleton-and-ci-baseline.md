# 01: Package skeleton, console entry point, and CI matrix baseline

**What to build:** The `screenrec` package is installable, the `screenrec` console command runs, and a CI matrix continuously verifies both platform paths — the foundation every subsequent recording-feature ticket lands on.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] The package installs into a fresh environment (uv/pip) and the `screenrec` console command runs, printing help/version output
- [x] The package is split into four responsibility modules — capture, encoder, session, cli (per ADR 0002) — with clear boundaries between them
- [x] The pytest suite is wired up and a smoke test runs green
- [x] The GitHub Actions matrix runs the smoke test on both windows-latest and ubuntu-arm64 (under Xvfb), and both are green

## Comments

Implemented via TDD at the CLI subprocess seam: smoke tests (`tests/test_smoke.py`) drove the package skeleton.

- src-layout package `screenrec` with `capture` (WindowSource boundary), `encoder` (FrameEncoder boundary), `session` (RecordingSession boundary), `cli` (argparse + `screenrec` console entry point) per ADR 0002; root placeholder `main.py` removed.
- `pyproject.toml`: hatchling build backend, `[project.scripts] screenrec = "screenrec.cli:main"`, pytest dev group; `uv.lock` re-locked.
- Fresh-install verified: `uv venv` + `uv pip install .` in a clean venv, `screenrec --version`/`--help` run correctly.
- CI baseline `.github/workflows/ci.yml`: matrix `windows-latest` + `ubuntu-arm64` (Xvfb via `xvfb-run -a uv run pytest`), `uv sync --frozen`.
- Two-axis code review (Standards + Spec) passed with P2 notes applied: test asserts against `screenrec.__version__` (no duplicated version fact); capture docstring reworded to state sources "will be" implemented against the boundary.
- Note: bare `screenrec` invocation prints help (intentional CLI default, consistent with the ticket's help/version requirement).
