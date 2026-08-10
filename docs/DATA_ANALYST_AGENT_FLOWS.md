# Data Analyst Agent Flows

This guide shows how to use `openai-snowflake-agent-context` as the context and orchestration layer for a Snowflake-grounded data analyst agent.

The SDK extension does not replace the OpenAI Python SDK. It prepares Snowflake metadata, description-quality analysis, orchestration context, eval inputs, sample-record description suggestions, and reviewable follow-up work so an OpenAI-powered agent has useful grounding before it writes SQL or recommends analysis.

## 1. Install And Configure

Install the package in a project that also has access to Snowflake credentials:

```bash
uv add openai-snowflake-agent-context
```

Set Snowflake and OpenAI environment variables:

```bash
export OPENAI_API_KEY="..."
export SNOWFLAKE_ACCOUNT="your-account"
export SNOWFLAKE_USER="your-user"
export SNOWFLAKE_WAREHOUSE="agent_wh"
export SNOWFLAKE_DATABASE="ANALYTICS"
export SNOWFLAKE_SCHEMA="PUBLIC"
export SNOWFLAKE_PRIVATE_KEY_PATH="$HOME/.ssh/snowflake_rsa_key.p8"
export SNOWFLAKE_PRIVATE_KEY_PASSPHRASE="optional-passphrase"
```

The Snowflake connection helper uses private key authentication. If your application already manages Snowflake connections, pass that connection directly to `SnowflakeMetadataProvider`.

## 2. Connect To Snowflake

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
    database=os.environ["SNOWFLAKE_DATABASE"],
    schema=os.environ["SNOWFLAKE_SCHEMA"],
    private_key_path=os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"],
)

connection = connect_with_private_key(
    config,
    private_key_passphrase=os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"),
)

provider = SnowflakeMetadataProvider(connection, config)
```

## 3. Run A Single Data Analyst Agent

Use `run_data_analyst_agent` when you want one OpenAI call grounded in current Snowflake metadata and orchestrator context:

```python
from openai import OpenAI

from openai_snowflake_agent_context import run_data_analyst_agent

client = OpenAI()

result = run_data_analyst_agent(
    openai_client=client,
    provider=provider,
    question="Which order fields need better descriptions before writing reporting SQL?",
    model="gpt-4.1",
    table_names=("ANALYTICS.PUBLIC.ORDERS",),
)

print(result.response_text)
```

The flow:

- pulls Snowflake table and column metadata
- scores table and column descriptions
- builds LLM-readable schema context
- routes the question through the orchestrator
- calls `client.responses.create(...)`
- returns the model response plus the context used for the request

## 4. Build Context Without Calling OpenAI

Use this when another runtime owns the OpenAI call:

```python
from openai_snowflake_agent_context import build_data_analyst_context

context = build_data_analyst_context(
    provider,
    "What data gaps block customer order analysis?",
    table_names=("ANALYTICS.PUBLIC.ORDERS",),
)

print(context.to_markdown())
```

## 5. Create An OpenAI Eval Run

Create an eval in the OpenAI platform first, then use its eval ID to run the data analyst agent against Snowflake-grounded questions:

```python
from openai_snowflake_agent_context import create_data_analyst_eval_run

eval_run = create_data_analyst_eval_run(
    openai_client=client,
    provider=provider,
    eval_id="eval_...",
    run_name="orders-agent-regression",
    model="gpt-4.1",
    table_names=("ANALYTICS.PUBLIC.ORDERS",),
    questions=(
        "Which columns need better descriptions before an agent writes SQL?",
        "What data quality risks should be checked before creating an orders mart?",
    ),
    expected_outputs=(
        "Mention weak or missing descriptions.",
        "Mention review of totals and status values.",
    ),
)

print(eval_run.eval_run)
```

The helper builds a `completions` eval data source with `file_content` items. Each item includes the analyst question, Snowflake metadata context, orchestration context, and optional expected output.

## 6. Build A Multi-Agent Analyst Plan

Use the multi-agent flow when the work should be split across metadata analysis, quality review, and SQL or transformation planning:

```python
from openai_snowflake_agent_context import build_data_analyst_multi_agent_plan

plan = build_data_analyst_multi_agent_plan(
    provider,
    "Create an orders reporting view and identify quality risks.",
    table_names=("ANALYTICS.PUBLIC.ORDERS",),
)

for assignment in plan.ready_assignments():
    print(assignment.assignment_id, assignment.agent.role_id, assignment.description)
```

By default, the generated assignments are:

- metadata analysis
- data quality review
- SQL or transformation planning

Quality and SQL assignments depend on metadata analysis, so a runner can execute ready assignments first and then continue with dependent work after the metadata assignment completes.

## 7. Suggest Column Descriptions From Sample Records

When a human explicitly approves row-level examples, use the sample-record description flow:

```python
suggestions = provider.suggest_column_descriptions(
    "ANALYTICS.PUBLIC.ORDERS",
    client,
    model="gpt-4.1-mini",
    sample_size=5,
)

print(suggestions.column_descriptions)
```

Review suggestions before applying them:

```python
from openai_snowflake_agent_context import DescriptionUpdateRequest

result = provider.update_descriptions(
    [
        DescriptionUpdateRequest(
            table="ANALYTICS.PUBLIC.ORDERS",
            column_descriptions=suggestions.column_descriptions,
        )
    ],
    apply=False,
)

for statement in result.plan.statements:
    print(statement.sql)
```

Only pass `apply=True` after a human reviews the generated Snowflake `COMMENT` statements.

## 8. Long-Running Agent Sessions

For recurring or long-running analysis, combine these flows with the harness:

```python
from openai_snowflake_agent_context.agent_harness import initialize_agent_session
from openai_snowflake_agent_context import AgentOrchestrator

report = initialize_agent_session("agent_harness.toml")
plan = AgentOrchestrator().plan_multi_agent_from_harness_report(report)

print(plan.to_markdown())
```

The harness restores memory, status, and the next work item. The orchestrator turns that state into specialist assignments that can be handed to one or more agents.

## Safety Defaults

- Metadata-only analysis is the default.
- Sampling rows requires an explicit method call and sample size.
- Description updates are dry-run by default.
- Generated SQL and Snowflake `COMMENT` statements should be reviewed before execution.
- The data analyst prompt tells the model not to invent tables or columns.
