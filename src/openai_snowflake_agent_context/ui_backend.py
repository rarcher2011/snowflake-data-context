"""Minimal FastAPI backend for the React Snowflake setup UI."""

from __future__ import annotations

import os
from typing import Any, Callable, Protocol, cast

from .config import SnowflakeContextConfig
from .connection import connect_with_private_key


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


def list_snowflake_warehouses(connection_factory: ConnectionFactory) -> list[str]:
    """Return warehouse names from Snowflake using `SHOW WAREHOUSES`."""

    connection = connection_factory()
    try:
        cursor = connection.cursor()
        cursor.execute("SHOW WAREHOUSES")
        return [_warehouse_name_from_row(row) for row in cursor.fetchall()]
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


def create_ui_app(
    connection_factory: ConnectionFactory | None = None,
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
        except (OSError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

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


if __name__ == "__main__":
    main()
