# Architecture and Technical Specification

## 1. Purpose

This repository will provide Python extension helpers for the official OpenAI Python SDK that let coding agents use Snowflake table descriptions and metadata as reliable working context.

The goal is not to fork or replace the OpenAI SDK. The goal is to sit beside it with small, composable helpers that:

- Retrieve Snowflake schema and governance metadata.
- Normalize that metadata into strongly typed Python objects.
- Rank and compress it for a model context window.
- Attach the resulting context to OpenAI SDK requests, agent instructions, tool definitions, or local agent runtimes.

## 2. Primary Use Cases

- A coding agent needs to write SQL against a Snowflake warehouse and must understand table purpose, columns, comments, and relationships.
- A data engineer wants generated SQL to respect masking policies, tags, grants, and known sensitive fields.
- A model needs a compact description of relevant tables instead of an entire database catalog dump.
- A local development workflow needs reproducible metadata snapshots so tests and generated code are not dependent on live warehouse access.

## 3. Non-Goals

- Replace Snowflake access control or expose data the current Snowflake role cannot already see.
- Execute generated SQL automatically without explicit caller approval.
- Store Snowflake credentials in this package.
- Depend on private OpenAI SDK internals.
- Build a full semantic catalog product.

## 4. Package Shape

Proposed package:

```text
openai_snowflake_agent_context/
  __init__.py
  config.py
  metadata.py
  formatter.py
  cache.py
  openai_extensions.py
  snowflake_queries.py
  ranking.py
  redaction.py
```

Initial public API:

```python
from openai import OpenAI
from openai_snowflake_agent_context import (
    SnowflakeContextConfig,
    SnowflakeMetadataProvider,
    with_snowflake_context,
)

client = OpenAI()
provider = SnowflakeMetadataProvider(connection, SnowflakeContextConfig(...))

response = with_snowflake_context(
    client.responses.create,
    provider=provider,
    tables=["ANALYTICS.PUBLIC.ORDERS", "ANALYTICS.PUBLIC.CUSTOMERS"],
    model="gpt-4.1",
    input="Write a query for monthly repeat purchase rate.",
)
```

The extension should also expose lower-level helpers for users who want to manage OpenAI calls directly:

```python
context = provider.describe_tables(["ANALYTICS.PUBLIC.ORDERS"])
prompt_block = format_table_context(context, token_budget=4000)
```

## 5. Architecture

### 5.1 Components

`SnowflakeMetadataProvider`
: Coordinates metadata retrieval. Accepts a Snowflake connector connection and a `SnowflakeContextConfig`.

`SnowflakeMetadataRepository`
: Executes narrowly scoped metadata SQL. This should be kept separate from formatting and ranking logic.

`MetadataNormalizer`
: Converts Snowflake result rows into stable Pydantic or dataclass models.

`ContextRanker`
: Chooses relevant databases, schemas, tables, and columns based on explicit table names, user query text, recent usage, comments, name similarity, optional embeddings, and configured limits.

`ContextFormatter`
: Produces model-friendly Markdown or JSON blocks. It should preserve identifiers exactly and mark uncertain inferred relationships as inferred.

`GovernanceRedactor`
: Removes or annotates sensitive items according to policies, tags, masking information, and caller configuration.

`ContextCache`
: Caches metadata by account, role, database, schema, object name, and warehouse/catalog timestamp. Should support in-memory cache first, then optional local disk cache.

`OpenAIExtensionLayer`
: Provides wrapper functions that decorate `OpenAI` calls by injecting Snowflake context into request input or instructions. This layer must use public OpenAI SDK APIs only.

`SamplingHelper`
: Creates explicit random sample tables for workflows that need row-level examples. Sampling is opt-in, writes to a caller-provided destination table, and returns a status payload that downstream harness runs can use to reference the sampled table instead of the original source.

### 5.2 Data Flow

1. Caller creates a Snowflake connection using their normal credential flow.
2. Caller configures metadata scope and safety settings.
3. Provider retrieves Snowflake metadata from `INFORMATION_SCHEMA`, `ACCOUNT_USAGE`, `SHOW` commands, or `DESCRIBE` commands depending on role permissions and requested detail.
4. Repository returns raw rows.
5. Normalizer creates typed metadata objects.
6. Redactor removes disallowed or sensitive details.
7. Ranker selects the most relevant objects for the task and token budget.
8. Formatter emits agent-ready context.
9. OpenAI extension wrapper injects context into the SDK call.

## 6. Snowflake Metadata Sources

Use these sources in order of least surprising behavior:

- `INFORMATION_SCHEMA.TABLES`
- `INFORMATION_SCHEMA.COLUMNS`
- `INFORMATION_SCHEMA.VIEWS`
- `INFORMATION_SCHEMA.TABLE_CONSTRAINTS`
- `INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS`
- `INFORMATION_SCHEMA.KEY_COLUMN_USAGE`
- `ACCOUNT_USAGE.TABLES`
- `ACCOUNT_USAGE.COLUMNS`
- `ACCOUNT_USAGE.ACCESS_HISTORY`
- `SHOW TABLES`, `SHOW VIEWS`, `SHOW COLUMNS`
- `DESCRIBE TABLE`

Optional enrichment:

- Tags via `ACCOUNT_USAGE.TAG_REFERENCES`
- Masking policies via policy references where available
- Search optimization, clustering, row access policies, and retention settings
- Query history summaries for freshness and common joins

All metadata SQL must be parameterized where possible and must quote identifiers safely when dynamic identifiers are unavoidable.

## 7. Context Format

Default output should be Markdown because coding agents consume it well:

```markdown
## Snowflake Tables

### ANALYTICS.PUBLIC.ORDERS
- Type: TABLE
- Description: Customer order facts.
- Governance: contains PII tag on CUSTOMER_EMAIL; masked for current role.
- Freshness: updated daily.

Columns:
- ORDER_ID NUMBER primary key
- CUSTOMER_ID NUMBER foreign key candidate to CUSTOMERS.CUSTOMER_ID
- ORDER_DATE DATE
- TOTAL_AMOUNT NUMBER

Usage notes:
- Grain: one row per order.
- Prefer ORDER_DATE for monthly reporting.
```

JSON output should be available for agent frameworks that prefer structured tool context.

## 8. OpenAI SDK Extension Strategy

Avoid monkey-patching the `openai` package. Provide wrapper functions and typed utilities:

- `with_snowflake_context(callable, provider, *, input, instructions=None, tables=None, query=None, **kwargs)`
- `build_snowflake_context(provider, *, tables=None, query=None, token_budget=None)`
- `snowflake_context_tool(provider)` for agent runtimes that support callable tools.

The wrapper should:

1. Build context before the OpenAI call.
2. Merge context into `instructions` or prepend it to `input`, depending on the target API.
3. Preserve all caller-provided SDK arguments.
4. Return the original OpenAI SDK response type unchanged.

This keeps compatibility high as the official SDK evolves.

## 9. Safety and Governance Requirements

- Never bypass Snowflake role permissions.
- Never log credentials or full connection strings.
- Default to metadata only, not row samples.
- Require explicit opt-in for sample values.
- Require an explicit destination table for random sampling and surface that sampled table in harness status/context if present.
- Redact or annotate columns with sensitive tags, masking policies, or names matching configured sensitive patterns.
- Include the active Snowflake role and database scope in debug metadata so users can diagnose missing catalog objects.
- Make context injection visible to callers through optional debug output.

## 10. Configuration

`SnowflakeContextConfig` should support:

- `account`, `user`, `role`, `warehouse`, `database`, `schema`
- `include_tables`, `exclude_tables`
- `include_views`
- `include_governance`
- `include_samples`
- `max_tables`
- `max_columns_per_table`
- `token_budget`
- `cache_ttl_seconds`
- `output_format`: `markdown` or `json`
- `sensitive_name_patterns`

## 10.1 Table Sampling

The table sampling helper should remain separate from metadata retrieval. The initial contract is:

```python
from openai_snowflake_agent_context import sample_table

result = sample_table(
    connection,
    "ANALYTICS.PUBLIC.ORDERS",
    "ANALYTICS.PUBLIC.ORDERS_SAMPLE",
)
```

The generated Snowflake SQL uses `CREATE OR REPLACE TABLE <destination> AS SELECT * FROM <source> SAMPLE BERNOULLI (1)` by default. Identifiers are quoted segment by segment, and `sample_percent` must be greater than zero and less than or equal to 100.

The result includes `sampled_table`/`destination_table` fields intended for `.agent_harness/status.json`. When these fields are present, startup scripts should reference the sampled table in generated context so later agents analyze the sample table intentionally.

## 11. Caching

Phase 1 should use an in-memory TTL cache.

Phase 2 can add optional disk cache with explicit path configuration. Cache keys should include:

- Snowflake account
- Role
- Database
- Schema
- Object identifier
- Metadata source version
- Package version

Cached content must not include credentials. If sample values are ever cached, that must require a separate explicit opt-in.

## 12. Testing Strategy

Unit tests:

- SQL builder quotes identifiers correctly.
- Normalizer handles missing comments and Snowflake type variants.
- Formatter respects token budgets.
- Redactor masks sensitive metadata.
- OpenAI wrapper preserves SDK arguments and response objects.

Integration tests:

- Run against a disposable Snowflake database/schema when credentials are available.
- Skip automatically when Snowflake environment variables are missing.
- Use fixtures that create minimal tables, comments, tags, and relationships.

Contract tests:

- Verify generated context remains stable for snapshot fixtures.
- Verify wrappers work with mocked OpenAI SDK methods.

## 13. Implementation Phases

### Phase 1: Local Metadata Context

- Implement config models.
- Implement metadata models.
- Implement Snowflake information schema queries.
- Implement Markdown formatter.
- Implement in-memory cache.
- Add unit tests and fixture-based snapshot tests.

### Phase 2: OpenAI SDK Wrappers

- Implement `build_snowflake_context`.
- Implement `with_snowflake_context`.
- Support Responses API-style calls first.
- Add mocked OpenAI SDK tests.

### Phase 3: Ranking and Token Budgeting

- Add query/table relevance scoring.
- Add token-aware truncation.
- Add optional metadata embeddings for larger warehouses.
- Add compact relationship summaries.

### Phase 4: Governance and Operational Hardening

- Add tags, policies, grants, and access history enrichment.
- Add configurable redaction.
- Add disk cache.
- Add structured logs with credential-safe fields only.

## 14. Open Questions

- Should table relationship inference be limited to declared constraints only, or should it include naming heuristics?
- Should the package ship a CLI for generating offline metadata snapshots?
- Should sample values be entirely excluded from the first release?
- Which OpenAI SDK API surface should be the first-class wrapper target: Responses API, Assistants-like agent runtime, or generic callable wrapper?

## 15. Acceptance Criteria for First Release

- A user can connect to Snowflake with an existing connector connection.
- A user can request context for specific tables.
- The package returns concise Markdown context with table comments, column names, types, comments, and primary/foreign key information where available.
- A wrapper can inject that context into an OpenAI SDK call without changing the response type.
- Tests cover formatting, redaction, SQL building, and wrapper behavior.
- No credentials are logged or cached.
