# ChatGPT Actions Plugin

This repository includes a small ChatGPT Actions/OpenAPI adapter for executing selected SDK extension methods over HTTP.

## Exposed Methods

- `POST /metadata/description-analysis`
  - Calls `analyze_table_metadata_descriptions`.
  - Accepts table metadata payloads and returns description coverage, quality scores, and columns needing improvement.
- `POST /harness/progress-updates/format`
  - Calls `format_progress_update`.
  - Accepts progress fields and returns human-readable update text.
- `GET /openapi.json`
  - Returns the OpenAPI schema for ChatGPT Actions setup.
- `GET /.well-known/ai-plugin.json`
  - Returns a legacy plugin manifest for clients that still expect one.

## Install Server Dependencies

```bash
.venv/bin/python -m pip install -e '.[chatgpt-plugin]'
```

## Serve Locally

```python
from openai_snowflake_agent_context.chatgpt_plugin import create_app

app = create_app("https://your-public-action-host.example.com")
```

Run with Uvicorn:

```bash
.venv/bin/python -m uvicorn openai_snowflake_agent_context.chatgpt_plugin:create_app
```

For a production ChatGPT Action, host the app at a public HTTPS URL and provide `GET /openapi.json` as the action schema.

## Example Request

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

