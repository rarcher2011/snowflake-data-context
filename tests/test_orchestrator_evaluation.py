from openai_snowflake_agent_context.agent_orchestrator import AgentOrchestrator, AgentRole
from openai_snowflake_agent_context.orchestrator_evaluation import (
    SAMPLE_DATA,
    SAMPLE_QUESTIONS,
    SAMPLE_SQL,
    run_orchestrator_evaluation,
)


def test_orchestrator_evaluation_passes_for_default_orchestrator() -> None:
    result = run_orchestrator_evaluation()

    assert result.passed is True
    assert result.score == 1.0
    assert result.to_dict() == {
        "total_cases": 5,
        "passed_cases": 5,
        "score": 1.0,
        "passed": True,
        "failures": [],
        "sample_questions": list(SAMPLE_QUESTIONS),
        "sample_data": list(SAMPLE_DATA),
        "sample_sql": list(SAMPLE_SQL),
    }
    markdown = result.to_markdown()
    assert "Score: 100.0%" in markdown
    assert "Which columns in the orders table need better descriptions" in markdown
    assert "PENDING_REVIEW" in markdown
    assert "ANALYTICS.PUBLIC.ORDERS_SAMPLE" in markdown


def test_orchestrator_evaluation_reports_failures_for_bad_routing() -> None:
    bad_default = AgentRole(
        role_id="catch_all",
        title="Catch All",
        purpose="Incorrectly captures every request.",
        keywords=("metadata", "quality", "transformation"),
    )
    result = run_orchestrator_evaluation(AgentOrchestrator(roles=(bad_default,)))

    assert result.passed is False
    assert result.score < 1.0
    assert any("expected metadata_analyst" in failure for failure in result.failures)
    assert "## Failures" in result.to_markdown()
