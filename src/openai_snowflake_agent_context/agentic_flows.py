"""Agentic data analyst flows built on Snowflake metadata context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from .agent_harness import WorkItem
from .agent_orchestrator import AgentOrchestrator, MultiAgentPlan, OrchestratorDecision
from .metadata import SnowflakeMetadataProvider


class OpenAIResponsesResource(Protocol):
    """Minimal OpenAI Responses API surface used by the analyst flows."""

    def create(self, **kwargs: Any) -> object:
        """Create a model response."""


class OpenAIEvalRunsResource(Protocol):
    """Minimal OpenAI Evals run API surface used by the analyst flows."""

    def create(self, eval_id: str, **kwargs: Any) -> object:
        """Create an eval run."""


class OpenAIEvalsResource(Protocol):
    """Minimal OpenAI Evals API surface used by the analyst flows."""

    runs: OpenAIEvalRunsResource


class OpenAIClient(Protocol):
    """Minimal OpenAI client protocol expected by the analyst flows."""

    responses: OpenAIResponsesResource
    evals: OpenAIEvalsResource


@dataclass(frozen=True)
class DataAnalystAgentContext:
    """Context bundle prepared for a data analyst agent."""

    question: str
    schema_context: str
    orchestration_decision: OrchestratorDecision

    def to_markdown(self) -> str:
        """Render data analyst context for an OpenAI request."""

        return "\n\n".join(
            (
                "# Data Analyst Agent Context",
                f"Question: {self.question}",
                "## Snowflake Metadata Context",
                self.schema_context,
                "## Orchestration",
                self.orchestration_decision.to_markdown(),
            )
        )


@dataclass(frozen=True)
class DataAnalystAgentResult:
    """Response and context from a data analyst agent run."""

    question: str
    model: str
    response_text: str
    context: DataAnalystAgentContext

    def to_markdown(self) -> str:
        """Render the analyst response with its source context."""

        return "\n\n".join(
            (
                "# Data Analyst Agent Result",
                f"- Model: {self.model}",
                f"- Question: {self.question}",
                "",
                "## Response",
                self.response_text,
                "",
                "## Context",
                self.context.to_markdown(),
            )
        )


@dataclass(frozen=True)
class DataAnalystEvalItem:
    """One OpenAI eval item for the data analyst agent."""

    question: str
    context_markdown: str
    expected_output: str | None = None

    def to_eval_item(self) -> dict[str, object]:
        """Return an eval item compatible with file_content eval data sources."""

        item: dict[str, object] = {
            "question": self.question,
            "context": self.context_markdown,
        }
        if self.expected_output:
            item["expected_output"] = self.expected_output
        return {"item": item}


@dataclass(frozen=True)
class DataAnalystEvalRunResult:
    """Metadata returned after creating an OpenAI eval run for the analyst agent."""

    eval_id: str
    run_name: str
    eval_items: tuple[DataAnalystEvalItem, ...]
    data_source: dict[str, object]
    eval_run: object


def build_data_analyst_context(
    provider: SnowflakeMetadataProvider,
    question: str,
    *,
    table_names: Sequence[str] | None = None,
    orchestrator: AgentOrchestrator | None = None,
    work_id: str = "DATA-ANALYST-1",
) -> DataAnalystAgentContext:
    """Build Snowflake and orchestration context for a data analyst agent."""

    analysis = provider.analyze_schema_descriptions(list(table_names) if table_names else None)
    schema_context = analysis.to_context_markdown()
    orchestrator = orchestrator or AgentOrchestrator()
    decision = orchestrator.plan_next(
        work_id=work_id,
        work_description=question,
        status={"status": "pending"},
        prior_context=schema_context,
    )
    return DataAnalystAgentContext(
        question=question,
        schema_context=schema_context,
        orchestration_decision=decision,
    )


def run_data_analyst_agent(
    *,
    openai_client: OpenAIClient,
    provider: SnowflakeMetadataProvider,
    question: str,
    model: str = "gpt-4.1",
    table_names: Sequence[str] | None = None,
    orchestrator: AgentOrchestrator | None = None,
    work_id: str = "DATA-ANALYST-1",
) -> DataAnalystAgentResult:
    """Run a Snowflake-grounded data analyst agent with the OpenAI Responses API."""

    context = build_data_analyst_context(
        provider,
        question,
        table_names=table_names,
        orchestrator=orchestrator,
        work_id=work_id,
    )
    response = openai_client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": DATA_ANALYST_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": context.to_markdown(),
            },
        ],
    )
    return DataAnalystAgentResult(
        question=question,
        model=model,
        response_text=_extract_response_text(response),
        context=context,
    )


def build_data_analyst_eval_items(
    provider: SnowflakeMetadataProvider,
    questions: Sequence[str],
    *,
    table_names: Sequence[str] | None = None,
    expected_outputs: Sequence[str | None] | None = None,
    orchestrator: AgentOrchestrator | None = None,
) -> tuple[DataAnalystEvalItem, ...]:
    """Build OpenAI eval items grounded in current Snowflake metadata context."""

    expected_outputs = expected_outputs or ()
    items: list[DataAnalystEvalItem] = []
    for index, question in enumerate(questions, start=1):
        context = build_data_analyst_context(
            provider,
            question,
            table_names=table_names,
            orchestrator=orchestrator,
            work_id=f"DATA-ANALYST-EVAL-{index}",
        )
        expected_output = expected_outputs[index - 1] if index <= len(expected_outputs) else None
        items.append(
            DataAnalystEvalItem(
                question=question,
                context_markdown=context.to_markdown(),
                expected_output=expected_output,
            )
        )
    return tuple(items)


def create_data_analyst_eval_run(
    *,
    openai_client: OpenAIClient,
    provider: SnowflakeMetadataProvider,
    eval_id: str,
    questions: Sequence[str],
    run_name: str = "snowflake-data-analyst-agent",
    model: str = "gpt-4.1",
    table_names: Sequence[str] | None = None,
    expected_outputs: Sequence[str | None] | None = None,
    orchestrator: AgentOrchestrator | None = None,
) -> DataAnalystEvalRunResult:
    """Create an OpenAI eval run for the Snowflake-grounded data analyst agent."""

    eval_items = build_data_analyst_eval_items(
        provider,
        questions,
        table_names=table_names,
        expected_outputs=expected_outputs,
        orchestrator=orchestrator,
    )
    data_source = build_data_analyst_eval_data_source(eval_items, model=model)
    eval_run = openai_client.evals.runs.create(
        eval_id,
        name=run_name,
        data_source=data_source,
    )
    return DataAnalystEvalRunResult(
        eval_id=eval_id,
        run_name=run_name,
        eval_items=eval_items,
        data_source=data_source,
        eval_run=eval_run,
    )


def build_data_analyst_eval_data_source(
    eval_items: Sequence[DataAnalystEvalItem],
    *,
    model: str,
) -> dict[str, object]:
    """Build a completions data source for OpenAI eval runs."""

    return {
        "type": "completions",
        "model": model,
        "input_messages": {
            "type": "template",
            "template": [
                {
                    "role": "system",
                    "content": DATA_ANALYST_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        "{{item.context}}\n\n"
                        "Answer this analyst question using only the provided Snowflake context:\n"
                        "{{item.question}}"
                    ),
                },
            ],
        },
        "source": {
            "type": "file_content",
            "content": [item.to_eval_item() for item in eval_items],
        },
    }


def build_data_analyst_multi_agent_plan(
    provider: SnowflakeMetadataProvider,
    question: str,
    *,
    table_names: Sequence[str] | None = None,
    work_items: Sequence[WorkItem] | None = None,
    orchestrator: AgentOrchestrator | None = None,
) -> MultiAgentPlan:
    """Build a multi-agent analyst plan grounded in current Snowflake metadata."""

    analysis = provider.analyze_schema_descriptions(list(table_names) if table_names else None)
    schema_context = analysis.to_context_markdown()
    orchestrator = orchestrator or AgentOrchestrator()
    return orchestrator.plan_multi_agent_work(
        objective=question,
        work_items=tuple(work_items or _default_data_analyst_work_items()),
        status={"status": "pending"},
        prior_context=schema_context,
    )


DATA_ANALYST_SYSTEM_PROMPT = (
    "You are a data analyst agent for a small or mid-sized business. "
    "Use the provided Snowflake metadata, description quality scores, and orchestration context. "
    "Do not invent tables or columns. When SQL is useful, produce reviewable Snowflake SQL. "
    "Call out metadata gaps, data quality risks, stakeholder questions, and recommended next work."
)


def _default_data_analyst_work_items() -> tuple[WorkItem, ...]:
    return (
        WorkItem(
            work_id="ANALYST-META-1",
            description="Analyze Snowflake metadata descriptions for the analyst question",
            checked=False,
        ),
        WorkItem(
            work_id="ANALYST-QUALITY-1",
            description="Review data quality risks and validation concerns for the analyst question",
            checked=False,
        ),
        WorkItem(
            work_id="ANALYST-SQL-1",
            description="Create transformation SQL or query plan for the analyst question",
            checked=False,
        ),
    )


def _extract_response_text(response: object) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()
    return str(response).strip()
