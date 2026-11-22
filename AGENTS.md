# screenrec — Agent Instructions

## Agent skills

### Issue tracker

Issues and specs for this repo live as markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage roles, mapped one-to-one to the same label strings. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: one `GLOSSARY.md` at the repo root plus `docs/adr/`. See `docs/agents/domain.md`.

## Library Reference

When developing, always make sure to use the library correctly by reading the library references

- mss: an ultra fast cross-platform multiple screenshots module in pure python using ctypes.
    - document reference: https://python-mss.readthedocs.io/stable/


## Developing Notes

- Use `uv` to develop the project, such as adding dependencies, running scripts, etc
- Write a concise commit message in Chinese for every commit.