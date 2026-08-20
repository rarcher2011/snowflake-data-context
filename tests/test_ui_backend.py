import pytest

from openai_snowflake_agent_context.ui_backend import (
    build_connection_status,
    build_env_snowflake_config,
    create_env_connection_factory,
    fetch_snowflake_identity,
    list_snowflake_warehouses,
)


class FakeCursor:
    def __init__(self, current_database: str | None = "ANALYTICS") -> None:
        self.executed_sql: list[str] = []
        self.current_database = current_database

    def execute(self, sql: str) -> object:
        self.executed_sql.append(sql)
        return self

    def fetchall(self) -> list[object]:
        if self.executed_sql[-1] == "SELECT CURRENT_USER(), CURRENT_DATABASE()":
            return [("AGENT_USER", self.current_database)]
        return [
            ("AGENT_WH",),
            {"name": "ANALYST_WH"},
            WarehouseRow("TRANSFORM_WH"),
        ]


class FakeConnection:
    def __init__(self, current_database: str | None = "ANALYTICS") -> None:
        self.cursor_instance = FakeCursor(current_database=current_database)
        self.closed = False

    def cursor(self) -> FakeCursor:
        return self.cursor_instance

    def close(self) -> None:
        self.closed = True


class WarehouseRow:
    def __init__(self, name: str) -> None:
        self.name = name


def test_list_snowflake_warehouses_executes_show_warehouses_and_closes_connection() -> None:
    connection = FakeConnection()

    warehouses = list_snowflake_warehouses(lambda: connection)

    assert warehouses == ["AGENT_WH", "ANALYST_WH", "TRANSFORM_WH"]
    assert connection.cursor_instance.executed_sql == ["SHOW WAREHOUSES"]
    assert connection.closed is True


def test_fetch_snowflake_identity_returns_current_user_and_database() -> None:
    connection = FakeConnection()

    identity = fetch_snowflake_identity(lambda: connection)

    assert identity == {
        "current_user": "AGENT_USER",
        "current_database": "ANALYTICS",
    }
    assert connection.cursor_instance.executed_sql == [
        "SELECT CURRENT_USER(), CURRENT_DATABASE()",
    ]
    assert connection.closed is True


def test_build_connection_status_reports_working_private_key_connection() -> None:
    status = build_connection_status(
        {
            "SNOWFLAKE_ACCOUNT": "test-account",
            "SNOWFLAKE_USER": "configured_user",
            "SNOWFLAKE_WAREHOUSE": "AGENT_WH",
            "SNOWFLAKE_DATABASE": "ANALYTICS",
            "SNOWFLAKE_SCHEMA": "PUBLIC",
            "SNOWFLAKE_PRIVATE_KEY_PATH": "/tmp/snowflake_key.p8",
        },
        connection_factory=lambda: FakeConnection(),
    )

    assert status["configured"] is True
    assert status["account"] == "test-account"
    assert status["configuredUser"] == "configured_user"
    assert status["currentUser"] == "AGENT_USER"
    assert status["database"] == "ANALYTICS"
    assert status["schema"] == "PUBLIC"
    assert status["privateKeyConfigured"] is True
    assert status["privateKeyConnectionWorking"] is True
    assert status["error"] is None


def test_build_connection_status_reports_missing_database_as_not_selected() -> None:
    status = build_connection_status(
        {
            "SNOWFLAKE_ACCOUNT": "test-account",
            "SNOWFLAKE_USER": "configured_user",
            "SNOWFLAKE_WAREHOUSE": "AGENT_WH",
            "SNOWFLAKE_PRIVATE_KEY_PATH": "/tmp/snowflake_key.p8",
        },
        connection_factory=lambda: FakeConnection(current_database=None),
    )

    assert status["database"] == "Not selected"
    assert status["schema"] == "Not selected"


def test_build_connection_status_reports_missing_required_environment() -> None:
    status = build_connection_status({})

    assert status["configured"] is False
    assert status["account"] == "Not configured"
    assert status["currentUser"] == "Not configured"
    assert status["database"] == "Not selected"
    assert status["privateKeyConfigured"] is False
    assert status["privateKeyConnectionWorking"] is False
    assert "SNOWFLAKE_ACCOUNT" in str(status["error"])


def test_build_env_snowflake_config_uses_private_key_environment() -> None:
    config = build_env_snowflake_config(
        {
            "SNOWFLAKE_ACCOUNT": "test-account",
            "SNOWFLAKE_USER": "agent_user",
            "SNOWFLAKE_WAREHOUSE": "AGENT_WH",
            "SNOWFLAKE_ROLE": "ANALYST",
            "SNOWFLAKE_DATABASE": "ANALYTICS",
            "SNOWFLAKE_SCHEMA": "PUBLIC",
            "SNOWFLAKE_PRIVATE_KEY_PATH": "/tmp/snowflake_key.p8",
        }
    )

    assert config.account == "test-account"
    assert config.user == "agent_user"
    assert config.warehouse == "AGENT_WH"
    assert config.role == "ANALYST"
    assert config.database == "ANALYTICS"
    assert config.schema == "PUBLIC"
    assert config.private_key_path == "/tmp/snowflake_key.p8"


def test_build_env_snowflake_config_requires_private_key_path() -> None:
    with pytest.raises(ValueError, match="SNOWFLAKE_PRIVATE_KEY_PATH"):
        build_env_snowflake_config(
            {
                "SNOWFLAKE_ACCOUNT": "test-account",
                "SNOWFLAKE_USER": "agent_user",
                "SNOWFLAKE_WAREHOUSE": "AGENT_WH",
            }
        )


def test_create_env_connection_factory_returns_callable() -> None:
    factory = create_env_connection_factory(
        {
            "SNOWFLAKE_ACCOUNT": "test-account",
            "SNOWFLAKE_USER": "agent_user",
            "SNOWFLAKE_WAREHOUSE": "AGENT_WH",
            "SNOWFLAKE_PRIVATE_KEY_PATH": "/tmp/snowflake_key.p8",
        }
    )

    assert callable(factory)
