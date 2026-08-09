# Data Analyst Agent Flows

This guide shows how to use `openai-snowflake-agent-context` as the context and orchestration layer for a Snowflake-grounded data analyst agent.

The SDK extension does not replace the OpenAI Python SDK. It prepares Snowflake metadata, description-quality analysis, orchestration context, eval inputs, and reviewable follow-up work so an OpenAI-powered agent has useful grounding before it writes SQL or recommends analysis.

## 1. Connect To Snowflake

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

Create the provider:

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

## 2. Run A Data Analyst Agent

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

The flow pulls Snowflake metadata, scores table and column descriptions, builds LLM-readable context, routes the work through the orchestrator, and calls `client.responses.create(...)`.

## 3. Build Context Without Calling OpenAI

```python
from openai_snowflake_agent_context import build_data_analyst_context

context = build_data_analyst_context(
    provider,
    "What data gaps block customer order analysis?",
    table_names=("ANALYTICS.PUBLIC.ORDERS",),
)

print(context.to_markdown())
```

## 4. Create An OpenAI Eval Run

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

## 5. Build A Multi-Agent Analyst Plan

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

The default multi-agent plan creates metadata, quality-review, and SQL-planning assignments. Quality and SQL assignments depend on metadata analysis.

## Safety Defaults

- Metadata-only analysis is the default.
- Sampling rows requires an explicit method call.
- Description updates are dry-run by default.
- Generated SQL and Snowflake `COMMENT` statements should be reviewed before execution.
- The data analyst prompt tells the model not to invent tables or columns.
