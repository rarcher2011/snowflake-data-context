import pytest

from openai_snowflake_agent_context.ui_backend import (
    build_connection_status,
    build_env_snowflake_config,
    create_env_connection_factory,
    create_ui_app,
    describe_snowflake_table,
    fetch_snowflake_identity,
    list_snowflake_databases,
    list_snowflake_schemas,
    list_snowflake_tables,
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
        if self.executed_sql[-1] == "SELECT CURRENT_DATABASE()":
            return [(self.current_database,)]
        if self.executed_sql[-1] == "SHOW DATABASES":
            return [
                ("2026-08-20", "ANALYTICS"),
                {"name": "RAW"},
                WarehouseRow("REPORTING"),
            ]
        if self.executed_sql[-1].startswith("SHOW SCHEMAS"):
            return [
                ("2026-08-20", "PUBLIC"),
                {"name": "CORE"},
                WarehouseRow("MARTS"),
            ]
        if self.executed_sql[-1].startswith("SHOW TABLES"):
            return [
                (
                    "2026-08-20",
                    "ORDERS",
                    "ANALYTICS",
                    "SAMPLE_DATA",
                    "TABLE",
                    "Order fact table.",
                    "",
                    78986,
                    3681280,
                ),
                {
                    "name": "ORDER_VIEW",
                    "kind": "VIEW",
                    "database_name": "ANALYTICS",
                    "schema_name": "SAMPLE_DATA",
                    "comment": "",
                },
            ]
        if "INFORMATION_SCHEMA.COLUMNS" in self.executed_sql[-1]:
            return [
                ("ORDER_ID", "NUMBER", "Unique order identifier.", "NO", 1),
                {
                    "COLUMN_NAME": "CUSTOMER_ID",
                    "DATA_TYPE": "VARCHAR",
                    "COMMENT": "",
                    "IS_NULLABLE": "YES",
                    "ORDINAL_POSITION": 2,
                },
            ]
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


class FakeLLMResponse:
    output_text = (
        '{"columns":[{"name":"ORDER_ID","description":"Unique order identifier.",'
        '"rationale":"Existing description is already specific."},'
        '{"name":"CUSTOMER_ID","description":"Identifier for the customer associated with the row.",'
        '"rationale":"Names the business entity and relationship."}]}'
    )


class FakeLLMResponses:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    def create(self, **kwargs: object) -> object:
        self.kwargs = kwargs
        return FakeLLMResponse()


class FakeLLMClient:
    def __init__(self) -> None:
        self.responses = FakeLLMResponses()


def test_list_snowflake_warehouses_executes_show_warehouses_and_closes_connection() -> None:
    connection = FakeConnection()

    warehouses = list_snowflake_warehouses(lambda: connection)

    assert warehouses == ["AGENT_WH", "ANALYST_WH", "TRANSFORM_WH"]
    assert connection.cursor_instance.executed_sql == ["SHOW WAREHOUSES"]
    assert connection.closed is True


def test_list_snowflake_databases_executes_show_databases_and_closes_connection() -> None:
    connection = FakeConnection()

    databases = list_snowflake_databases(lambda: connection)

    assert databases == ["ANALYTICS", "RAW", "REPORTING"]
    assert connection.cursor_instance.executed_sql == ["SHOW DATABASES"]
    assert connection.closed is True


def test_list_snowflake_schemas_uses_selected_warehouse_and_database() -> None:
    connection = FakeConnection()

    schemas = list_snowflake_schemas(
        lambda: connection,
        warehouse="ANALYST_WH",
        database="ANALYTICS",
    )

    assert schemas == ["PUBLIC", "CORE", "MARTS"]
    assert connection.cursor_instance.executed_sql == [
        'USE WAREHOUSE "ANALYST_WH"',
        'SHOW SCHEMAS IN DATABASE "ANALYTICS"',
    ]
    assert connection.closed is True


def test_list_snowflake_schemas_escapes_identifier_quotes() -> None:
    connection = FakeConnection()

    list_snowflake_schemas(
        lambda: connection,
        warehouse='AGENT"WH',
        database='ANALYTICS"DEV',
    )

    assert connection.cursor_instance.executed_sql == [
        'USE WAREHOUSE "AGENT""WH"',
        'SHOW SCHEMAS IN DATABASE "ANALYTICS""DEV"',
    ]


def test_list_snowflake_tables_handles_not_selected_database_with_schema() -> None:
    connection = FakeConnection()

    tables = list_snowflake_tables(
        lambda: connection,
        warehouse="COMPUTE_WH",
        database="Not selected",
        schema="SAMPLE_DATA",
    )

    assert tables == [
        {
            "database": "ANALYTICS",
            "schema": "SAMPLE_DATA",
            "name": "ORDERS",
            "type": "BASE TABLE",
            "descriptionStatus": "strong",
        },
        {
            "database": "ANALYTICS",
            "schema": "SAMPLE_DATA",
            "name": "ORDER_VIEW",
            "type": "VIEW",
            "descriptionStatus": "missing",
        },
    ]
    assert connection.cursor_instance.executed_sql == [
        'USE WAREHOUSE "COMPUTE_WH"',
        "SELECT CURRENT_DATABASE()",
        'SHOW TABLES IN SCHEMA "ANALYTICS"."SAMPLE_DATA"',
    ]
    assert connection.closed is True


def test_list_snowflake_tables_requires_database_when_schema_has_no_context() -> None:
    connection = FakeConnection(current_database=None)

    with pytest.raises(
        ValueError,
        match="A database must be selected or configured before listing schema tables.",
    ):
        list_snowflake_tables(
            lambda: connection,
            warehouse="COMPUTE_WH",
            database="Not selected",
            schema="SAMPLE_DATA",
        )

    assert connection.cursor_instance.executed_sql == [
        'USE WAREHOUSE "COMPUTE_WH"',
        "SELECT CURRENT_DATABASE()",
    ]
    assert connection.closed is True


def test_list_snowflake_tables_uses_database_and_schema_when_selected() -> None:
    connection = FakeConnection()

    list_snowflake_tables(
        lambda: connection,
        warehouse="COMPUTE_WH",
        database="ANALYTICS",
        schema="SAMPLE_DATA",
    )

    assert connection.cursor_instance.executed_sql == [
        'USE WAREHOUSE "COMPUTE_WH"',
        'SHOW TABLES IN SCHEMA "ANALYTICS"."SAMPLE_DATA"',
    ]


def test_describe_snowflake_table_returns_column_metadata() -> None:
    connection = FakeConnection()

    metadata = describe_snowflake_table(
        lambda: connection,
        warehouse="COMPUTE_WH",
        database="RBAC_DEV",
        schema="SAMPLE_DATA",
        table="GAS_SAMPLE",
    )

    assert metadata == {
        "database": "RBAC_DEV",
        "schema": "SAMPLE_DATA",
        "table": "GAS_SAMPLE",
        "columns": [
            {
                "name": "ORDER_ID",
                "dataType": "NUMBER",
                "description": "Unique order identifier.",
                "nullable": "NO",
            },
            {
                "name": "CUSTOMER_ID",
                "dataType": "VARCHAR",
                "description": "",
                "nullable": "YES",
            },
        ],
    }
    assert connection.cursor_instance.executed_sql == [
        'USE WAREHOUSE "COMPUTE_WH"',
        (
            "SELECT COLUMN_NAME, DATA_TYPE, COMMENT, IS_NULLABLE, ORDINAL_POSITION "
            'FROM "RBAC_DEV".INFORMATION_SCHEMA.COLUMNS '
            "WHERE UPPER(TABLE_SCHEMA) = UPPER('SAMPLE_DATA') "
            "AND UPPER(TABLE_NAME) = UPPER('GAS_SAMPLE') "
            "ORDER BY ORDINAL_POSITION"
        ),
    ]
    assert connection.closed is True


def test_ui_app_exposes_metadata_description_analysis_endpoint() -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_ui_app(connection_factory=lambda: FakeConnection()))

    response = client.post(
        "/metadata/description-analysis",
        json={
            "tables": [
                {
                    "database": "RBAC_DEV",
                    "schema": "SAMPLE_DATA",
                    "name": "GAS_SAMPLE",
                    "kind": "TABLE",
                    "description": None,
                    "columns": [
                        "ORDER_ID NUMBER -- Unique order identifier.",
                        "CUSTOMER_ID VARCHAR",
                    ],
                    "context_markdown": "",
                }
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_tables"] == 1
    assert payload["total_columns"] == 2
    assert payload["described_columns"] == 1
    assert payload["missing_column_descriptions"] == 1


def test_ui_app_scaffolds_column_description_save_endpoint() -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_ui_app(connection_factory=lambda: FakeConnection()))

    response = client.post(
        "/api/snowflake/column-descriptions",
        json={
            "database": "RBAC_DEV",
            "schema": "SAMPLE_DATA",
            "table": "GAS_SAMPLE",
            "columns": [
                {"name": "ORDER_ID", "description": "Unique order identifier."},
                {"name": "CUSTOMER_ID", "description": "Customer identifier."},
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "scaffolded",
        "persisted": False,
        "columnsReceived": 2,
    }


def test_ui_app_uses_llm_client_for_description_suggestions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setenv("OPENAI_DESCRIPTION_MODEL", "test-description-model")
    llm_client = FakeLLMClient()
    client = TestClient(
        create_ui_app(
            connection_factory=lambda: FakeConnection(),
            llm_client_factory=lambda: llm_client,
        )
    )

    response = client.post(
        "/api/snowflake/description-suggestions",
        json={
            "database": "RBAC_DEV",
            "schema": "SAMPLE_DATA",
            "table": "GAS_SAMPLE",
            "columns": [
                {
                    "name": "ORDER_ID",
                    "dataType": "NUMBER",
                    "description": "Unique order identifier.",
                    "nullable": "NO",
                },
                {
                    "name": "CUSTOMER_ID",
                    "dataType": "VARCHAR",
                    "description": "",
                    "nullable": "YES",
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "suggested"
    assert payload["model"] == "test-description-model"
    assert payload["table"] == "RBAC_DEV.SAMPLE_DATA.GAS_SAMPLE"
    assert payload["suggestions"] == [
        {
            "name": "ORDER_ID",
            "suggestedDescription": "Unique order identifier.",
            "reason": "Existing description is already specific.",
        },
        {
            "name": "CUSTOMER_ID",
            "suggestedDescription": "Identifier for the customer associated with the row.",
            "reason": "Names the business entity and relationship.",
        },
    ]
    assert llm_client.responses.kwargs["model"] == "test-description-model"
    assert "RBAC_DEV" in str(llm_client.responses.kwargs["input"])


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
