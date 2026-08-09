from openai_snowflake_agent_context import SnowflakeContextConfig, SnowflakeMetadataProvider
from openai_snowflake_agent_context.agentic_flows import (
    DATA_ANALYST_SYSTEM_PROMPT,
    build_data_analyst_context,
    build_data_analyst_eval_data_source,
    build_data_analyst_eval_items,
    build_data_analyst_multi_agent_plan,
    create_data_analyst_eval_run,
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


class FakeEvalRun:
    id = "evalrun_123"


class FakeEvalRuns:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, object]]] = []

    def create(self, eval_id: str, **kwargs: object) -> FakeEvalRun:
        self.requests.append((eval_id, kwargs))
        return FakeEvalRun()


class FakeEvals:
    def __init__(self) -> None:
        self.runs = FakeEvalRuns()


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.responses = FakeOpenAIResponses()
        self.evals = FakeEvals()


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


def test_build_data_analyst_eval_items_and_data_source() -> None:
    provider = FakeProvider()

    items = build_data_analyst_eval_items(
        provider,
        ("Which order columns need better descriptions?",),
        table_names=("ANALYTICS.PUBLIC.ORDERS",),
        expected_outputs=("Mention CUSTOMER_ID and ORDER_TOTAL.",),
    )
    data_source = build_data_analyst_eval_data_source(items, model="gpt-4.1-mini")

    assert items[0].question == "Which order columns need better descriptions?"
    assert items[0].expected_output == "Mention CUSTOMER_ID and ORDER_TOTAL."
    assert "ORDER_TOTAL: missing" in items[0].context_markdown
    assert data_source["type"] == "completions"
    assert data_source["model"] == "gpt-4.1-mini"
    assert "Answer this analyst question" in str(data_source["input_messages"])
    assert "Which order columns need better descriptions?" in str(data_source["source"])


def test_create_data_analyst_eval_run_calls_openai_evals_api() -> None:
    provider = FakeProvider()
    client = FakeOpenAIClient()

    result = create_data_analyst_eval_run(
        openai_client=client,
        provider=provider,
        eval_id="eval_orders_agent",
        questions=("What metadata gaps block order analysis?",),
        expected_outputs=("Mention missing descriptions.",),
        run_name="orders-agent-regression",
        model="gpt-4.1-mini",
    )

    assert result.eval_id == "eval_orders_agent"
    assert result.run_name == "orders-agent-regression"
    assert result.eval_run.id == "evalrun_123"
    assert client.evals.runs.requests[0][0] == "eval_orders_agent"
    request = client.evals.runs.requests[0][1]
    assert request["name"] == "orders-agent-regression"
    assert request["data_source"] == result.data_source
    assert "What metadata gaps block order analysis?" in str(result.data_source)


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
