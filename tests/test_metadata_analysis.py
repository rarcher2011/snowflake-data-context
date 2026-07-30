from openai_snowflake_agent_context import analyze_table_metadata_descriptions
from openai_snowflake_agent_context.metadata import TableContext
from openai_snowflake_agent_context.metadata_analysis import (
    QUALITY_MISSING,
    QUALITY_STRONG,
    QUALITY_WEAK,
    parse_column_description,
    score_description,
)


def test_analyze_table_metadata_descriptions_rolls_up_column_quality() -> None:
    analysis = analyze_table_metadata_descriptions(
        [
            TableContext(
                database="ANALYTICS",
                schema="PUBLIC",
                name="ORDERS",
                kind="TABLE",
                description="Order fact table with one row per customer order.",
                columns=(
                    "ORDER_ID NUMBER -- Unique identifier for an order from the commerce system.",
                    "CUSTOMER_ID NUMBER -- id",
                    "ORDER_TOTAL NUMBER",
                    "ORDER_STATUS TEXT -- Current lifecycle status used by fulfillment teams.",
                ),
                context_markdown="",
            )
        ]
    )

    assert analysis.total_tables == 1
    assert analysis.total_columns == 4
    assert analysis.described_columns == 3
    assert analysis.missing_column_descriptions == 1
    assert analysis.weak_column_descriptions == 1
    assert analysis.strong_column_descriptions == 2
    assert analysis.description_coverage == 0.75

    needs_improvement = analysis.columns_needing_improvement
    assert [column.column_name for column in needs_improvement] == ["CUSTOMER_ID", "ORDER_TOTAL"]
    assert needs_improvement[0].result.quality == QUALITY_WEAK
    assert needs_improvement[1].result.quality == QUALITY_MISSING


def test_schema_description_analysis_renders_context_markdown() -> None:
    analysis = analyze_table_metadata_descriptions(
        [
            TableContext(
                database="ANALYTICS",
                schema="PUBLIC",
                name="ORDERS",
                kind="TABLE",
                description="Order fact table with one row per customer order.",
                columns=(
                    "ORDER_ID NUMBER -- Unique identifier for an order from the commerce system.",
                    "CUSTOMER_ID NUMBER -- id",
                    "ORDER_TOTAL NUMBER",
                ),
                context_markdown="",
            )
        ]
    )

    context = analysis.to_context_markdown()

    assert "# Snowflake Metadata Description Analysis" in context
    assert "- Tables analyzed: 1" in context
    assert "- Description coverage: 66.7%" in context
    assert "ANALYTICS.PUBLIC.ORDERS.CUSTOMER_ID: weak" in context
    assert "ANALYTICS.PUBLIC.ORDERS.ORDER_TOTAL: missing" in context
    assert "description is generic" in context
    assert "Add a description that explains what ORDER_TOTAL represents" in context
    assert "ORDER_ID: strong" in context


def test_schema_description_analysis_can_render_only_columns_needing_improvement() -> None:
    analysis = analyze_table_metadata_descriptions(
        [
            TableContext(
                database="ANALYTICS",
                schema="PUBLIC",
                name="ORDERS",
                kind="TABLE",
                description="Order fact table with one row per customer order.",
                columns=(
                    "ORDER_ID NUMBER -- Unique identifier for an order from the commerce system.",
                    "CUSTOMER_ID NUMBER -- id",
                ),
                context_markdown="",
            )
        ]
    )

    context = analysis.to_context_markdown(include_all_columns=False)

    assert "CUSTOMER_ID: weak" in context
    assert "ORDER_ID: strong" not in context


def test_parse_column_description_accepts_common_compact_formats() -> None:
    assert parse_column_description("ORDER_ID NUMBER -- Unique order identifier.") == (
        "ORDER_ID",
        "Unique order identifier.",
    )
    assert parse_column_description("ORDER_DATE DATE: Date the customer submitted the order.") == (
        "ORDER_DATE",
        "Date the customer submitted the order.",
    )
    assert parse_column_description("STATUS | Current business lifecycle status.") == (
        "STATUS",
        "Current business lifecycle status.",
    )
    assert parse_column_description("TOTAL_AMOUNT NUMBER") == ("TOTAL_AMOUNT", None)


def test_score_description_flags_missing_generic_and_strong_descriptions() -> None:
    missing = score_description("CUSTOMER_ID", None)
    generic = score_description("CUSTOMER_ID", "id")
    strong = score_description(
        "CUSTOMER_ID",
        "Unique customer identifier from the billing system used to join account activity.",
    )

    assert missing.quality == QUALITY_MISSING
    assert generic.quality == QUALITY_WEAK
    assert "generic" in " ".join(generic.issues)
    assert strong.quality == QUALITY_STRONG
    assert strong.recommendation is None
