# Test-Driven Development Plan

## Purpose

This document defines the test-first path for building the Snowflake metadata context extension. The project should add behavior by writing or enabling tests before implementation code.

## Testing Principles

- Keep live Snowflake and OpenAI calls out of unit tests.
- Use fake connections, fake cursors, and fixture rows for metadata behavior.
- Treat formatter snapshots as contract tests because coding agents depend on stable context shape.
- Mark future behavior with `xfail` only when the intended API is useful to document now and implementation is intentionally deferred.
- Prefer small modules with narrow tests over broad end-to-end tests during early implementation.

## Current Initial Tests

- `tests/test_public_api.py` verifies the exported package surface.
- `tests/test_config.py` verifies safe default configuration and immutability.
- `tests/test_metadata_provider.py` verifies the current provider contract, the `TableContext` data object, and two future API outlines.

## TDD Phases

### Phase 1: Metadata Models and Formatting

Write tests first for:

- Table, column, relationship, and governance metadata models.
- Markdown formatting for one table, multiple tables, no description, and governance annotations.
- Token-budget truncation that preserves table identifiers and column names.

Expected modules:

- `formatter.py`
- `models.py`
- `token_budget.py`

### Phase 2: Snowflake SQL Builders

Write tests first for:

- Safe fully qualified identifier handling.
- Information schema table query generation.
- Information schema column query generation.
- Constraint and relationship query generation.
- Guardrails for unsupported wildcard or unsafe identifier input.

Expected modules:

- `snowflake_queries.py`
- `identifiers.py`

### Phase 3: Metadata Provider

Write tests first for:

- Fake cursor execution order.
- Mapping table and column rows into typed models.
- Explicit table selection.
- Database/schema scope filtering.
- Empty catalog results.
- Snowflake connector exceptions surfaced with helpful package exceptions.

Expected modules:

- `metadata.py`
- `exceptions.py`

### Phase 4: Redaction and Governance

Write tests first for:

- Sensitive name pattern redaction.
- Tag and masking-policy annotations.
- Governance metadata disabled by config.
- Sample values disabled by default.
- Sample values requiring explicit opt-in.

Expected modules:

- `redaction.py`
- `governance.py`

### Phase 5: OpenAI SDK Extension Layer

Write tests first for:

- Wrapper preserves all OpenAI SDK keyword arguments.
- Wrapper returns the original SDK response object unchanged.
- Context is injected into instructions when instructions are provided.
- Context is prepended to input when instructions are absent.
- Provider errors fail closed with clear exceptions.

Expected modules:

- `openai_extensions.py`

### Phase 6: Integration Tests

Write tests first for:

- Snowflake integration fixture creation when credentials are present.
- Automatic skipping when Snowflake environment variables are absent.
- Snapshot comparison for a tiny fixture schema.
- Optional mocked OpenAI SDK call that receives formatted context.

Integration tests should live under `tests/integration/` and must never require credentials to run the default test suite.

## Suggested Commands

```bash
pytest
pytest -q -rx
pytest tests/test_metadata_provider.py
```

