import pytest

from openai_snowflake_agent_context.ui_backend import (
    build_env_snowflake_config,
    create_env_connection_factory,
    list_snowflake_warehouses,
)


class FakeCursor:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []

    def execute(self, sql: str) -> object:
        self.executed_sql.append(sql)
        return self

    def fetchall(self) -> list[object]:
        return [
            ("AGENT_WH",),
            {"name": "ANALYST_WH"},
            WarehouseRow("TRANSFORM_WH"),
        ]


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakeCursor()
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
