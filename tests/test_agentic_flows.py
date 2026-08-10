from openai_snowflake_agent_context import SnowflakeContextConfig, SnowflakeMetadataProvider
from openai_snowflake_agent_context.agentic_flows import (
    DATA_ANALYST_SYSTEM_PROMPT,
    build_data_analyst_context,
    build_data_analyst_multi_agent_plan,
    run_data_analyst_agent,
)
from openai_snowflake_agent_context.metadata import TableContext


class FakeConnection:
    def cursor(self) -> object:
        return object()


class FakeProvider(SnowflakeMetadataProvider):
    def __init__(self) -> None:
        super().__init__(
            FakeConnection(),  # type: ignore[arg-type]
            SnowflakeContextConfig(
                account="test-account",
                user="analyst",
                warehouse="agent_wh",
                database="ANALYTICS",
                schema="PUBLIC",
            ),
        )
        self.requested_tables: list[str] | None = []

    def describe_tables(self, table_names: list[str] | None = None) -> list[TableContext]:
        self.requested_tables = table_names
        return [
            TableContext(
                database="ANALYTICS",
                schema="PUBLIC",
                name="ORDERS",
                kind="BASE TABLE",
                description="Order fact table with one row per customer order.",
                columns=(
                    "ORDER_ID NUMBER -- Unique identifier for an order from the commerce system.",
                    "CUSTOMER_ID NUMBER",
                    "ORDER_TOTAL NUMBER",
                    "ORDER_STATUS TEXT -- Current lifecycle status used by fulfillment teams.",
                ),
                context_markdown="",
            )
        ]


class FakeOpenAIResponse:
    output_text = "The orders table is usable, but CUSTOMER_ID and ORDER_TOTAL need metadata work."


class FakeOpenAIResponses:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> FakeOpenAIResponse:
        self.requests.append(kwargs)
        return FakeOpenAIResponse()


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.responses = FakeOpenAIResponses()


def test_build_data_analyst_context_includes_schema_scores_and_orchestration() -> None:
    provider = FakeProvider()

    context = build_data_analyst_context(
        provider,
        "Which order fields need better descriptions?",
        table_names=("ANALYTICS.PUBLIC.ORDERS",),
        work_id="QUESTION-1",
    )

    markdown = context.to_markdown()

    assert provider.requested_tables == ["ANALYTICS.PUBLIC.ORDERS"]
    assert "Which order fields need better descriptions?" in markdown
    assert "ANALYTICS.PUBLIC.ORDERS" in markdown
    assert "ORDER_TOTAL: missing" in markdown
    assert "QUESTION-1" in markdown


def test_run_data_analyst_agent_calls_openai_with_grounded_context() -> None:
    provider = FakeProvider()
    client = FakeOpenAIClient()

    result = run_data_analyst_agent(
        openai_client=client,
        provider=provider,
        question="What data gaps block order analysis?",
        model="gpt-4.1-mini",
    )

    assert result.response_text == (
        "The orders table is usable, but CUSTOMER_ID and ORDER_TOTAL need metadata work."
    )
    request = client.responses.requests[0]
    assert request["model"] == "gpt-4.1-mini"
    request_input = request["input"]
    assert DATA_ANALYST_SYSTEM_PROMPT in str(request_input)
    assert "Snowflake Metadata Context" in str(request_input)
    assert "ORDER_TOTAL: missing" in str(request_input)


def test_build_data_analyst_multi_agent_plan_creates_ready_specialist_work() -> None:
    provider = FakeProvider()

    plan = build_data_analyst_multi_agent_plan(
        provider,
        "Create an orders reporting view and identify quality risks.",
    )

    assert [assignment.agent.role_id for assignment in plan.assignments] == [
        "metadata_analyst",
        "quality_reviewer",
        "data_engineer",
    ]
    assert [assignment.assignment_id for assignment in plan.ready_assignments()] == ["A1"]
    assert [assignment.assignment_id for assignment in plan.ready_assignments(("A1",))] == [
        "A2",
        "A3",
    ]
    assert "ORDER_TOTAL: missing" in plan.shared_context
