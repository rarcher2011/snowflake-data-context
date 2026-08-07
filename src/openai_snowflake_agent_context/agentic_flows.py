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


class OpenAIClient(Protocol):
    """Minimal OpenAI client protocol expected by the analyst flows."""

    responses: OpenAIResponsesResource


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
        work_items=tuple(work_items or _default_data_analyst_work_items(question)),
        status={"status": "pending"},
        prior_context=schema_context,
    )


DATA_ANALYST_SYSTEM_PROMPT = (
    "You are a data analyst agent for a small or mid-sized business. "
    "Use the provided Snowflake metadata, description quality scores, and orchestration context. "
    "Do not invent tables or columns. When SQL is useful, produce reviewable Snowflake SQL. "
    "Call out metadata gaps, data quality risks, stakeholder questions, and recommended next work."
)


def _default_data_analyst_work_items(question: str) -> tuple[WorkItem, ...]:
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
