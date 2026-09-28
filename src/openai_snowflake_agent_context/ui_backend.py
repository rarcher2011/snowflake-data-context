"""Minimal FastAPI backend for the React Snowflake setup UI."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from typing import Any, Protocol, cast

from pydantic import BaseModel, Field

from .chatgpt_plugin import MetadataAnalysisRequest, execute_metadata_description_analysis
from .config import SnowflakeContextConfig
from .connection import connect_with_private_key
from .openai_responses import extract_response_text

NOT_CONFIGURED = "Not configured"
NOT_SELECTED = "Not selected"


class WarehouseCursor(Protocol):
    """Cursor surface needed for warehouse discovery."""

    def execute(self, sql: str) -> object:
        """Execute a Snowflake SQL statement."""

    def fetchall(self) -> list[object]:
        """Fetch all rows from the last statement."""


class WarehouseConnection(Protocol):
    """Connection surface needed for warehouse discovery."""

    def cursor(self) -> WarehouseCursor:
        """Return a cursor-like object."""

    def close(self) -> object:
        """Close the connection."""


ConnectionFactory = Callable[[], WarehouseConnection]


class LLMResponsesResource(Protocol):
    """Minimal Responses API surface needed for description suggestions."""

    def create(self, **kwargs: Any) -> object:
        """Create a model response."""


class LLMClient(Protocol):
    """Minimal configured LLM SDK client used by the UI backend."""

    responses: LLMResponsesResource


LLMClientFactory = Callable[[], LLMClient]


class ColumnDescriptionUpdate(BaseModel):
    """Editable column description submitted by the UI."""

    name: str
    description: str


class ColumnDescriptionSaveRequest(BaseModel):
    """Request body for saving edited Snowflake column descriptions."""

    database: str
    schema_name: str = Field(alias="schema")
    table: str
    columns: list[ColumnDescriptionUpdate]


class ColumnMetadataPayload(BaseModel):
    """Column metadata submitted by the UI for description suggestions."""

    name: str
    dataType: str
    description: str = ""
    nullable: str = ""


class MetadataDescriptionSuggestionRequest(BaseModel):
    """Request body for LLM-backed column description suggestions."""

    database: str
    schema_name: str = Field(alias="schema")
    table: str
    columns: list[ColumnMetadataPayload]


class PlainTextTableQueryRequest(BaseModel):
    """Request body for plain-text table queries backed by metadata context."""

    warehouse: str | None = None
    database: str
    schema_name: str = Field(alias="schema")
    table: str
    question: str
    columns: list[ColumnMetadataPayload]
    row_limit: int = Field(default=100, ge=1, le=500)


class DiscoveryReportRequest(BaseModel):
    """Request body for the schema discovery report endpoint."""

    warehouse: str | None = None
    database: str
    schema_name: str = Field(alias="schema")
    max_tables_to_sample: int = Field(default=3, ge=1, le=10)
    sample_percent: float = Field(default=1.0, ge=0.1, le=10.0)


def list_snowflake_warehouses(connection_factory: ConnectionFactory) -> list[str]:
    """Return warehouse names from Snowflake using `SHOW WAREHOUSES`."""

    connection = connection_factory()
    try:
        cursor = connection.cursor()
        cursor.execute("SHOW WAREHOUSES")
        return [_warehouse_name_from_row(row) for row in cursor.fetchall()]
    finally:
        connection.close()


def list_snowflake_databases(connection_factory: ConnectionFactory) -> list[str]:
    """Return database names from Snowflake using `SHOW DATABASES`."""

    connection = connection_factory()
    try:
        cursor = connection.cursor()
        cursor.execute("SHOW DATABASES")
        return [_database_name_from_row(row) for row in cursor.fetchall()]
    finally:
        connection.close()


def list_snowflake_schemas(
    connection_factory: ConnectionFactory,
    *,
    warehouse: str | None = None,
    database: str | None = None,
) -> list[str]:
    """Return schema names from Snowflake using `SHOW SCHEMAS`."""

    connection = connection_factory()
    try:
        cursor = connection.cursor()
        if warehouse:
            cursor.execute(f"USE WAREHOUSE {_quote_snowflake_identifier(warehouse)}")
        if database:
            cursor.execute(f"SHOW SCHEMAS IN DATABASE {_quote_snowflake_identifier(database)}")
        else:
            cursor.execute("SHOW SCHEMAS")
        return [_schema_name_from_row(row) for row in cursor.fetchall()]
    finally:
        connection.close()


def list_snowflake_tables(
    connection_factory: ConnectionFactory,
    *,
    warehouse: str | None = None,
    database: str | None = None,
    schema: str | None = None,
) -> list[dict[str, str]]:
    """Return table summaries from Snowflake using `SHOW TABLES`."""

    connection = connection_factory()
    try:
        cursor = connection.cursor()
        if warehouse:
            cursor.execute(f"USE WAREHOUSE {_quote_snowflake_identifier(warehouse)}")

        resolved_database = _selected_value(database)
        resolved_schema = _selected_value(schema)
        if resolved_schema and not resolved_database:
            resolved_database = _current_database(cursor)
            if not resolved_database:
                raise ValueError(
                    "A database must be selected or configured before listing schema tables."
                )

        if resolved_database and resolved_schema:
            cursor.execute(
                "SHOW TABLES IN SCHEMA "
                f"{_quote_snowflake_identifier(resolved_database)}."
                f"{_quote_snowflake_identifier(resolved_schema)}"
            )
        elif resolved_database:
            cursor.execute(f"SHOW TABLES IN DATABASE {_quote_snowflake_identifier(resolved_database)}")
        else:
            cursor.execute("SHOW TABLES")

        return [_table_summary_from_row(row, resolved_database, resolved_schema) for row in cursor.fetchall()]
    finally:
        connection.close()


def describe_snowflake_table(
    connection_factory: ConnectionFactory,
    *,
    warehouse: str | None = None,
    database: str,
    schema: str,
    table: str,
) -> dict[str, object]:
    """Return column metadata for a selected Snowflake table."""

    connection = connection_factory()
    try:
        cursor = connection.cursor()
        if warehouse:
            cursor.execute(f"USE WAREHOUSE {_quote_snowflake_identifier(warehouse)}")

        cursor.execute(
            "SELECT COLUMN_NAME, DATA_TYPE, COMMENT, IS_NULLABLE, ORDINAL_POSITION "
            f"FROM {_quote_snowflake_identifier(database)}.INFORMATION_SCHEMA.COLUMNS "
            f"WHERE UPPER(TABLE_SCHEMA) = UPPER({_quote_snowflake_literal(schema)}) "
            f"AND UPPER(TABLE_NAME) = UPPER({_quote_snowflake_literal(table)}) "
            "ORDER BY ORDINAL_POSITION"
        )
        columns = [_column_metadata_from_row(row) for row in cursor.fetchall()]
        return {
            "database": database,
            "schema": schema,
            "table": table,
            "columns": columns,
        }
    finally:
        connection.close()


def build_connection_status(
    environ: dict[str, str] | None = None,
    connection_factory: ConnectionFactory | None = None,
) -> dict[str, object]:
    """Return UI-ready Snowflake connection status from environment configuration."""

    environ = environ or dict(os.environ)
    missing = _missing_required_env(environ)
    private_key_configured = bool(environ.get("SNOWFLAKE_PRIVATE_KEY_PATH"))
    status: dict[str, object] = {
        "configured": not missing,
        "account": environ.get("SNOWFLAKE_ACCOUNT") or NOT_CONFIGURED,
        "configuredUser": environ.get("SNOWFLAKE_USER") or NOT_CONFIGURED,
        "currentUser": environ.get("SNOWFLAKE_USER") or NOT_CONFIGURED,
        "database": environ.get("SNOWFLAKE_DATABASE") or NOT_SELECTED,
        "schema": environ.get("SNOWFLAKE_SCHEMA") or NOT_SELECTED,
        "privateKeyConfigured": private_key_configured,
        "privateKeyConnectionWorking": False,
        "error": None,
    }
    if missing:
        status["error"] = f"Missing required environment variables: {', '.join(missing)}"
        return status

    try:
        factory = connection_factory or create_env_connection_factory(environ)
        identity = fetch_snowflake_identity(factory)
    except Exception as exc:  # noqa: BLE001 - surface connector failures in UI status
        status["error"] = str(exc)
        return status

    status["currentUser"] = identity["current_user"]
    status["database"] = identity["current_database"] or environ.get("SNOWFLAKE_DATABASE") or NOT_SELECTED
    status["privateKeyConnectionWorking"] = True
    status["error"] = None
    return status


def fetch_snowflake_identity(connection_factory: ConnectionFactory) -> dict[str, str | None]:
    """Return current Snowflake user and database for the UI connection panel."""

    connection = connection_factory()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT CURRENT_USER(), CURRENT_DATABASE()")
        rows = cursor.fetchall()
        if not rows:
            raise ValueError("Snowflake did not return connection identity.")
        row = rows[0]
        return {
            "current_user": _row_field(row, 0, "CURRENT_USER()") or NOT_CONFIGURED,
            "current_database": _row_field(row, 1, "CURRENT_DATABASE()"),
        }
    finally:
        connection.close()


def build_env_snowflake_config(environ: dict[str, str] | None = None) -> SnowflakeContextConfig:
    """Build Snowflake connection config from environment variables."""

    environ = environ or dict(os.environ)
    return SnowflakeContextConfig(
        account=_required_env(environ, "SNOWFLAKE_ACCOUNT"),
        user=_required_env(environ, "SNOWFLAKE_USER"),
        warehouse=_required_env(environ, "SNOWFLAKE_WAREHOUSE"),
        role=environ.get("SNOWFLAKE_ROLE"),
        database=environ.get("SNOWFLAKE_DATABASE"),
        schema=environ.get("SNOWFLAKE_SCHEMA"),
        private_key_path=_required_env(environ, "SNOWFLAKE_PRIVATE_KEY_PATH"),
    )


def create_env_connection_factory(
    environ: dict[str, str] | None = None,
) -> ConnectionFactory:
    """Create a Snowflake private-key connection factory from environment variables."""

    environ = environ or dict(os.environ)
    config = build_env_snowflake_config(environ)
    private_key_passphrase = environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")

    def factory() -> WarehouseConnection:
        return cast(
            WarehouseConnection,
            connect_with_private_key(
                config,
                private_key_passphrase=private_key_passphrase,
            ),
        )

    return factory


def create_env_llm_client(environ: dict[str, str] | None = None) -> LLMClient:
    """Create an OpenAI SDK client from environment configuration."""

    environ = environ or dict(os.environ)
    if not environ.get("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY is required to suggest descriptions with the LLM SDK.")
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - package dependency should provide this
        raise RuntimeError("Install the openai package to suggest descriptions.") from exc
    return cast(LLMClient, OpenAI())


def create_ui_app(
    connection_factory: ConnectionFactory | None = None,
    llm_client_factory: LLMClientFactory | None = None,
) -> Any:
    """Create the FastAPI app used by the local React UI."""

    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as exc:  # pragma: no cover - exercised only without optional deps
        raise RuntimeError(
            "Install the chatgpt-plugin extra to serve the UI backend: "
            "uv sync --extra chatgpt-plugin"
        ) from exc

    app = FastAPI(title="Snowflake Data Context UI API")

    @app.get("/api/snowflake/warehouses")
    def warehouses() -> list[str]:
        try:
            factory = connection_factory or create_env_connection_factory()
            return list_snowflake_warehouses(factory)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/snowflake/databases")
    def databases() -> list[str]:
        try:
            factory = connection_factory or create_env_connection_factory()
            return list_snowflake_databases(factory)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/snowflake/schemas")
    def schemas(warehouse: str | None = None, database: str | None = None) -> list[str]:
        try:
            environ = dict(os.environ)
            factory = connection_factory or create_env_connection_factory(environ)
            return list_snowflake_schemas(
                factory,
                warehouse=warehouse,
                database=_selected_value(database) or environ.get("SNOWFLAKE_DATABASE"),
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/snowflake/tables")
    def tables(
        warehouse: str | None = None,
        database: str | None = None,
        schema: str | None = None,
    ) -> list[dict[str, str]]:
        try:
            environ = dict(os.environ)
            factory = connection_factory or create_env_connection_factory(environ)
            return list_snowflake_tables(
                factory,
                warehouse=warehouse,
                database=_selected_value(database) or environ.get("SNOWFLAKE_DATABASE"),
                schema=schema,
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/snowflake/table-metadata")
    def table_metadata(
        warehouse: str | None = None,
        database: str | None = None,
        schema: str | None = None,
        table: str | None = None,
    ) -> dict[str, object]:
        try:
            environ = dict(os.environ)
            resolved_database = _selected_value(database) or environ.get("SNOWFLAKE_DATABASE")
            resolved_schema = _selected_value(schema) or environ.get("SNOWFLAKE_SCHEMA")
            if not resolved_database or not resolved_schema or not table:
                raise ValueError("Database, schema, and table are required to fetch table metadata.")
            factory = connection_factory or create_env_connection_factory(environ)
            return describe_snowflake_table(
                factory,
                warehouse=warehouse,
                database=resolved_database,
                schema=resolved_schema,
                table=table,
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/metadata/description-analysis")
    def analyze_metadata_descriptions(payload: MetadataAnalysisRequest) -> dict[str, Any]:
        return execute_metadata_description_analysis(payload)

    @app.post("/api/snowflake/column-descriptions")
    def save_column_descriptions(payload: ColumnDescriptionSaveRequest) -> dict[str, object]:
        return {
            "status": "scaffolded",
            "persisted": False,
            "columnsReceived": len(payload.columns),
        }

    @app.post("/api/snowflake/description-suggestions")
    def suggest_column_descriptions(
        payload: MetadataDescriptionSuggestionRequest,
    ) -> dict[str, object]:
        try:
            environ = dict(os.environ)
            client = llm_client_factory() if llm_client_factory else create_env_llm_client(environ)
            model = _description_suggestion_model(environ)
            return suggest_metadata_descriptions_with_llm(
                payload=payload,
                llm_client=client,
                model=model,
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/snowflake/query")
    def query_table(payload: PlainTextTableQueryRequest) -> dict[str, object]:
        try:
            environ = dict(os.environ)
            client = llm_client_factory() if llm_client_factory else create_env_llm_client(environ)
            model = _query_generation_model(environ)
            factory = connection_factory or create_env_connection_factory(environ)
            return run_plain_text_table_query(
                payload=payload,
                connection_factory=factory,
                llm_client=client,
                model=model,
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/snowflake/discovery-report")
    def discovery_report(payload: DiscoveryReportRequest) -> dict[str, object]:
        try:
            environ = dict(os.environ)
            client = llm_client_factory() if llm_client_factory else create_env_llm_client(environ)
            model = _discovery_report_model(environ)
            factory = connection_factory or create_env_connection_factory(environ)
            return run_discovery_report(
                payload=payload,
                connection_factory=factory,
                llm_client=client,
                model=model,
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/connection/status")
    def connection_status() -> dict[str, object]:
        return build_connection_status(connection_factory=connection_factory)

    return app


def main() -> None:
    """Run the local UI API with Uvicorn."""

    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - exercised only without optional deps
        raise RuntimeError(
            "Install the chatgpt-plugin extra to run the UI backend: "
            "uv sync --extra chatgpt-plugin"
        ) from exc

    uvicorn.run(
        "openai_snowflake_agent_context.ui_backend:create_ui_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )


def _required_env(environ: dict[str, str], name: str) -> str:
    value = environ.get(name)
    if not value:
        raise ValueError(f"{name} is required to connect to Snowflake.")
    return value


def _missing_required_env(environ: dict[str, str]) -> list[str]:
    return [
        name
        for name in (
            "SNOWFLAKE_ACCOUNT",
            "SNOWFLAKE_USER",
            "SNOWFLAKE_WAREHOUSE",
            "SNOWFLAKE_PRIVATE_KEY_PATH",
        )
        if not environ.get(name)
    ]


def _warehouse_name_from_row(row: object) -> str:
    if isinstance(row, dict):
        value = row.get("name", row.get("NAME"))
        if value is None:
            raise ValueError("Warehouse row did not include a name field.")
        return str(value)
    if isinstance(row, (tuple, list)) and row:
        return str(row[0])
    name = getattr(row, "name", None)
    if name is not None:
        return str(name)
    raise ValueError("Warehouse row did not include a name field.")


def _database_name_from_row(row: object) -> str:
    if isinstance(row, dict):
        value = row.get("name", row.get("NAME"))
        if value is None:
            raise ValueError("Database row did not include a name field.")
        return str(value)
    if isinstance(row, (tuple, list)) and len(row) > 1:
        return str(row[1])
    name = getattr(row, "name", None)
    if name is not None:
        return str(name)
    raise ValueError("Database row did not include a name field.")


def _schema_name_from_row(row: object) -> str:
    if isinstance(row, dict):
        value = row.get("name", row.get("NAME"))
        if value is None:
            raise ValueError("Schema row did not include a name field.")
        return str(value)
    if isinstance(row, (tuple, list)) and len(row) > 1:
        return str(row[1])
    name = getattr(row, "name", None)
    if name is not None:
        return str(name)
    raise ValueError("Schema row did not include a name field.")


def _table_summary_from_row(
    row: object,
    fallback_database: str | None,
    fallback_schema: str | None,
) -> dict[str, str]:
    name = _table_row_value(row, "name", "NAME", 1)
    database = _table_row_value(row, "database_name", "DATABASE_NAME", 2) or fallback_database or ""
    schema = _table_row_value(row, "schema_name", "SCHEMA_NAME", 3) or fallback_schema or ""
    kind = _table_row_value(row, "kind", "KIND", 4) or "BASE TABLE"
    comment = _table_row_value(row, "comment", "COMMENT", 5)
    return {
        "database": database,
        "schema": schema,
        "name": name or "",
        "type": _normalize_table_kind(kind),
        "descriptionStatus": "strong" if comment else "missing",
    }


def _column_metadata_from_row(row: object) -> dict[str, str]:
    description = _row_field(row, 2, "COMMENT") or ""
    return {
        "name": _row_field(row, 0, "COLUMN_NAME") or "",
        "dataType": _row_field(row, 1, "DATA_TYPE") or "",
        "description": description,
        "nullable": _normalize_nullable(_row_field(row, 3, "IS_NULLABLE")),
    }


def _cursor_column_names(cursor: object) -> list[str]:
    description = getattr(cursor, "description", None)
    if not isinstance(description, list | tuple):
        return []
    names: list[str] = []
    for item in description:
        if isinstance(item, (list, tuple)) and item:
            names.append(str(item[0]))
        else:
            name = getattr(item, "name", None)
            if name is not None:
                names.append(str(name))
    return names


def _query_row_to_record(row: object, column_names: list[str]) -> dict[str, object]:
    if isinstance(row, dict):
        return dict(row)
    if isinstance(row, (list, tuple)):
        return {
            column_names[index] if index < len(column_names) else f"column_{index + 1}": value
            for index, value in enumerate(row)
        }
    as_dict = getattr(row, "as_dict", None)
    if callable(as_dict):
        value = as_dict()
        if isinstance(value, dict):
            return dict(value)
    return {"value": row}


def _current_database(cursor: WarehouseCursor) -> str | None:
    cursor.execute("SELECT CURRENT_DATABASE()")
    rows = cursor.fetchall()
    if not rows:
        return None
    return _row_field(rows[0], 0, "CURRENT_DATABASE()")


def _table_row_value(row: object, lower_key: str, upper_key: str, index: int) -> str | None:
    if isinstance(row, dict):
        value = row.get(lower_key, row.get(upper_key))
    elif isinstance(row, (tuple, list)) and len(row) > index:
        value = row[index]
    else:
        value = getattr(row, lower_key, getattr(row, upper_key, None))
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _row_field(row: object, index: int, key: str) -> str | None:
    return _row_field_any(row, index, key, key.lower())


def _row_field_any(row: object, index: int, *keys: str) -> str | None:
    if isinstance(row, dict):
        value = None
        for key in keys:
            value = row.get(key, row.get(key.lower(), row.get(key.upper())))
            if value is not None:
                break
    elif isinstance(row, (tuple, list)) and len(row) > index:
        value = row[index]
    else:
        value = None
        for key in keys:
            value = getattr(row, key, getattr(row, key.lower(), None))
            if value is not None:
                break
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _quote_snowflake_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _quote_snowflake_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _selected_value(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if stripped == NOT_SELECTED:
        return None
    return stripped or None


def _normalize_table_kind(kind: str) -> str:
    normalized = kind.upper()
    if normalized == "VIEW":
        return "VIEW"
    return "BASE TABLE"


def _normalize_nullable(value: str | None) -> str:
    if value is None:
        return ""
    normalized = value.strip().upper()
    if normalized in {"Y", "YES", "TRUE"}:
        return "YES"
    if normalized in {"N", "NO", "FALSE"}:
        return "NO"
    return value


def suggest_metadata_descriptions_with_llm(
    *,
    payload: MetadataDescriptionSuggestionRequest,
    llm_client: LLMClient,
    model: str,
) -> dict[str, object]:
    """Ask a configured LLM client for column description suggestions."""

    response = llm_client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": (
                    "You write concise Snowflake column descriptions for analytics teams. "
                    "Use only the submitted table and column metadata. "
                    "Return strict JSON with a columns array. Each item must include "
                    "name, description, and rationale."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(_llm_description_suggestion_payload(payload), sort_keys=True),
            },
        ],
    )
    response_text = extract_response_text(response)
    suggestions = _parse_llm_description_suggestions(response_text)
    return {
        "status": "suggested",
        "model": model,
        "table": f"{payload.database}.{payload.schema_name}.{payload.table}",
        "suggestions": [
            {
                "name": suggestion["name"],
                "suggestedDescription": suggestion["description"],
                "reason": suggestion["rationale"],
            }
            for suggestion in suggestions
        ],
    }


def run_plain_text_table_query(
    *,
    payload: PlainTextTableQueryRequest,
    connection_factory: ConnectionFactory,
    llm_client: LLMClient,
    model: str,
) -> dict[str, object]:
    """Generate a read-only Snowflake SQL query from metadata context and execute it."""

    response = llm_client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": (
                    "You generate safe, read-only Snowflake SQL for one selected table. "
                    "Use only the supplied table metadata. Return strict JSON with sql and explanation. "
                    "The SQL must be a single SELECT or WITH query and must not modify data."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(_llm_table_query_payload(payload), sort_keys=True),
            },
        ],
    )
    response_text = extract_response_text(response)
    query_plan = _parse_llm_query_response(response_text)
    sql = _bounded_read_only_sql(query_plan["sql"], payload.row_limit)

    connection = connection_factory()
    try:
        cursor = connection.cursor()
        if payload.warehouse:
            cursor.execute(f"USE WAREHOUSE {_quote_snowflake_identifier(payload.warehouse)}")
        cursor.execute(sql)
        column_names = _cursor_column_names(cursor)
        rows = [_query_row_to_record(row, column_names) for row in cursor.fetchall()]
    finally:
        connection.close()

    return {
        "status": "completed",
        "model": model,
        "sql": sql,
        "explanation": query_plan["explanation"],
        "columns": column_names,
        "rows": rows,
        "rowCount": len(rows),
    }


def _llm_table_query_payload(payload: PlainTextTableQueryRequest) -> dict[str, object]:
    return {
        "question": payload.question,
        "row_limit": payload.row_limit,
        "table": {
            "database": payload.database,
            "schema": payload.schema_name,
            "name": payload.table,
            "identifier": _quote_snowflake_identifier_path(
                payload.database,
                payload.schema_name,
                payload.table,
            ),
        },
        "columns": [
            {
                "name": column.name,
                "data_type": column.dataType,
                "description": column.description,
                "nullable": column.nullable,
            }
            for column in payload.columns
        ],
    }


def _parse_llm_query_response(response_text: str) -> dict[str, str]:
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM response did not contain valid JSON SQL.") from exc
    if not isinstance(payload, dict):
        raise TypeError("LLM query response must be an object.")
    return {
        "sql": _required_payload_text(payload, "sql"),
        "explanation": _optional_payload_text_any(payload, "explanation", "rationale"),
    }


def _bounded_read_only_sql(sql: str, row_limit: int) -> str:
    cleaned = sql.strip().rstrip(";").strip()
    if not re.match(r"^(select|with)\b", cleaned, flags=re.IGNORECASE):
        raise ValueError("Generated SQL must be a SELECT or WITH query.")
    if ";" in cleaned:
        raise ValueError("Generated SQL must contain a single statement.")
    if re.search(
        r"\b(insert|update|delete|merge|drop|alter|create|truncate|copy|put|remove|grant|revoke)\b",
        cleaned,
        flags=re.IGNORECASE,
    ):
        raise ValueError("Generated SQL must be read-only.")
    if re.search(r"\blimit\s+\d+\b", cleaned, flags=re.IGNORECASE):
        return cleaned
    return f"SELECT * FROM (\n{cleaned}\n) AS generated_query\nLIMIT {row_limit}"


def _quote_snowflake_identifier_path(*parts: str) -> str:
    return ".".join(_quote_snowflake_identifier(part) for part in parts)


def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[: text.rfind("```")]
    return text.strip()


def _llm_description_suggestion_payload(
    payload: MetadataDescriptionSuggestionRequest,
) -> dict[str, object]:
    return {
        "table": {
            "database": payload.database,
            "schema": payload.schema_name,
            "name": payload.table,
        },
        "columns": [
            {
                "name": column.name,
                "data_type": column.dataType,
                "existing_description": column.description,
                "nullable": column.nullable,
            }
            for column in payload.columns
        ],
    }


def _parse_llm_description_suggestions(response_text: str) -> list[dict[str, str]]:
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM response did not contain valid JSON suggestions.") from exc

    raw_columns = payload.get("columns", payload.get("suggestions"))
    if not isinstance(raw_columns, list):
        raise TypeError("LLM response must include a columns array.")

    suggestions: list[dict[str, str]] = []
    for raw_column in raw_columns:
        if not isinstance(raw_column, dict):
            raise TypeError("Each column suggestion must be an object.")
        suggestions.append(
            {
                "name": _required_payload_text(raw_column, "name"),
                "description": _required_payload_text_any(
                    raw_column,
                    "description",
                    "suggestedDescription",
                    "suggested_description",
                ),
                "rationale": _optional_payload_text_any(raw_column, "rationale", "reason"),
            }
        )
    return suggestions


def _required_payload_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Column suggestion must include non-empty {key}.")
    return value.strip()


def _required_payload_text_any(payload: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError(f"Column suggestion must include one of: {', '.join(keys)}.")


def _optional_payload_text_any(payload: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _description_suggestion_model(environ: dict[str, str]) -> str:
    return environ.get("OPENAI_DESCRIPTION_MODEL") or environ.get("OPENAI_MODEL") or "gpt-4.1-mini"


def _query_generation_model(environ: dict[str, str]) -> str:
    return environ.get("OPENAI_QUERY_MODEL") or environ.get("OPENAI_MODEL") or "gpt-4.1-mini"


def _discovery_report_model(environ: dict[str, str]) -> str:
    return environ.get("OPENAI_DISCOVERY_MODEL") or environ.get("OPENAI_MODEL") or "gpt-4.1-mini"


# ---------------------------------------------------------------------------
# Discovery report
# ---------------------------------------------------------------------------

_FK_SUFFIX_RE = re.compile(r"(_ID|_KEY|_FK|_REF)$", re.IGNORECASE)
_DATE_TYPES = frozenset({"DATE", "TIMESTAMP", "TIMESTAMP_NTZ", "TIMESTAMP_LTZ", "TIMESTAMP_TZ", "DATETIME"})
_NUMERIC_TYPES = frozenset({"NUMBER", "FLOAT", "DECIMAL", "INTEGER", "INT", "BIGINT", "SMALLINT", "TINYINT", "DOUBLE"})


def fetch_schema_columns(
    connection_factory: ConnectionFactory,
    *,
    warehouse: str | None = None,
    database: str,
    schema: str,
) -> list[dict[str, object]]:
    """Return all column metadata for a schema in a single INFORMATION_SCHEMA query."""
    connection = connection_factory()
    try:
        cursor = connection.cursor()
        if warehouse:
            cursor.execute(f"USE WAREHOUSE {_quote_snowflake_identifier(warehouse)}")
        cursor.execute(
            "SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, COMMENT, IS_NULLABLE, ORDINAL_POSITION "
            f"FROM {_quote_snowflake_identifier(database)}.INFORMATION_SCHEMA.COLUMNS "
            f"WHERE UPPER(TABLE_SCHEMA) = UPPER({_quote_snowflake_literal(schema)}) "
            "ORDER BY TABLE_NAME, ORDINAL_POSITION"
        )
        rows = cursor.fetchall()
        return [
            {
                "table_name": _row_field(row, 0, "TABLE_NAME") or "",
                "column_name": _row_field(row, 1, "COLUMN_NAME") or "",
                "data_type": _row_field(row, 2, "DATA_TYPE") or "",
                "description": _row_field(row, 3, "COMMENT") or "",
                "nullable": _normalize_nullable(_row_field(row, 4, "IS_NULLABLE")),
                "ordinal": _row_field(row, 5, "ORDINAL_POSITION") or "",
            }
            for row in rows
        ]
    finally:
        connection.close()


def fetch_schema_table_row_counts(
    connection_factory: ConnectionFactory,
    *,
    warehouse: str | None = None,
    database: str,
    schema: str,
) -> dict[str, int]:
    """Return estimated row counts from INFORMATION_SCHEMA.TABLES (no table scan)."""
    connection = connection_factory()
    try:
        cursor = connection.cursor()
        if warehouse:
            cursor.execute(f"USE WAREHOUSE {_quote_snowflake_identifier(warehouse)}")
        cursor.execute(
            "SELECT TABLE_NAME, ROW_COUNT "
            f"FROM {_quote_snowflake_identifier(database)}.INFORMATION_SCHEMA.TABLES "
            f"WHERE UPPER(TABLE_SCHEMA) = UPPER({_quote_snowflake_literal(schema)}) "
            "AND TABLE_TYPE IN ('BASE TABLE', 'VIEW') "
            "ORDER BY ROW_COUNT DESC NULLS LAST"
        )
        result: dict[str, int] = {}
        for row in cursor.fetchall():
            name = _row_field(row, 0, "TABLE_NAME") or ""
            count_str = _row_field(row, 1, "ROW_COUNT")
            result[name] = int(count_str) if count_str and count_str.isdigit() else 0
        return result
    finally:
        connection.close()


def fetch_table_sample_stats(
    connection_factory: ConnectionFactory,
    *,
    warehouse: str | None = None,
    database: str,
    schema: str,
    table: str,
    columns: list[dict[str, object]],
    sample_percent: float = 1.0,
) -> dict[str, object]:
    """Return sampled summary statistics for a table using TABLESAMPLE BERNOULLI."""
    date_cols = [c for c in columns if str(c.get("data_type", "")).upper() in _DATE_TYPES][:2]
    numeric_cols = [
        c for c in columns
        if str(c.get("data_type", "")).upper() in _NUMERIC_TYPES
        and not _FK_SUFFIX_RE.search(str(c.get("column_name", "")))
    ][:3]

    select_parts = ["COUNT(*) AS _row_count"]
    for col in date_cols:
        quoted = _quote_snowflake_identifier(str(col["column_name"]))
        select_parts.append(f"MIN({quoted}) AS _min_{col['column_name']}")
        select_parts.append(f"MAX({quoted}) AS _max_{col['column_name']}")
    for col in numeric_cols:
        quoted = _quote_snowflake_identifier(str(col["column_name"]))
        select_parts.append(f"AVG({quoted}) AS _avg_{col['column_name']}")
        select_parts.append(f"MAX({quoted}) AS _max_{col['column_name']}")

    table_ref = (
        f"{_quote_snowflake_identifier(database)}"
        f".{_quote_snowflake_identifier(schema)}"
        f".{_quote_snowflake_identifier(table)}"
    )
    sql = (
        f"SELECT {', '.join(select_parts)} "
        f"FROM {table_ref} TABLESAMPLE BERNOULLI ({sample_percent})"
    )

    connection = connection_factory()
    try:
        cursor = connection.cursor()
        if warehouse:
            cursor.execute(f"USE WAREHOUSE {_quote_snowflake_identifier(warehouse)}")
        cursor.execute(sql)
        col_names = _cursor_column_names(cursor)
        rows = cursor.fetchall()
    finally:
        connection.close()

    if not rows:
        return {"sampled": True, "sample_percent": sample_percent, "stats": {}}

    row = rows[0]
    record = _query_row_to_record(row, col_names)
    stats: dict[str, object] = {}
    for key, value in record.items():
        if key == "_row_count":
            continue
        clean_key = key.lstrip("_")
        stats[clean_key] = _serialize_stat(value)

    sampled_count = record.get("_row_count")
    return {
        "sampled": True,
        "sample_percent": sample_percent,
        "sampled_row_count": int(sampled_count) if sampled_count is not None else None,
        "stats": stats,
    }


def _serialize_stat(value: object) -> object:
    if value is None:
        return None
    try:
        import datetime
        if isinstance(value, (datetime.date, datetime.datetime)):
            return value.isoformat()
    except Exception:  # noqa: BLE001
        pass
    if isinstance(value, float):
        return round(value, 4)
    return value


def detect_table_relationships(
    tables_columns: dict[str, list[dict[str, object]]],
) -> list[dict[str, str]]:
    """Detect likely FK relationships by matching column names to table names."""
    table_names_upper = {name.upper(): name for name in tables_columns}
    relationships: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for table_name, columns in tables_columns.items():
        for col in columns:
            col_name = str(col.get("column_name", ""))
            if not _FK_SUFFIX_RE.search(col_name):
                continue
            stem = _FK_SUFFIX_RE.sub("", col_name).upper()
            own = table_name.upper()
            if stem == own or stem + "S" == own:
                continue
            # Match exact stem or common plural form (stem + S)
            candidates = [stem, stem + "S"]
            ref_table = None
            for candidate in candidates:
                if candidate in table_names_upper:
                    ref_table = table_names_upper[candidate]
                    break
            if ref_table is None:
                continue
            key = (table_name, col_name, ref_table, "")
            if key not in seen:
                seen.add(key)
                relationships.append(
                    {
                        "from_table": table_name,
                        "from_column": col_name,
                        "to_table": ref_table,
                        "relationship": "likely FK",
                    }
                )

    return relationships


def _build_discovery_llm_prompt(
    tables_columns: dict[str, list[dict[str, object]]],
    row_counts: dict[str, int],
    relationships: list[dict[str, str]],
) -> str:
    """Build a compact schema summary for the LLM — keeps token cost low."""
    lines: list[str] = [
        "Snowflake schema tables with columns (data_type [description if any]):"
    ]
    for table_name, columns in tables_columns.items():
        count = row_counts.get(table_name, 0)
        col_parts = []
        for col in columns[:20]:  # cap columns per table to limit tokens
            col_name = col.get("column_name", "")
            data_type = col.get("data_type", "")
            desc = col.get("description", "")
            entry = f"{col_name} {data_type}"
            if desc:
                entry += f" [{desc[:60]}]"
            col_parts.append(entry)
        lines.append(f"\nTABLE {table_name} (~{count:,} rows): {', '.join(col_parts)}")

    if relationships:
        lines.append(
            "\nDetected relationships: "
            + "; ".join(
                f"{r['from_table']}.{r['from_column']} -> {r['to_table']}"
                for r in relationships
            )
        )

    return "\n".join(lines)


def _parse_discovery_llm_response(response_text: str) -> list[dict[str, object]]:
    try:
        payload = json.loads(_strip_markdown_fences(response_text))
    except json.JSONDecodeError as exc:
        raise ValueError("LLM discovery response did not contain valid JSON.") from exc
    tables = payload.get("tables")
    if not isinstance(tables, list):
        raise TypeError("LLM discovery response must include a tables array.")
    result: list[dict[str, object]] = []
    for item in tables:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "name": str(item.get("name", "")),
                "description": str(item.get("description", "")),
                "key_columns": item.get("key_columns", []),
                "purpose": str(item.get("purpose", "")),
            }
        )
    return result


def run_discovery_report(
    *,
    payload: DiscoveryReportRequest,
    connection_factory: ConnectionFactory,
    llm_client: LLMClient,
    model: str,
) -> dict[str, object]:
    """Build a discovery report: schema overview, relationships, sampled stats, LLM descriptions."""

    # 1. Fetch all column metadata in one query
    all_columns = fetch_schema_columns(
        connection_factory,
        warehouse=payload.warehouse,
        database=payload.database,
        schema=payload.schema_name,
    )

    # Group columns by table
    tables_columns: dict[str, list[dict[str, object]]] = {}
    for col in all_columns:
        tname = str(col["table_name"])
        tables_columns.setdefault(tname, []).append(col)

    if not tables_columns:
        return {
            "status": "empty",
            "database": payload.database,
            "schema": payload.schema_name,
            "tables": [],
            "relationships": [],
            "summary_stats": [],
        }

    # 2. Get row count estimates (no table scan)
    row_counts = fetch_schema_table_row_counts(
        connection_factory,
        warehouse=payload.warehouse,
        database=payload.database,
        schema=payload.schema_name,
    )

    # 3. Detect FK-style relationships
    relationships = detect_table_relationships(tables_columns)

    # 4. Sample the top N largest tables for summary stats
    sorted_tables = sorted(tables_columns.keys(), key=lambda t: row_counts.get(t, 0), reverse=True)
    tables_to_sample = sorted_tables[: payload.max_tables_to_sample]

    summary_stats: list[dict[str, object]] = []
    for table_name in tables_to_sample:
        cols = tables_columns[table_name]
        stats = fetch_table_sample_stats(
            connection_factory,
            warehouse=payload.warehouse,
            database=payload.database,
            schema=payload.schema_name,
            table=table_name,
            columns=cols,
            sample_percent=payload.sample_percent,
        )
        summary_stats.append(
            {
                "table": table_name,
                "estimated_row_count": row_counts.get(table_name, 0),
                **stats,
            }
        )

    # 5. Ask LLM for compact table descriptions — one call for the whole schema
    compact_prompt = _build_discovery_llm_prompt(tables_columns, row_counts, relationships)
    response = llm_client.responses.create(
        model=model,
        text={"format": {"type": "json_object"}},
        input=[
            {
                "role": "system",
                "content": (
                    "You are a data analyst. Given a Snowflake schema, return a JSON object with a "
                    "tables array. Each item must include: name (string), description (1-2 sentence "
                    "plain-English summary of the table's purpose), key_columns (array of the most "
                    "analytically important column names, max 5), and purpose (one of: fact, dimension, "
                    "staging, reference, log, unknown). Be concise — descriptions under 150 characters."
                ),
            },
            {
                "role": "user",
                "content": compact_prompt,
            },
        ],
        max_output_tokens=1000,
    )
    response_text = extract_response_text(response)
    llm_tables = _parse_discovery_llm_response(response_text)

    # Merge LLM descriptions with metadata
    llm_by_name = {t["name"]: t for t in llm_tables}
    tables_out: list[dict[str, object]] = []
    for table_name in sorted_tables:
        cols = tables_columns[table_name]
        llm_info = llm_by_name.get(table_name, {})
        tables_out.append(
            {
                "name": table_name,
                "database": payload.database,
                "schema": payload.schema_name,
                "estimated_row_count": row_counts.get(table_name, 0),
                "column_count": len(cols),
                "description": llm_info.get("description", ""),
                "purpose": llm_info.get("purpose", "unknown"),
                "key_columns": llm_info.get("key_columns", []),
                "existing_description_coverage": _description_coverage(cols),
            }
        )

    return {
        "status": "completed",
        "model": model,
        "database": payload.database,
        "schema": payload.schema_name,
        "table_count": len(tables_out),
        "tables": tables_out,
        "relationships": relationships,
        "summary_stats": summary_stats,
    }


def _description_coverage(columns: list[dict[str, object]]) -> dict[str, object]:
    total = len(columns)
    described = sum(1 for c in columns if c.get("description"))
    return {
        "total_columns": total,
        "described_columns": described,
        "percent": round(described / total * 100, 1) if total else 0.0,
    }


if __name__ == "__main__":
    main()
