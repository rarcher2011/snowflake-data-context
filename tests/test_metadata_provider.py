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

    def execute(self, sql: str) -> object:
        self.executed_sql.append(sql)
        if "INFORMATION_SCHEMA.TABLES" in sql:
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
        else:
            self._rows = []
        return self

    def fetchall(self) -> list[object]:
        return self._rows


class FakeMetadataConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakeMetadataCursor()

    def cursor(self) -> FakeMetadataCursor:
        return self.cursor_instance


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
    assert "TABLE_SCHEMA = 'PUBLIC'" in connection.cursor_instance.executed_sql[0]


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
