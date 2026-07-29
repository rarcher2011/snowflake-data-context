# Test-Driven Development Plan

## Purpose

This document defines the test-first path for building the Snowflake metadata context extension, the long-running agent harness, and the SMB analytics workflows described in `docs/SMB_ANALYTICS_WORKFLOWS.md`. The project should add or update tests before implementation code, then use the smallest implementation that makes those tests pass.

## Testing Principles

- Keep live Snowflake, OpenAI, S3, Google Cloud Storage, and Google Docs calls out of default unit tests.
- Use fake connections, fake cursors, fake cloud clients, and fixture rows for deterministic behavior.
- Treat formatter snapshots and generated harness session context as contract tests because coding agents depend on stable context shape.
- Mark future behavior with `xfail` only when it documents a near-term API contract and implementation is intentionally deferred.
- Prefer small modules with narrow tests over broad end-to-end tests during early implementation.
- Add integration tests only when they automatically skip without credentials.
- Keep credential, connection-string, and sample-data handling covered by negative tests.
- Treat SMB-facing reports as product contracts: wording can evolve, but finding categories, priorities, and recommended actions should be stable enough to test.
- Keep transformation recommendations reviewable. Tests should prove the package produces plans, not silent production changes.

## Current Test Coverage

The current suite covers the repository scaffold, public API, long-running harness, and cloud location abstractions.

- `tests/test_public_api.py` verifies the exported package surface.
- `tests/test_config.py` verifies safe default configuration and immutability.
- `tests/test_metadata_provider.py` verifies the current provider contract, the `TableContext` data object, and `xfail` outlines for formatter and OpenAI wrapper behavior.
- `tests/test_agent_harness.py` verifies local harness config loading, latest-memory parsing, JSON status loading, Markdown work queue parsing, mismatch detection, and session context generation.
- `tests/test_agent_harness_locations.py` verifies local/S3/GCS/Google Docs location specs, object-store URI parsing, Google Doc ID parsing, remote memory/status/work reads with fake readers, and remote config declaration.
- `tests/test_agent_harness_cloud.py` verifies the optional boto3 S3, Google Cloud Storage, and Google Docs adapter behavior using fake SDK clients.
- `tests/test_sampling.py` verifies one percent Snowflake sample-table SQL generation, identifier quoting, execution through fake cursors, and sampled-table status payloads.

Current verification commands:

```bash
uv sync --extra dev
uv run python -m pytest -q
uv run ruff check .
uv run mypy src
uv run scripts/start_agent_harness.py --json
```

## Completed TDD Slices

### Slice A: Package Scaffold

Covered behavior:

- Public exports remain stable.
- `SnowflakeContextConfig` defaults to metadata-only safety.
- Config objects are immutable after creation.
- `SnowflakeMetadataProvider.describe_tables` explicitly raises `NotImplementedError` until implemented.

### Slice B: Local Long-Running Agent Harness

Covered behavior:

- Harness config resolves paths from the configured repo root.
- Latest memory file is selected and parsed for `summary`, `status`, and `work_id`.
- Status JSON is loaded separately from memory.
- First unchecked Markdown work item becomes the next work item.
- Memory, status, and work queue mismatches are reported.
- Startup writes `.agent_harness/session_context.md`.

### Slice C: Cloud-Backed Harness Locations

Covered behavior:

- `s3://`, `gs://`, `gdoc://`, Google Docs share URLs, and local paths are parsed into location specs.
- Object-store URIs validate bucket and key/prefix.
- Remote S3 memory and GCS status can be read through fake readers.
- Google Docs can be used as a work queue location.
- Remote config locations can be declared for bootstrap metadata.
- Optional cloud adapter classes can read/list text content from fake boto3, GCS, and Google Docs clients.

### Slice D: Explicit Snowflake Table Sampling

Covered behavior:

- Sampling builds `CREATE OR REPLACE TABLE` SQL with `SAMPLE BERNOULLI (1)` by default.
- Source and destination Snowflake identifiers are quoted segment by segment.
- Invalid sample percentages and malformed identifier paths are rejected before execution.
- Fake cursor tests verify the sampling helper executes the generated SQL.
- Sampling results expose `sampled_table` status fields so later harness starts can reference the sampled table.
- Harness session context includes the sampled table when status declares one.

## Next TDD Slices

### Slice 0: SMB Analytics Domain Models

Write tests first for:

- `DataGap` severity, category, source table, source column, and recommendation fields.
- `DataIssue` for freshness, governance, schema, and quality concerns.
- `AnalysisWorkItem` for analyst, engineer, agent, and stakeholder-question work.
- `TransformationCandidate` for reviewable transformation recommendations.
- `MonitoringSnapshot` for point-in-time metadata health.
- Serialization to dictionaries suitable for harness status and ChatGPT Actions responses.

Expected modules:

- `analytics_models.py`

Exit criteria:

- Public dataclasses or Pydantic models represent SMB analytics work without requiring live Snowflake access.
- Models can be serialized without credentials or raw sampled data.

### Slice 0.1: Discovery Reports

Write tests first for:

- Discovery report summary metrics for scanned tables and columns.
- Missing and weak description findings converted into prioritized data gaps.
- Tables with unclear grain or missing business usage notes flagged for follow-up.
- Report output that separates observations, recommendations, and stakeholder questions.
- Markdown and JSON report formats.

Expected modules:

- `discovery_report.py`

Exit criteria:

- A caller can turn existing `TableContext` and description analysis objects into an SMB-friendly discovery report.

### Slice 0.2: Analyst Backlog Generation

Write tests first for:

- Data gaps converted into actionable work items.
- Work items labeled by owner type: analyst, engineer, agent, or stakeholder.
- Prioritization by severity, affected table count, and whether the issue blocks analysis.
- Stable output for harness work queues.

Expected modules:

- `analytics_backlog.py`

Exit criteria:

- A discovery report can produce a reviewable backlog that the harness can carry into future sessions.

### Slice 0.3: Transformation Recommendations

Write tests first for:

- Candidate staging models for raw or poorly documented tables.
- Reporting-view suggestions when multiple related tables are present.
- Relationship-validation tasks when joins are inferred but uncertain.
- Cleanup recommendations for generic status, type, or category fields.
- Human approval markers for any generated SQL plan.

Expected modules:

- `transformation_analysis.py`

Exit criteria:

- The package can recommend transformation candidates without executing transformation SQL.

### Slice 0.4: Monitoring Snapshots

Write tests first for:

- Snapshot creation from a discovery report.
- Comparison between previous and current snapshots.
- New, persistent, and resolved data gaps.
- Human-readable monitoring summaries.
- Harness status fields for recurring monitoring runs.

Expected modules:

- `monitoring.py`

Exit criteria:

- Recurring agent runs can report what changed since the last analysis.

### Slice 1: Metadata Models and Formatting

Write tests first for:

- Table, column, relationship, and governance metadata models.
- Markdown formatting for one table, multiple tables, missing descriptions, and governance annotations.
- JSON formatting for agent runtimes that prefer structured context.
- Token-budget truncation that preserves table identifiers, column names, and safety notes.
- Stable snapshot output for representative table fixtures.

Expected modules:

- `models.py`
- `formatter.py`
- `token_budget.py`

Exit criteria:

- Remove or replace the formatter `xfail` in `tests/test_metadata_provider.py`.
- Add fixture-driven formatter tests under `tests/fixtures/`.

### Slice 2: Snowflake SQL Builders

Write tests first for:

- Safe fully qualified identifier handling.
- Quoting and validation for database, schema, table, and column names.
- Information schema table query generation.
- Information schema column query generation.
- Constraint and relationship query generation.
- Guardrails for unsupported wildcard or unsafe identifier input.

Expected modules:

- `identifiers.py`
- `snowflake_queries.py`

Exit criteria:

- SQL builders return deterministic SQL plus bind parameters where possible.
- Unsafe identifiers fail closed before reaching Snowflake.

### Slice 3: Metadata Provider

Write tests first for:

- Fake cursor execution order.
- Mapping table and column rows into typed models.
- Explicit table selection.
- Database/schema scope filtering.
- Empty catalog results.
- Snowflake connector exceptions surfaced with helpful package exceptions.
- Integration between repository rows, formatter output, and `TableContext`.

Expected modules:

- `metadata.py`
- `exceptions.py`
- `snowflake_repository.py`

Exit criteria:

- `SnowflakeMetadataProvider.describe_tables` returns real `TableContext` objects for fake cursor fixtures.
- The current provider `NotImplementedError` test is replaced with behavior tests.

### Slice 4: Redaction and Governance

Write tests first for:

- Sensitive name pattern redaction.
- Tag and masking-policy annotations.
- Governance metadata disabled by config.
- Sample values disabled by default.
- Sample values requiring explicit opt-in.
- Credential and connection-string values never appearing in formatted context or logs.

Expected modules:

- `redaction.py`
- `governance.py`

Exit criteria:

- Governance and redaction decisions are represented in formatter output.
- Tests prove metadata-only behavior remains the default.

### Slice 5: OpenAI SDK Extension Layer

Write tests first for:

- Wrapper preserves all OpenAI SDK keyword arguments.
- Wrapper returns the original SDK response object unchanged.
- Context is injected into instructions when instructions are provided.
- Context is prepended to input when instructions are absent.
- Provider errors fail closed with clear exceptions.
- Context can be built separately from making an OpenAI SDK call.

Expected modules:

- `openai_extensions.py`

Exit criteria:

- Remove or replace the OpenAI wrapper `xfail` in `tests/test_metadata_provider.py`.
- Wrapper tests use mocked callables only.

### Slice 6: Harness Persistence and Remote Writes

Write tests first for:

- Writing updated memory records locally.
- Writing updated status records locally.
- Optional writer protocols for S3 and GCS.
- Google Docs write behavior only if a clear authenticated-doc workflow is selected.
- Append-only memory mode versus overwrite status mode.
- Conflict behavior when remote status changed after startup.

Expected modules:

- `agent_harness_persistence.py`
- extensions to `agent_harness_locations.py`

Exit criteria:

- The harness can read remote context and persist local state safely.
- Remote writes remain opt-in and testable with fake clients.

### Slice 7: Harness CLI and Bootstrap UX

Write tests first for:

- CLI JSON output shape.
- CLI non-JSON summary output.
- Missing config file behavior.
- Remote reader unavailable warnings.
- Exit codes for recoverable warnings versus fatal configuration errors.
- Loading remote bootstrap config from a declared `locations.config` value.

Expected modules:

- `agent_harness_cli.py`
- possible `agent_harness_bootstrap.py`

Exit criteria:

- CLI behavior is contract-tested without invoking shell subprocesses where possible.
- Startup remains useful for first-run local repos with no `.agent_harness/` directory.

### Slice 8: Integration Tests

Write tests first for:

- Snowflake integration fixture creation when credentials are present.
- Automatic skipping when Snowflake environment variables are absent.
- Snapshot comparison for a tiny fixture schema.
- Optional mocked OpenAI SDK call that receives formatted context.
- Optional cloud integration smoke tests that skip unless explicit environment variables are set.

Integration tests should live under `tests/integration/` and must never require credentials to run the default test suite.

## Test Data and Fixtures

Add fixtures only when they make a test easier to read or preserve a stable contract.

Recommended fixture folders:

- `tests/fixtures/snowflake/` for table, column, constraint, and governance metadata rows.
- `tests/fixtures/formatter/` for expected Markdown and JSON context snapshots.
- `tests/fixtures/harness/` for memory, status, work queue, and session context examples.

Fixture data must not contain real credentials, customer data, or private warehouse metadata.

## Suggested Commands

```bash
uv run python -m pytest -q
uv run python -m pytest -q -rx
uv run python -m pytest tests/test_agent_harness.py -q
uv run python -m pytest tests/test_metadata_provider.py -q
uv run ruff check .
uv run mypy src
```
