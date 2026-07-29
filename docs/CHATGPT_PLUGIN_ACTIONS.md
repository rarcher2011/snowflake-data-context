# ChatGPT Actions Plugin

This repository includes a small ChatGPT Actions/OpenAPI adapter for executing selected SDK extension methods over HTTP. The current adapter exposes low-level metadata, sampling, and progress helpers. The target SMB analytics roadmap should add higher-level actions for discovery reports, data gap summaries, transformation recommendations, and monitoring snapshots.

## Exposed Methods

- `POST /metadata/description-analysis`
  - Calls `analyze_table_metadata_descriptions`.
  - Accepts table metadata payloads and returns description coverage, quality scores, and columns needing improvement.
- `POST /metadata/sample-table`
  - Calls `sample_table`.
  - Accepts a source table name and destination table location, then creates a random one percent Snowflake sample table by default.
- `POST /harness/progress-updates/format`
  - Calls `format_progress_update`.
  - Accepts progress fields and returns human-readable update text.
- `GET /openapi.json`
  - Returns the OpenAPI schema for ChatGPT Actions setup.
- `GET /.well-known/ai-plugin.json`
  - Returns a legacy plugin manifest for clients that still expect one.

## Install Server Dependencies

```bash
uv sync --extra chatgpt-plugin
```

## Serve Locally

```python
from openai_snowflake_agent_context.chatgpt_plugin import create_app

app = create_app("https://your-public-action-host.example.com")
```

Run with Uvicorn:

```bash
uv run --extra chatgpt-plugin uvicorn --factory openai_snowflake_agent_context.chatgpt_plugin:create_app
```

For a production ChatGPT Action, host the app at a public HTTPS URL and provide `GET /openapi.json` as the action schema.

## Example Request

Metadata description analysis:

```json
{
  "tables": [
    {
      "database": "ANALYTICS",
      "schema": "PUBLIC",
      "name": "ORDERS",
      "kind": "TABLE",
      "description": "Order fact table with one row per customer order.",
      "columns": [
        "ORDER_ID NUMBER -- Unique identifier for an order from the commerce system.",
        "CUSTOMER_ID NUMBER",
        "ORDER_TOTAL NUMBER -- Total order amount charged to the customer."
      ]
    }
  ]
}
```

Table sampling:

```json
{
  "table_name": "ANALYTICS.PUBLIC.ORDERS",
  "destination_location": "ANALYTICS.PUBLIC.ORDERS_SAMPLE",
  "sample_percent": 1
}
```

The sampling response includes `sampled_table`, which can be copied into harness status so future agents reference the sampled table.

## Target SMB Analytics Actions

Future ChatGPT Actions should expose the workflows described in `docs/SMB_ANALYTICS_WORKFLOWS.md`:

- `POST /analytics/discovery-report`
  - Builds an SMB-friendly report from Snowflake metadata, description analysis, and optional sampling status.
- `POST /analytics/data-gaps`
  - Returns prioritized data gaps, issues, stakeholder questions, and recommended next actions.
- `POST /analytics/transformation-candidates`
  - Recommends reviewable transformations such as staging models, reporting views, cleanup rules, and relationship checks.
- `POST /analytics/monitoring-snapshot`
  - Creates a point-in-time metadata health snapshot for recurring monitoring.
- `POST /analytics/monitoring-diff`
  - Compares current and previous snapshots to identify new, persistent, and resolved gaps.

These are roadmap endpoints. They should be added only after the underlying SDK methods and tests exist.
