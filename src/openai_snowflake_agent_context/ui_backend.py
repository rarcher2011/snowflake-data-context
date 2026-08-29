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


if __name__ == "__main__":
    main()
