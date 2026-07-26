# Architecture and Technical Specification

## 1. Purpose

This repository will provide Python extension helpers and long-running agent harness patterns that help small and mid-sized businesses use Snowflake data more effectively. The immediate technical foundation is Snowflake metadata context for OpenAI SDK workflows. The broader product goal is to support data discovery, analysis, transformation planning, monitoring, and feedback loops for teams that have some technical resources but limited analyst capacity.

The goal is not to fork or replace the OpenAI SDK. The goal is to sit beside it with small, composable helpers that let agents:

- Retrieve Snowflake schema and governance metadata.
- Normalize that metadata into strongly typed Python objects.
- Rank and compress it for a model context window.
- Attach the resulting context to OpenAI SDK requests, agent instructions, tool definitions, or local agent runtimes.
- Identify metadata gaps, data issues, and transformation opportunities.
- Preserve analysis memory, status, and unresolved work across long-running agent sessions.
- Produce human-readable progress updates for teams that need visibility but do not have a dedicated analytics operations function.

## 2. Primary Use Cases

- A coding agent needs to write SQL against a Snowflake warehouse and must understand table purpose, columns, comments, and relationships.
- A small business needs to discover which Snowflake tables are useful and trustworthy before asking an agent to analyze or transform them.
- A company has one overloaded analyst and needs automated triage of metadata gaps, data issues, and future analysis work.
- A data engineer wants generated SQL to respect masking policies, tags, grants, and known sensitive fields.
- A model needs a compact description of relevant tables instead of an entire database catalog dump.
- A local development workflow needs reproducible metadata snapshots so tests and generated code are not dependent on live warehouse access.
- A long-running analysis needs continuity across context windows, restarts, and handoffs.

## 3. Non-Goals

- Replace Snowflake access control or expose data the current Snowflake role cannot already see.
- Execute generated SQL automatically without explicit caller approval.
- Store Snowflake credentials in this package.
- Depend on private OpenAI SDK internals.
- Build a full semantic catalog product.
- Replace analyst judgment, business stakeholder review, or formal data governance processes.
- Automatically deploy data transformations without explicit human approval.

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
  analytics_models.py
  discovery_report.py
  analytics_backlog.py
  transformation_analysis.py
  monitoring.py
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

`DiscoveryReportBuilder`
: Aggregates table metadata, description quality, sampling status, and governance hints into an analyst-readable discovery report for a database, schema, or business domain.

`DataGapAnalyzer`
: Converts missing descriptions, weak descriptions, unclear grain, stale metadata, missing relationships, and other catalog signals into prioritized data gaps.

`TransformationPlanner`
: Uses metadata and optional sampled-table context to recommend reviewable transformation candidates, such as staging models, cleanup rules, reporting views, and relationship checks.

`MonitoringSnapshotStore`
: Persists recurring metadata-health and data-gap snapshots so agents can compare current state with previous runs.

`AnalyticsWorkOrchestrator`
: Turns discovery findings into work items, tracks unresolved issues, and updates long-running harness state for future agent sessions.

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

### 5.3 SMB Analytics Data Flow

The target SMB analytics loop sits above the raw metadata flow:

1. Agent starts from harness memory, status, and configured work.
2. Provider retrieves metadata for the configured Snowflake scope.
3. Description analysis scores table and column readiness.
4. Discovery report groups tables, weak documentation, governance warnings, and unknowns.
5. Data gap analyzer creates prioritized gaps and recommendations.
6. Transformation planner proposes reviewable transformation candidates when enough context exists.
7. Monitoring snapshot compares current findings with previous runs.
8. Harness records active goals, unresolved gaps, sampled tables, and next work items.
9. Progress updates communicate what changed and what still needs human review.

Metadata remains the source input. Analyst-ready work products are the output.

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

## 7.1 Discovery Report Format

Discovery reports should be readable by both humans and agents. A report should include:

- Scope: account, role, database, schema, and selected tables.
- Summary: tables scanned, columns scanned, coverage metrics, and high-priority findings.
- Data gaps: missing descriptions, weak descriptions, unclear ownership, unclear grain, missing relationships, stale metadata, or governance warnings.
- Recommended next work: analyst tasks, engineering tasks, stakeholder questions, and safe agent-delegable actions.
- Sampling status: whether a sampled table exists and whether row-level analysis was explicitly requested.
- Transformation candidates: proposed views, staging models, cleanup rules, or relationship validations.
- Monitoring context: new, persistent, and resolved gaps compared with a previous snapshot.

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
- Distinguish metadata observations from inferred business meaning.
- Keep discovery reports and monitoring snapshots free of raw sensitive row data unless the caller explicitly opts in.
- Mark transformation recommendations as plans until a human confirms execution.

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

## 10.2 SMB Analytics Configuration

Future configuration should support analytics-operating settings in addition to Snowflake connection scope:

- `business_domain`: optional domain label such as finance, sales, operations, product, or support.
- `analysis_goal`: the current long-running analysis objective.
- `monitoring_frequency`: advisory cadence for recurring checks.
- `gap_priority_threshold`: minimum priority to include in human-facing reports.
- `transformation_mode`: `off`, `recommend_only`, or `plan_sql`.
- `progress_audience`: intended reader for status updates, such as analyst, engineer, executive, or client.
- `stakeholder_questions_enabled`: whether reports should include business questions that need human answers.

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
