import pytest

from openai_snowflake_agent_context.sampling import (
    build_sample_table_sql,
    quote_snowflake_identifier_path,
    sample_table,
)


class FakeCursor:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []

    def execute(self, sql: str) -> object:
        self.executed_sql.append(sql)
        return self


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakeCursor()

    def cursor(self) -> FakeCursor:
        return self.cursor_instance


def test_build_sample_table_sql_creates_one_percent_random_sample() -> None:
    sql = build_sample_table_sql(
        "ANALYTICS.PUBLIC.ORDERS",
        "ANALYTICS.PUBLIC.ORDERS_SAMPLE",
    )

    assert sql == (
        'CREATE OR REPLACE TABLE "ANALYTICS"."PUBLIC"."ORDERS_SAMPLE" AS\n'
        "SELECT *\n"
        'FROM "ANALYTICS"."PUBLIC"."ORDERS" SAMPLE BERNOULLI (1)'
    )


def test_sample_table_executes_sql_and_returns_status_update() -> None:
    connection = FakeConnection()

    result = sample_table(
        connection,
        "ANALYTICS.PUBLIC.ORDERS",
        "ANALYTICS.PUBLIC.ORDERS_SAMPLE",
    )

    assert connection.cursor_instance.executed_sql == [result.sql]
    assert result.sample_percent == 1.0
    assert result.sampled_table == "ANALYTICS.PUBLIC.ORDERS_SAMPLE"
    assert result.to_status_update()["sampled_table"] == "ANALYTICS.PUBLIC.ORDERS_SAMPLE"


def test_sample_table_supports_custom_sample_percent() -> None:
    sql = build_sample_table_sql(
        "ANALYTICS.PUBLIC.ORDERS",
        "ANALYTICS.PUBLIC.ORDERS_SAMPLE",
        sample_percent=0.5,
    )

    assert "SAMPLE BERNOULLI (0.5)" in sql


def test_sample_table_rejects_invalid_sample_percent() -> None:
    with pytest.raises(ValueError, match="sample_percent"):
        build_sample_table_sql(
            "ANALYTICS.PUBLIC.ORDERS",
            "ANALYTICS.PUBLIC.ORDERS_SAMPLE",
            sample_percent=0,
        )


def test_quote_snowflake_identifier_path_quotes_each_segment() -> None:
    assert (
        quote_snowflake_identifier_path('Analytics."Public.Schema".Orders')
        == '"Analytics"."Public.Schema"."Orders"'
    )


def test_quote_snowflake_identifier_path_rejects_empty_segments() -> None:
    with pytest.raises(ValueError, match="empty path segment"):
        quote_snowflake_identifier_path("ANALYTICS..ORDERS")
