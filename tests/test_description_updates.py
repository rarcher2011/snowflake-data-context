import pytest

from openai_snowflake_agent_context import DescriptionUpdateRequest, SnowflakeContextConfig
from openai_snowflake_agent_context.description_updates import (
    apply_description_update_plan,
    build_description_update_plan,
    quote_identifier,
    quote_sql_string,
)
from openai_snowflake_agent_context.metadata import SnowflakeMetadataProvider


class FakeCursor:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []

    def execute(self, sql: str) -> object:
        self.executed_sql.append(sql)
        return object()


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakeCursor()

    def cursor(self) -> FakeCursor:
        return self.cursor_instance


def test_build_description_update_plan_generates_table_and_column_comments() -> None:
    plan = build_description_update_plan(
        [
            DescriptionUpdateRequest(
                database="ANALYTICS",
                schema="PUBLIC",
                table="ORDERS",
                table_description="Order fact table with one row per customer order.",
                column_descriptions={
                    "ORDER_ID": "Unique order identifier from the commerce system.",
                    "CUSTOMER_ID": "Customer identifier used to join account activity.",
                },
            )
        ]
    )

    assert [statement.sql for statement in plan.statements] == [
        (
            'COMMENT ON TABLE "ANALYTICS"."PUBLIC"."ORDERS" '
            "IS 'Order fact table with one row per customer order.'"
        ),
        (
            'COMMENT ON COLUMN "ANALYTICS"."PUBLIC"."ORDERS"."ORDER_ID" '
            "IS 'Unique order identifier from the commerce system.'"
        ),
        (
            'COMMENT ON COLUMN "ANALYTICS"."PUBLIC"."ORDERS"."CUSTOMER_ID" '
            "IS 'Customer identifier used to join account activity.'"
        ),
    ]


def test_build_description_update_plan_uses_provider_defaults() -> None:
    plan = build_description_update_plan(
        [
            DescriptionUpdateRequest(
                table="CUSTOMERS",
                column_descriptions={"CUSTOMER_EMAIL": "Email address used for customer support."},
            )
        ],
        default_database="ANALYTICS",
        default_schema="PUBLIC",
    )

    assert plan.statements[0].sql == (
        'COMMENT ON COLUMN "ANALYTICS"."PUBLIC"."CUSTOMERS"."CUSTOMER_EMAIL" '
        "IS 'Email address used for customer support.'"
    )


def test_description_update_plan_escapes_quotes_and_rejects_unsafe_identifiers() -> None:
    assert quote_sql_string("Customer's preferred name") == "'Customer''s preferred name'"

    with pytest.raises(ValueError, match="Unsafe Snowflake identifier"):
        quote_identifier("ORDERS;DROP")

    with pytest.raises(ValueError, match="Description cannot be blank"):
        build_description_update_plan(
            [
                DescriptionUpdateRequest(
                    database="ANALYTICS",
                    schema="PUBLIC",
                    table="ORDERS",
                    table_description=" ",
                )
            ]
        )


def test_apply_description_update_plan_executes_each_statement_in_order() -> None:
    connection = FakeConnection()
    plan = build_description_update_plan(
        [
            DescriptionUpdateRequest(
                database="ANALYTICS",
                schema="PUBLIC",
                table="ORDERS",
                column_descriptions={"ORDER_STATUS": "Current fulfillment lifecycle status."},
            )
        ]
    )

    apply_description_update_plan(connection, plan)

    assert connection.cursor_instance.executed_sql == [
        (
            'COMMENT ON COLUMN "ANALYTICS"."PUBLIC"."ORDERS"."ORDER_STATUS" '
            "IS 'Current fulfillment lifecycle status.'"
        )
    ]


def test_provider_update_descriptions_defaults_to_dry_run() -> None:
    connection = FakeConnection()
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

    result = provider.update_descriptions(
        [
            DescriptionUpdateRequest(
                table="ORDERS",
                table_description="Order fact table with one row per customer order.",
            )
        ]
    )

    assert result.applied is False
    assert connection.cursor_instance.executed_sql == []
    assert result.plan.statements[0].sql == (
        'COMMENT ON TABLE "ANALYTICS"."PUBLIC"."ORDERS" '
        "IS 'Order fact table with one row per customer order.'"
    )


def test_provider_update_descriptions_applies_when_requested() -> None:
    connection = FakeConnection()
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

    result = provider.update_descriptions(
        [
            DescriptionUpdateRequest(
                table="ORDERS",
                column_descriptions={"ORDER_TOTAL": "Total amount charged to the customer."},
            )
        ],
        apply=True,
    )

    assert result.applied is True
    assert connection.cursor_instance.executed_sql == [
        (
            'COMMENT ON COLUMN "ANALYTICS"."PUBLIC"."ORDERS"."ORDER_TOTAL" '
            "IS 'Total amount charged to the customer.'"
        )
    ]

