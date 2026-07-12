# Agent Instructions

This repository builds Python extension helpers for using Snowflake table descriptions and metadata with OpenAI SDK coding-agent workflows.

Agents should treat this file as the first stop before making changes.

## Startup Checklist

Before editing code or docs:

1. Confirm the current branch and worktree state.

   ```bash
   git status --short
   git branch --show-current
   ```

2. Check for project context.

   Look for `project_context.md` at the repository root. If it exists, read it before doing any implementation or planning. If it does not exist, continue with the repository docs and note the absence when it affects your assumptions.

3. Check for prior agent memory or history.

   Look for files commonly used by previous agent runs, including:

   - `memory.md`
   - `history.md`
   - `agent_memory.md`
   - `agent_history.md`
   - `.agents/`
   - `.codex/`
   - `work/`

   If any are present, read the relevant files before continuing. Treat them as context, not as authoritative truth when they conflict with tracked source files or current user instructions.

4. Check for incomplete work.

   Inspect:

   - `git status --short`
   - recent commits with `git log --oneline -5`
   - open TODO markers with `rg "TODO|FIXME|XXX|NotImplemented|xfail"`
   - failing or skipped tests
   - open PR notes or issue references if the user provides them

   Do not overwrite or revert user changes. If incomplete work is related to the task, continue from it carefully. If it is unrelated, leave it alone.

5. Verify local descriptions and data.

   Confirm that any descriptions, sample metadata, fixture data, schema exports, or Snowflake catalog snapshots referenced by the task have actually been pulled into the repository folder before using them.

   Check likely locations:

   - `docs/`
   - `tests/fixtures/`
   - `data/`
   - `examples/`
   - `work/`

   If referenced data is missing, do not invent it. Add a small fixture only when the task calls for test data and the shape is clear from existing docs or tests.

## Repository Map

- `src/openai_snowflake_agent_context/`: package source.
- `tests/`: unit and future contract tests.
- `docs/ARCHITECTURE_TECH_SPEC.md`: architecture and implementation plan.
- `docs/TDD_TEST_PLAN.md`: phased test-driven development outline.
- `pyproject.toml`: package metadata and tooling configuration.

## Development Practices

- Prefer small, testable modules over broad implementation files.
- Write or update tests before adding behavior.
- Keep live Snowflake and OpenAI calls out of default unit tests.
- Use fake connections, fake cursors, and fixture rows for metadata behavior.
- Mark intentionally deferred behavior with `pytest.mark.xfail` only when it documents a near-term API contract.
- Keep metadata-only behavior as the default; sample values must require explicit opt-in.
- Preserve caller-provided OpenAI SDK arguments and response objects in extension wrappers.
- Do not monkey-patch the official `openai` package.
- Avoid logging credentials, connection strings, or sample data.
- Quote Snowflake identifiers safely when dynamic identifiers are unavoidable.
- Treat governance metadata, masking policies, and sensitive tags as safety-relevant behavior.

## Testing

Use the local virtual environment if it exists:

```bash
.venv/bin/python -m pytest -q
```

If no virtual environment exists, create one and install dev dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
```

For targeted work:

```bash
.venv/bin/python -m pytest tests/test_metadata_provider.py -q
```

## Documentation Expectations

When behavior changes, update whichever document best matches the change:

- `README.md` for user-facing usage.
- `docs/ARCHITECTURE_TECH_SPEC.md` for architecture or design decisions.
- `docs/TDD_TEST_PLAN.md` for test strategy and implementation sequencing.
- `AGENTS.md` for agent workflow expectations.

## Handoff Notes

Before finishing:

1. Run the relevant tests, or clearly state why they were not run.
2. Check `git status --short`.
3. Summarize the branch, commit, tests, and any remaining incomplete work.
4. If you created or updated a branch intended for review, push it and provide the PR URL when available.

