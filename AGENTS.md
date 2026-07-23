# Agent Instructions

This repository builds Python extension helpers for using Snowflake table descriptions and metadata with OpenAI SDK coding-agent workflows. It also includes a long-running agent harness for preserving work status, memory, progress updates, and external context across coding-agent sessions.

Agents should treat this file as the first stop before making changes.

## Current Project Context

- Primary local repo path: `/Users/richarcher/Documents/Codex/2026-07-02/creat/openai-snowflake-agent-context`.
- GitHub remote: `https://github.com/rarcher2011/snowflake-data-context.git`.
- Work is expected to happen on focused feature branches with pull requests.
- Branches and PRs have been used heavily in this project. Always check the current branch before editing, because the checkout may be on a feature branch rather than `main`.
- GitHub CLI auth and network access may vary by environment. Before pushing or opening a PR, check `gh auth status` and `git remote -v`. If network access is unavailable, leave a clear local handoff with the exact push or PR command.
- Do not assume a branch is pushed just because it has local commits. Confirm with `git status --short --branch`, `git branch -vv`, or `git ls-remote` when network is available.
- If a user asks for a PR description, provide concise Markdown with summary, tests, and risk notes.

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
   - `.agent_harness/`
   - `work/`
   - configured harness memory, status, or work files referenced by repo configuration

   If any are present, read the relevant files before continuing. Treat them as context, not as authoritative truth when they conflict with tracked source files or current user instructions.

   Ignore generated pytest temp directories such as `pytest-of-*` unless the current task is specifically about test artifacts.

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
- `docs/LONG_RUNNING_AGENT_HARNESS.md`: harness memory, status, and startup flow.
- `docs/CHATGPT_PLUGIN_ACTIONS.md`: ChatGPT Actions plugin integration notes.
- `docs/AWS_DEPLOYMENT.md`: AWS Lambda deployment design and script usage.
- `scripts/start_agent_harness.py`: startup script for long-running agent sessions.
- `scripts/deploy_aws.py`: AWS packaging and deployment helper.
- `pyproject.toml`: package metadata and tooling configuration.

## Implemented Feature Areas

The current codebase has grown beyond the initial scaffold. Before adding new APIs, inspect the relevant existing module and tests.

- Snowflake metadata context extraction for tables, columns, tags, policies, and descriptions.
- Metadata description analysis that identifies missing, weak, or useful table and column descriptions.
- Snowflake description update helpers that generate or execute description updates from user input.
- Long-running agent harness startup, memory discovery, status comparison, work intake, and session context generation.
- Cloud-backed harness memory and config locations for S3, Google Cloud Storage, and Google Docs.
- Human-readable Google Doc progress updates as long-running work advances.
- ChatGPT Actions plugin adapter and OpenAPI schema helpers for executing SDK extension methods.
- AWS Lambda deployment support and dry-run packaging checks.

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
- Keep cloud integrations optional. Import AWS, Google Cloud, and Google Docs dependencies lazily or behind extras so the core package remains lightweight.
- Prefer generated SQL plans plus explicit execution controls for Snowflake updates. User-provided description text should be handled as data, not interpolated unsafely.
- Keep long-running harness files human-readable where practical. Status and memory files should be easy for the next agent to inspect.
- When updating docs, align `README.md`, architecture notes, and TDD notes with the current code rather than aspirational behavior.

## Long-Running Harness Expectations

The harness exists to preserve continuity across long-running analysis and repeated agent starts. When working on harness behavior:

1. Check configuration first to determine the repository, memory location, status location, and work-intake location.
2. Find and read the latest memory before starting new work.
3. Compare the requested work and current status against the last saved memory and status file.
4. Record clear, human-readable progress when work starts, changes state, or completes.
5. Treat cloud memory backends as storage adapters. Core harness logic should remain testable with local files and fakes.
6. Do not write secrets, raw credentials, or sensitive data into memory, status, or Google Doc progress updates.

## Branch And PR Workflow

- Start new user-requested implementation work on a new branch unless the user asks to continue the current branch.
- Use focused commit messages that describe the behavior changed.
- Run relevant tests before committing when feasible.
- Push branches and open PRs when requested and network access is available.
- If sandbox or network approval is unavailable, do the local work, commit it if appropriate, and provide exact commands for the user to run.
- Backdated commits have been requested once in this project. Do not backdate commits unless the user explicitly asks, and use concrete dates in the commit metadata.

## Testing

Use the local virtual environment if it exists:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src
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

If pytest fails during startup because it cannot create a capture temp directory, first check that `pyproject.toml` still configures sys capture. If needed for a local run, set `TMPDIR=/private/tmp`.

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
