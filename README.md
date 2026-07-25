# OpenAI Snowflake Agent Context

OpenAI Snowflake Agent Context helps small and mid-sized businesses use coding agents for data discovery, analysis, and data transformation work in Snowflake.

Many companies have enough technical resources to maintain a data warehouse, but not enough analyst capacity to answer every data question, document every table, monitor every data quality issue, and keep every transformation backlog moving. This repo is designed for those teams: companies with part-time data support, one overloaded analyst, or engineers who understand the systems but cannot spend all day doing ad hoc analysis.

The package makes Snowflake metadata, table descriptions, sample tables, and long-running agent memory available to OpenAI SDK workflows so agents can understand warehouse structure, ask better questions, generate safer SQL, and keep analysis work moving across sessions.

## Problem Being Solved

Small and mid-sized businesses often face the same data problems as larger companies, but without a dedicated data platform team:

- Important tables exist, but nobody knows which ones are trustworthy.
- Column and table descriptions are missing, stale, or too vague for reliable analysis.
- A single analyst becomes the bottleneck for dashboards, SQL requests, data cleanup, and business questions.
- Engineers can help, but they need context before they can safely transform data or explain what it means.
- Data quality issues and documentation gaps are found once, then forgotten because there is no continuous follow-up loop.
- Analysis work spans days or weeks, but AI agents often lose continuity between context windows.

This repo aims to turn those problems into agent-friendly workflows: discover the data estate, analyze metadata quality, sample tables when row-level examples are explicitly needed, document gaps, recommend next steps, and preserve enough memory for long-running analysis to continue coherently.

## Intended Users

- Small and mid-sized businesses using Snowflake without a large analytics team.
- Teams with one analyst who needs help triaging requests and monitoring metadata quality.
- Engineering teams that own data pipelines but need better discovery and analysis support.
- Consultants or fractional data teams supporting multiple clients.
- Agentic coding workflows that need structured warehouse context before generating SQL or transformations.

## What This Enables

- Discover Snowflake databases, schemas, tables, views, columns, comments, tags, policies, grants, and freshness signals.
- Analyze table and column description quality so teams can see where metadata gaps weaken discovery and analysis.
- Generate reviewable Snowflake description updates from user-provided improvements.
- Create explicit random sample tables for analysis workflows that need row-level examples.
- Preserve long-running analysis context with local or cloud-backed memory, status, work queues, and progress updates.
- Continuously monitor and report on data gaps, documentation issues, and future feature opportunities.
- Attach compact Snowflake context to OpenAI SDK workflows without forking or monkey-patching the official SDK.

## Core Capabilities

- Discover Snowflake databases, schemas, tables, views, columns, comments, tags, policies, grants, and freshness signals.
- Convert Snowflake metadata into concise agent-ready context blocks.
- Provide extension-style helpers around the official `openai` Python SDK without forking it.
- Support explicit table selection, semantic search over metadata, and token-budgeted context packing.
- Offer safe defaults for credential handling, query limits, caching, and governance-aware redaction.
- Analyze table and column description quality so agents can identify metadata gaps that weaken SQL generation and analysis.
- Create explicit Snowflake sample tables for analysis workflows that need row-level examples.
- Maintain coherent long-running agent sessions with memory, status, work intake, and human-readable progress updates.

See [docs/SMB_ANALYTICS_WORKFLOWS.md](docs/SMB_ANALYTICS_WORKFLOWS.md) for the target SMB analytics workflows and [docs/ARCHITECTURE_TECH_SPEC.md](docs/ARCHITECTURE_TECH_SPEC.md) for the implementation plan and technical specification.

## Quick Start

Install the package in editable mode while the SDK extension is under active development:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

Run the local verification suite:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src
```

## Core Workflows

Use the SDK extension in three main workflows:

1. Analyze Snowflake metadata descriptions to find weak or missing documentation.
2. Generate reviewed Snowflake `COMMENT` statements from user-provided improvements.
3. Preserve long-running agent context with local or cloud-backed harness state.
4. Create sampled tables for deeper analysis when metadata alone is not enough.
5. Monitor unresolved data gaps, issues, and future feature requests over time.

The long-term target is an agent-assisted analytics loop: discover data, identify gaps, recommend analyst or engineering work, carry context forward, and provide human-readable updates until the work is resolved.

## Target Roadmap

- Add typed discovery reports for Snowflake schemas and business domains.
- Add first-class data gap, data issue, recommendation, and transformation candidate models.
- Extend the harness status format to track unresolved data gaps and active analysis goals.
- Add monitoring snapshots that compare current metadata health with previous runs.
- Expose discovery reports and monitoring summaries through ChatGPT Actions and deployable service endpoints.

## Long-Running Agent Harness

This repository includes a file-based startup harness for long-running coding agents and analysis sessions. It recovers the latest memory file, status JSON, and configured work queue, then writes a compact session context file for the next agent context window.

For SMB analytics work, the harness is the continuity layer. It helps agents remember what was already investigated, what remains incomplete, which data gaps were found, whether a sampled table should be used, and what progress should be reported back to humans. This makes the repo useful for analysis that runs longer than one chat, one ticket, or one analyst work session.

See [docs/LONG_RUNNING_AGENT_HARNESS.md](docs/LONG_RUNNING_AGENT_HARNESS.md) for usage and file formats.

## Metadata Description Analysis

The SDK extension exposes `analyze_table_metadata_descriptions` for scoring table and column descriptions in existing `TableContext` objects. `SnowflakeMetadataProvider.analyze_schema_descriptions()` delegates through `describe_tables(None)` so the intended workflow is to analyze every table returned for the configured schema.

The analysis reports description coverage, weak or missing column descriptions, quality scores, issues, and improvement recommendations.

```python
from openai_snowflake_agent_context import analyze_table_metadata_descriptions
from openai_snowflake_agent_context.metadata import TableContext

analysis = analyze_table_metadata_descriptions(
    [
        TableContext(
            database="ANALYTICS",
            schema="PUBLIC",
            name="ORDERS",
            kind="TABLE",
            description="Order fact table with one row per customer order.",
            columns=(
                "ORDER_ID NUMBER -- Unique identifier from the commerce system.",
                "CUSTOMER_ID NUMBER",
            ),
            context_markdown="",
        )
    ]
)

print(analysis.columns_needing_improvement)
```

## Snowflake Description Updates

Use `DescriptionUpdateRequest` with `SnowflakeMetadataProvider.update_descriptions(...)` to turn user-provided table and column descriptions into validated Snowflake `COMMENT ON TABLE` and `COMMENT ON COLUMN` statements. The method defaults to `apply=False` so callers can review SQL before writing to Snowflake; pass `apply=True` only when the user explicitly confirms execution.

```python
from openai_snowflake_agent_context import DescriptionUpdateRequest

result = provider.update_descriptions(
    [
        DescriptionUpdateRequest(
            table="ORDERS",
            table_description="Order fact table with one row per customer order.",
            column_descriptions={
                "CUSTOMER_ID": "Customer identifier used to join account activity.",
            },
        )
    ],
    apply=False,
)

for statement in result.plan.statements:
    print(statement.sql)
```

## Snowflake Table Sampling

The SDK extension exposes `sample_table` for creating a random Snowflake sample table from a source table:

```python
from openai_snowflake_agent_context import sample_table

result = sample_table(
    connection,
    "ANALYTICS.PUBLIC.ORDERS",
    "ANALYTICS.PUBLIC.ORDERS_SAMPLE",
)
```

By default the helper executes a random one percent `SAMPLE BERNOULLI (1)` into the destination table. The returned status payload includes `sampled_table`, which the long-running harness can surface in later startup summaries and session context files.

## ChatGPT Actions Plugin

The package includes an optional ChatGPT Actions/OpenAPI adapter so ChatGPT can execute selected SDK extension methods over HTTP. See [docs/CHATGPT_PLUGIN_ACTIONS.md](docs/CHATGPT_PLUGIN_ACTIONS.md).

## AWS Deployment

Use `scripts/deploy_aws.py` to package and deploy the ChatGPT Actions adapter to AWS Lambda with a Lambda Function URL. See [docs/AWS_DEPLOYMENT.md](docs/AWS_DEPLOYMENT.md).

## Status

In progress
