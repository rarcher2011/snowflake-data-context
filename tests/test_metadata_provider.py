import pytest

from openai_snowflake_agent_context import SnowflakeContextConfig, SnowflakeMetadataProvider
from openai_snowflake_agent_context.metadata import TableContext


class FakeConnection:
    def cursor(self) -> object:
        return object()


def test_describe_tables_declares_unimplemented_provider_contract() -> None:
    provider = SnowflakeMetadataProvider(
        FakeConnection(),
        SnowflakeContextConfig(
            account="test-account",
            user="analyst",
            warehouse="agent_wh",
        ),
    )

    with pytest.raises(NotImplementedError, match="not implemented"):
        provider.describe_tables(["ANALYTICS.PUBLIC.ORDERS"])


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

