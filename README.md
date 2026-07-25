# OpenAI Snowflake Agent Context

Python extension helpers for enriching OpenAI SDK coding-agent workflows with Snowflake table descriptions, schema metadata, relationship hints, and governance context.

The package is intended to make Snowflake metadata easy to retrieve, compact, cache, and attach to OpenAI model/tool calls so coding agents can generate safer SQL, understand warehouse structure, and reason about existing analytical assets.

## Planned Capabilities

- Discover Snowflake databases, schemas, tables, views, columns, comments, tags, policies, grants, and freshness signals.
- Convert Snowflake metadata into concise agent-ready context blocks.
- Provide extension-style helpers around the official `openai` Python SDK without forking it.
- Support explicit table selection, semantic search over metadata, and token-budgeted context packing.
- Offer safe defaults for credential handling, query limits, caching, and governance-aware redaction.
- Analyze table and column description quality so agents can identify metadata gaps that weaken SQL generation and analysis.
- Create explicit Snowflake sample tables for analysis workflows that need row-level examples.

See [docs/ARCHITECTURE_TECH_SPEC.md](docs/ARCHITECTURE_TECH_SPEC.md) for the implementation plan and technical specification.

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

## Long-Running Agent Harness

This repository includes a file-based startup harness for long-running coding agents and analysis sessions. It recovers the latest memory file, status JSON, and configured work queue, then writes a compact session context file for the next agent context window.

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
