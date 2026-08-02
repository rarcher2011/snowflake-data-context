import pytest

from openai_snowflake_agent_context import SnowflakeContextConfig, SnowflakeMetadataProvider
from openai_snowflake_agent_context.metadata import TableContext


class FakeConnection:
    def cursor(self) -> object:
        return object()


class FakeSamplingCursor:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []

    def execute(self, sql: str) -> object:
        self.executed_sql.append(sql)
        return self


class FakeSamplingConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakeSamplingCursor()

    def cursor(self) -> FakeSamplingCursor:
        return self.cursor_instance


class FakeMetadataCursor:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []
        self._rows: list[object] = []
        self.description: list[tuple[str]] = []

    def execute(self, sql: str) -> object:
        self.executed_sql.append(sql)
        if "INFORMATION_SCHEMA.TABLES" in sql:
            self.description = [
                ("TABLE_CATALOG",),
                ("TABLE_SCHEMA",),
                ("TABLE_NAME",),
                ("TABLE_TYPE",),
                ("COMMENT",),
            ]
            self._rows = [
                (
                    "ANALYTICS",
                    "PUBLIC",
                    "ORDERS",
                    "BASE TABLE",
                    "Order fact table with one row per customer order.",
                ),
                (
                    "ANALYTICS",
                    "PUBLIC",
                    "CUSTOMERS",
                    "BASE TABLE",
                    None,
                ),
            ]
        elif "INFORMATION_SCHEMA.COLUMNS" in sql:
            self.description = [
                ("TABLE_CATALOG",),
                ("TABLE_SCHEMA",),
                ("TABLE_NAME",),
                ("COLUMN_NAME",),
                ("DATA_TYPE",),
                ("COMMENT",),
                ("ORDINAL_POSITION",),
            ]
            self._rows = [
                (
                    "ANALYTICS",
                    "PUBLIC",
                    "ORDERS",
                    "ORDER_ID",
                    "NUMBER",
                    "Unique identifier for an order from the commerce system.",
                    1,
                ),
                (
                    "ANALYTICS",
                    "PUBLIC",
                    "ORDERS",
                    "CUSTOMER_ID",
                    "NUMBER",
                    None,
                    2,
                ),
                (
                    "ANALYTICS",
                    "PUBLIC",
                    "CUSTOMERS",
                    "CUSTOMER_ID",
                    "NUMBER",
                    "Customer identifier from the CRM source system.",
                    1,
                ),
            ]
        elif "ORDER BY RANDOM()" in sql:
            self.description = [("ORDER_ID",), ("CUSTOMER_ID",)]
            self._rows = [(1001, 501), (1002, 502)]
        else:
            self.description = []
            self._rows = []
        return self

    def fetchall(self) -> list[object]:
        return self._rows


class FakeMetadataConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakeMetadataCursor()

    def cursor(self) -> FakeMetadataCursor:
        return self.cursor_instance


class FakeOpenAIResponse:
    output_text = (
        '{"columns": ['
        '{"name": "ORDER_ID", "description": '
        '"Unique identifier for a customer order in the commerce system.", '
        '"rationale": "Values are unique order keys."}, '
        '{"name": "CUSTOMER_ID", "description": '
        '"Customer identifier used to join orders to customer records.", '
        '"rationale": "Sample values link each order to a customer."}'
        "]}"
    )


class FakeOpenAIResponses:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> FakeOpenAIResponse:
        self.requests.append(kwargs)
        return FakeOpenAIResponse()


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.responses = FakeOpenAIResponses()


class FakeMetadataProvider(SnowflakeMetadataProvider):
    def __init__(self) -> None:
        super().__init__(
            FakeConnection(),
            SnowflakeContextConfig(
                account="test-account",
                user="analyst",
                warehouse="agent_wh",
                database="ANALYTICS",
                schema="PUBLIC",
            ),
        )
        self.requested_table_names: list[str] | None = []

    def describe_tables(self, table_names: list[str] | None = None) -> list[TableContext]:
        self.requested_table_names = table_names
        return [
            TableContext(
                database="ANALYTICS",
                schema="PUBLIC",
                name="ORDERS",
                kind="TABLE",
                description="Order fact table with one row per customer order.",
                columns=(
                    "ORDER_ID NUMBER -- Unique identifier for an order from the commerce system.",
                    "CUSTOMER_ID NUMBER",
                ),
                context_markdown="",
            )
        ]


def test_describe_tables_fetches_information_schema_metadata() -> None:
    connection = FakeMetadataConnection()
    provider = SnowflakeMetadataProvider(
        connection,
        SnowflakeContextConfig(
            account="test-account",
            user="analyst",
            warehouse="agent_wh",
            database="ANALYTICS",
            schema="PUBLIC",
        ),
    )

    tables = provider.describe_tables()

    assert [table.name for table in tables] == ["ORDERS", "CUSTOMERS"]
    assert tables[0].description == "Order fact table with one row per customer order."
    assert tables[0].columns == (
        "ORDER_ID NUMBER -- Unique identifier for an order from the commerce system.",
        "CUSTOMER_ID NUMBER",
    )
    assert "ANALYTICS.PUBLIC.ORDERS" in tables[0].context_markdown
    assert "ANALYTICS.INFORMATION_SCHEMA.TABLES" in connection.cursor_instance.executed_sql[0]
    assert "UPPER(TABLE_SCHEMA) = UPPER('PUBLIC')" in connection.cursor_instance.executed_sql[0]


def test_describe_tables_filters_explicit_table_names() -> None:
    provider = SnowflakeMetadataProvider(
        FakeMetadataConnection(),
        SnowflakeContextConfig(
            account="test-account",
            user="analyst",
            warehouse="agent_wh",
            database="ANALYTICS",
            schema="PUBLIC",
        ),
    )

    tables = provider.describe_tables(["ANALYTICS.PUBLIC.CUSTOMERS"])

    assert [table.name for table in tables] == ["CUSTOMERS"]


def test_describe_tables_compares_configured_schema_case_insensitively() -> None:
    connection = FakeMetadataConnection()
    provider = SnowflakeMetadataProvider(
        connection,
        SnowflakeContextConfig(
            account="test-account",
            user="analyst",
            warehouse="agent_wh",
            database="ANALYTICS",
            schema="public",
        ),
    )

    provider.describe_tables()

    assert "UPPER(TABLE_SCHEMA) = UPPER('public')" in connection.cursor_instance.executed_sql[0]
    assert "UPPER(TABLE_SCHEMA) = UPPER('public')" in connection.cursor_instance.executed_sql[1]


def test_analyze_schema_descriptions_uses_live_describe_tables() -> None:
    provider = SnowflakeMetadataProvider(
        FakeMetadataConnection(),
        SnowflakeContextConfig(
            account="test-account",
            user="analyst",
            warehouse="agent_wh",
            database="ANALYTICS",
            schema="PUBLIC",
        ),
    )

    analysis = provider.analyze_schema_descriptions(["ORDERS"])

    assert analysis.total_tables == 1
    assert analysis.total_columns == 2
    assert [column.column_name for column in analysis.columns_needing_improvement] == ["CUSTOMER_ID"]


def test_table_context_holds_agent_ready_markdown() -> None:
    table = TableContext(
        database="ANALYTICS",
        schema="PUBLIC",
        name="ORDERS",
        kind="TABLE",
        description="Customer order facts.",
        columns=("ORDER_ID NUMBER", "CUSTOMER_ID NUMBER", "ORDER_DATE DATE"),
        context_markdown="### ANALYTICS.PUBLIC.ORDERS\n- Grain: one row per order.",
    )

    assert table.database == "ANALYTICS"
    assert table.columns == ("ORDER_ID NUMBER", "CUSTOMER_ID NUMBER", "ORDER_DATE DATE")
    assert "one row per order" in table.context_markdown


def test_analyze_schema_descriptions_uses_all_tables_when_table_names_omitted() -> None:
    provider = FakeMetadataProvider()

    analysis = provider.analyze_schema_descriptions()

    assert provider.requested_table_names is None
    assert analysis.total_tables == 1
    assert analysis.total_columns == 2
    assert [column.column_name for column in analysis.columns_needing_improvement] == ["CUSTOMER_ID"]


def test_analyze_schema_descriptions_passes_explicit_table_names() -> None:
    provider = FakeMetadataProvider()

    provider.analyze_schema_descriptions(["ANALYTICS.PUBLIC.ORDERS"])

    assert provider.requested_table_names == ["ANALYTICS.PUBLIC.ORDERS"]


def test_provider_sample_table_delegates_to_sampling_helper() -> None:
    connection = FakeSamplingConnection()
    provider = SnowflakeMetadataProvider(
        connection,
        SnowflakeContextConfig(
            account="test-account",
            user="analyst",
            warehouse="agent_wh",
        ),
    )

    result = provider.sample_table(
        "ANALYTICS.PUBLIC.ORDERS",
        "ANALYTICS.PUBLIC.ORDERS_SAMPLE",
    )

    assert result.sampled_table == "ANALYTICS.PUBLIC.ORDERS_SAMPLE"
    assert connection.cursor_instance.executed_sql == [result.sql]


def test_provider_suggest_column_descriptions_samples_rows_and_calls_openai() -> None:
    connection = FakeMetadataConnection()
    openai_client = FakeOpenAIClient()
    provider = SnowflakeMetadataProvider(
        connection,
        SnowflakeContextConfig(
            account="test-account",
            user="analyst",
            warehouse="agent_wh",
            database="ANALYTICS",
            schema="PUBLIC",
        ),
    )

    result = provider.suggest_column_descriptions(
        "ANALYTICS.PUBLIC.ORDERS",
        openai_client,
        model="gpt-4.1-mini",
        sample_size=2,
    )

    assert result.table_identifier == "ANALYTICS.PUBLIC.ORDERS"
    assert result.sample_records == (
        {"ORDER_ID": 1001, "CUSTOMER_ID": 501},
        {"ORDER_ID": 1002, "CUSTOMER_ID": 502},
    )
    assert result.column_descriptions == {
        "ORDER_ID": "Unique identifier for a customer order in the commerce system.",
        "CUSTOMER_ID": "Customer identifier used to join orders to customer records.",
    }
    assert result.sample_sql == (
        'SELECT *\nFROM "ANALYTICS"."PUBLIC"."ORDERS"\nORDER BY RANDOM()\nLIMIT 2'
    )
    assert connection.cursor_instance.executed_sql[-1] == result.sample_sql
    assert openai_client.responses.requests[0]["model"] == "gpt-4.1-mini"
    request_input = openai_client.responses.requests[0]["input"]
    assert '"name": "CUSTOMER_ID"' in str(request_input)
    assert '"data_type": "NUMBER"' in str(request_input)
    assert '"ORDER_ID": 1001' in str(request_input)


def test_provider_suggest_column_descriptions_requires_table_metadata() -> None:
    provider = SnowflakeMetadataProvider(
        FakeMetadataConnection(),
        SnowflakeContextConfig(
            account="test-account",
            user="analyst",
            warehouse="agent_wh",
            database="ANALYTICS",
            schema="PUBLIC",
        ),
    )

    with pytest.raises(ValueError, match="No Snowflake table metadata"):
        provider.suggest_column_descriptions("ANALYTICS.PUBLIC.MISSING", FakeOpenAIClient())


@pytest.mark.xfail(reason="Formatter module will be implemented during the next TDD phase.")
def test_future_formatter_packs_table_context_into_markdown() -> None:
    from openai_snowflake_agent_context.formatter import format_table_context

    table = TableContext(
        database="ANALYTICS",
        schema="PUBLIC",
        name="ORDERS",
        kind="TABLE",
        description="Customer order facts.",
        columns=("ORDER_ID NUMBER",),
        context_markdown="",
    )

    markdown = format_table_context([table], token_budget=500)

    assert "ANALYTICS.PUBLIC.ORDERS" in markdown
    assert "ORDER_ID NUMBER" in markdown


@pytest.mark.xfail(reason="OpenAI wrapper will be implemented after context formatting exists.")
def test_future_openai_wrapper_preserves_callable_result() -> None:
    from openai_snowflake_agent_context.openai_extensions import with_snowflake_context

    def fake_openai_call(**kwargs: object) -> dict[str, object]:
        return {"kwargs": kwargs}

    provider = SnowflakeMetadataProvider(
        FakeConnection(),
        SnowflakeContextConfig(
            account="test-account",
            user="analyst",
            warehouse="agent_wh",
        ),
    )

    result = with_snowflake_context(
        fake_openai_call,
        provider=provider,
        tables=["ANALYTICS.PUBLIC.ORDERS"],
        model="gpt-4.1",
        input="Write a query.",
    )

    assert result["kwargs"]["model"] == "gpt-4.1"
