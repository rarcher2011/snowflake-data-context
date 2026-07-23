"""ChatGPT Actions/OpenAPI adapter for SDK extension methods."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from pydantic import BaseModel, Field

from .agent_harness import HarnessProgressUpdate, format_progress_update
from .metadata import TableContext
from .metadata_analysis import analyze_table_metadata_descriptions
from .sampling import SnowflakeSamplingConnection, sample_table


class TableContextPayload(BaseModel):
    """Serializable table metadata supplied by ChatGPT Actions."""

    database: str
    schema_name: str = Field(alias="schema")
    name: str
    kind: str = "TABLE"
    description: str | None = None
    columns: list[str]
    context_markdown: str = ""


class MetadataAnalysisRequest(BaseModel):
    """Request body for table metadata description analysis."""

    tables: list[TableContextPayload]


class ProgressUpdateRequest(BaseModel):
    """Request body for formatting human-readable harness progress updates."""

    message: str
    work_id: str | None = None
    status: str | None = None
    completed: bool = False
    details: list[str] = Field(default_factory=list)
    generated_at: str | None = None


class SampleTableRequest(BaseModel):
    """Request body for creating a Snowflake sample table."""

    table_name: str
    destination_location: str
    sample_percent: float = 1.0


def execute_metadata_description_analysis(payload: MetadataAnalysisRequest) -> dict[str, Any]:
    """Execute the metadata description analyzer for a ChatGPT action request."""

    analysis = analyze_table_metadata_descriptions(
        [
            TableContext(
                database=table.database,
                schema=table.schema_name,
                name=table.name,
                kind=table.kind,
                description=table.description,
                columns=tuple(table.columns),
                context_markdown=table.context_markdown,
            )
            for table in payload.tables
        ]
    )
    return asdict(analysis)


def execute_format_progress_update(payload: ProgressUpdateRequest) -> dict[str, str]:
    """Execute the harness progress formatter for a ChatGPT action request."""

    text = format_progress_update(
        HarnessProgressUpdate(
            message=payload.message,
            work_id=payload.work_id,
            status=payload.status,
            completed=payload.completed,
            details=tuple(payload.details),
            generated_at=payload.generated_at,
        )
    )
    return {"text": text}


def execute_sample_table(
    payload: SampleTableRequest,
    connection: SnowflakeSamplingConnection,
) -> dict[str, Any]:
    """Execute a Snowflake table sampling request for a ChatGPT action."""

    result = sample_table(
        connection,
        payload.table_name,
        payload.destination_location,
        sample_percent=payload.sample_percent,
    )
    return result.to_status_update()


def build_openapi_schema(server_url: str = "https://example.com") -> dict[str, Any]:
    """Return an OpenAPI schema suitable for ChatGPT Actions configuration."""

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "OpenAI Snowflake Agent Context Actions",
            "version": "0.1.0",
            "description": "Execute Snowflake metadata context and harness helper methods.",
        },
        "servers": [{"url": server_url}],
        "paths": {
            "/metadata/description-analysis": {
                "post": {
                    "operationId": "analyzeMetadataDescriptions",
                    "summary": "Analyze table and column description quality.",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": MetadataAnalysisRequest.model_json_schema()
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Description quality rollup and recommendations.",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        }
                    },
                }
            },
            "/metadata/sample-table": {
                "post": {
                    "operationId": "sampleSnowflakeTable",
                    "summary": "Create a random Snowflake sample table.",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": SampleTableRequest.model_json_schema()
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Sampled table metadata and executed SQL.",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        }
                    },
                }
            },
            "/harness/progress-updates/format": {
                "post": {
                    "operationId": "formatHarnessProgressUpdate",
                    "summary": "Format a human-readable long-running agent progress update.",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": ProgressUpdateRequest.model_json_schema()
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Formatted progress update text.",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"text": {"type": "string"}},
                                        "required": ["text"],
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/openapi.json": {
                "get": {
                    "operationId": "getOpenApiSchema",
                    "summary": "Return the OpenAPI schema for this action service.",
                    "responses": {
                        "200": {
                            "description": "OpenAPI schema.",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        }
                    },
                }
            },
        },
    }


def build_ai_plugin_manifest(
    api_url: str = "https://example.com/openapi.json",
) -> dict[str, Any]:
    """Return a legacy ai-plugin manifest for clients that still expect one."""

    return {
        "schema_version": "v1",
        "name_for_human": "Snowflake Agent Context",
        "name_for_model": "snowflake_agent_context",
        "description_for_human": "Analyze Snowflake metadata descriptions, sample tables, and format agent progress updates.",
        "description_for_model": (
            "Use this service to execute SDK extension methods for Snowflake table metadata "
            "description analysis, random table sampling, and long-running agent progress "
            "update formatting."
        ),
        "auth": {"type": "none"},
        "api": {"type": "openapi", "url": api_url, "is_user_authenticated": False},
        "logo_url": "https://example.com/logo.png",
        "contact_email": "support@example.com",
        "legal_info_url": "https://example.com/legal",
    }


def create_app(
    server_url: str = "https://example.com",
    snowflake_connection: SnowflakeSamplingConnection | None = None,
) -> Any:
    """Create an optional FastAPI app exposing ChatGPT-callable actions."""

    try:
        from fastapi import FastAPI, HTTPException  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - exercised only without optional deps
        raise RuntimeError(
            "Install the chatgpt-plugin extra to serve the action app: "
            "pip install -e '.[chatgpt-plugin]'"
        ) from exc

    app = FastAPI(title="OpenAI Snowflake Agent Context Actions")

    @app.post("/metadata/description-analysis")  # type: ignore[untyped-decorator]
    def analyze_metadata_descriptions(payload: MetadataAnalysisRequest) -> dict[str, Any]:
        return execute_metadata_description_analysis(payload)

    @app.post("/metadata/sample-table")  # type: ignore[untyped-decorator]
    def sample_snowflake_table(payload: SampleTableRequest) -> dict[str, Any]:
        if snowflake_connection is None:
            raise HTTPException(
                status_code=503,
                detail="Snowflake connection is not configured for table sampling.",
            )
        return execute_sample_table(payload, snowflake_connection)

    @app.post("/harness/progress-updates/format")  # type: ignore[untyped-decorator]
    def format_harness_progress_update(payload: ProgressUpdateRequest) -> dict[str, str]:
        return execute_format_progress_update(payload)

    @app.get("/openapi.json")  # type: ignore[untyped-decorator]
    def openapi_json() -> dict[str, Any]:
        return build_openapi_schema(server_url)

    @app.get("/.well-known/ai-plugin.json")  # type: ignore[untyped-decorator]
    def ai_plugin_manifest() -> dict[str, Any]:
        return build_ai_plugin_manifest(f"{server_url.rstrip('/')}/openapi.json")

    return app
