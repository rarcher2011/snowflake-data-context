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

This project uses [uv](https://docs.astral.sh/uv/) for Python version management, dependency syncing, virtual environments, and command execution.

Install uv if it is not already available:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Sync the development environment:

```bash
uv sync --extra dev
```

If your runner cannot write to the default uv cache, use a project-local cache:

```bash
UV_CACHE_DIR=.uv-cache uv sync --extra dev
```

Run the local verification suite:

```bash
uv run python -m pytest -q
uv run ruff check .
uv run mypy src
```

## Set Up This Extension

### 1. Clone and install

Clone the repository and sync the package into uv-managed project environment:

```bash
git clone https://github.com/rarcher2011/snowflake-data-context.git
cd snowflake-data-context

uv sync
```

For local development and tests, install the development extra:

```bash
uv sync --extra dev
```

Optional extras are available for specific deployment and integration paths:

```bash
uv sync --extra cloud
uv sync --extra chatgpt-plugin
uv sync --extra aws
```

### 2. Configure Snowflake credentials

Use Snowflake key-pair authentication for this extension. Do not store Snowflake passwords in this repository or pass a `password` value into the package helpers.

Before running the Python setup, create a Snowflake-supported RSA key pair and assign the public key to the Snowflake user. Snowflake requires at least a 2048-bit RSA key pair, and the private key should be stored in PEM/PKCS#8 format.

Example key generation commands:

```bash
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out rsa_key.p8 -nocrypt
openssl rsa -in rsa_key.p8 -pubout -out rsa_key.pub
```

Assign the public key to the Snowflake user after removing the PEM header, footer, and line breaks:

```sql
ALTER USER your_user SET RSA_PUBLIC_KEY='MIIBIjANBgkqh...';
```

Set the connection scope and private key path with environment variables or your normal secret manager:

```bash
export SNOWFLAKE_ACCOUNT="your-account"
export SNOWFLAKE_USER="your-user"
export SNOWFLAKE_WAREHOUSE="your-warehouse"
export SNOWFLAKE_DATABASE="ANALYTICS"
export SNOWFLAKE_SCHEMA="PUBLIC"
export SNOWFLAKE_PRIVATE_KEY_PATH="$HOME/.ssh/snowflake_rsa_key.p8"
export SNOWFLAKE_PRIVATE_KEY_PASSPHRASE="optional-passphrase"
```

Create a Snowflake connector connection with the private-key helper:

```python
import os

from openai_snowflake_agent_context import (
    SnowflakeContextConfig,
    SnowflakeMetadataProvider,
    connect_with_private_key,
)

config = SnowflakeContextConfig(
    account=os.environ["SNOWFLAKE_ACCOUNT"],
    user=os.environ["SNOWFLAKE_USER"],
    warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
    database=os.environ.get("SNOWFLAKE_DATABASE"),
    schema=os.environ.get("SNOWFLAKE_SCHEMA"),
    private_key_path=os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"],
)

connection = connect_with_private_key(
    config,
    private_key_passphrase=os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"),
)

provider = SnowflakeMetadataProvider(connection, config)
```

If your application already manages Snowflake connections, it can keep doing that. The provider only requires a connection object with `cursor()`. The included helper is for teams that want a standard private-key setup path.

### 3. Run metadata and description analysis

Use the provider-level methods when live Snowflake metadata retrieval is available, or use the lower-level helpers with existing table metadata objects:

```python
analysis = provider.analyze_schema_descriptions()

analysis.print_context()

for column in analysis.columns_needing_improvement:
    print(column.table_identifier, column.column_name, column.result.recommendation)
```

For local tests or offline analysis, pass `TableContext` objects directly to `analyze_table_metadata_descriptions`.

### 4. Suggest column descriptions from sample records

When a human explicitly wants row-level examples used as context, the provider can fetch a small random sample, call the OpenAI SDK, and return reviewable column description suggestions:

```python
from openai import OpenAI

client = OpenAI()

suggestions = provider.suggest_column_descriptions(
    "ANALYTICS.PUBLIC.ORDERS",
    client,
    model="gpt-4.1-mini",
    sample_size=5,
)

print(suggestions.column_descriptions)
```

Review suggested descriptions before applying them through `provider.update_descriptions(...)`.

### 5. Review description updates before applying

Description updates are planned first and applied only when explicitly requested:

```python
from openai_snowflake_agent_context import DescriptionUpdateRequest

result = provider.update_descriptions(
    [
        DescriptionUpdateRequest(
            table="ANALYTICS.PUBLIC.ORDERS",
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

Set `apply=True` only after a human has reviewed the generated Snowflake `COMMENT` statements.

### 6. Configure the long-running harness

Create an `agent_harness.toml` file at the repo root:

```toml
[repo]
path = "."

[paths]
memory_dir = ".agent_harness/memory"
status_file = ".agent_harness/status.json"
work_file = ".agent_harness/work.md"
session_context_file = ".agent_harness/session_context.md"
```

Create optional starter files:

```bash
mkdir -p .agent_harness/memory
printf '%s\n' '- [ ] WORK-1: Run metadata discovery for the analytics schema' > .agent_harness/work.md
printf '%s\n' '{"work_id": "WORK-1", "status": "pending"}' > .agent_harness/status.json
```

Start a session:

```bash
uv run scripts/start_agent_harness.py
```

The harness writes `.agent_harness/session_context.md`, which future agents can read before continuing long-running analysis.

### 7. Route work through the orchestrator layer

Use the orchestrator layer after harness startup to decide which specialist agent should handle the next unit of work:

```python
from openai_snowflake_agent_context import AgentOrchestrator
from openai_snowflake_agent_context.agent_harness import initialize_agent_session

report = initialize_agent_session("agent_harness.toml")
decision = AgentOrchestrator().plan_from_harness_report(report)

print(decision.to_markdown())
```

For coordinated work that should be split across specialists, build a multi-agent plan:

```python
plan = AgentOrchestrator().plan_multi_agent_from_harness_report(report)

for assignment in plan.ready_assignments():
    print(assignment.assignment_id, assignment.agent.role_id, assignment.description)
```

The default roles route metadata discovery, transformation planning, quality review, stakeholder questions, and coordination work. Decisions and multi-agent plans can be serialized into harness status files or ChatGPT Action responses.

### 8. Serve ChatGPT Actions locally

Install the optional server dependencies:

```bash
uv sync --extra chatgpt-plugin
```

Create a small FastAPI app:

```python
from openai_snowflake_agent_context.chatgpt_plugin import create_app

app = create_app("https://your-public-action-host.example.com")
```

Run it with Uvicorn:

```bash
uv run --extra chatgpt-plugin uvicorn --factory openai_snowflake_agent_context.chatgpt_plugin:create_app
```

For production ChatGPT Actions, deploy behind a public HTTPS URL and provide the generated `GET /openapi.json` schema.

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
Use `analysis.to_context_markdown()` or `analysis.print_context()` to produce a human-readable report that can also be passed to an LLM as schema context.

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

print(analysis.to_context_markdown())
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
