"""Deterministic evaluations for the orchestrator layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .agent_harness import HarnessReport, MemoryRecord, WorkItem
from .agent_orchestrator import AgentOrchestrator, MultiAgentPlan, OrchestratorDecision


@dataclass(frozen=True)
class OrchestratorEvaluationCase:
    """One deterministic orchestration behavior check."""

    name: str
    assertion: Callable[[], tuple[bool, str]]


@dataclass(frozen=True)
class OrchestratorEvaluationResult:
    """Aggregate result for deterministic orchestrator evaluations."""

    total_cases: int
    passed_cases: int
    failures: tuple[str, ...]

    @property
    def score(self) -> float:
        """Return pass rate from 0.0 to 1.0."""

        if self.total_cases == 0:
            return 1.0
        return self.passed_cases / self.total_cases

    @property
    def passed(self) -> bool:
        """Return whether all evaluation cases passed."""

        return not self.failures

    def to_dict(self) -> dict[str, object]:
        """Return JSON-friendly evaluation output."""

        return {
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "score": self.score,
            "passed": self.passed,
            "failures": list(self.failures),
        }

    def to_markdown(self) -> str:
        """Render the evaluation result for human review."""

        lines = [
            "# Orchestrator Evaluation",
            "",
            f"- Total cases: {self.total_cases}",
            f"- Passed cases: {self.passed_cases}",
            f"- Score: {self.score:.1%}",
            f"- Passed: {'yes' if self.passed else 'no'}",
        ]
        if self.failures:
            lines.extend(["", "## Failures"])
            lines.extend(f"- {failure}" for failure in self.failures)
        return "\n".join(lines)


def run_orchestrator_evaluation(
    orchestrator: AgentOrchestrator | None = None,
) -> OrchestratorEvaluationResult:
    """Run deterministic evaluations that verify orchestrator behavior."""

    orchestrator = orchestrator or AgentOrchestrator()
    cases = _default_evaluation_cases(orchestrator)
    failures: list[str] = []
    passed_cases = 0
    for case in cases:
        passed, detail = case.assertion()
        if passed:
            passed_cases += 1
        else:
            failures.append(f"{case.name}: {detail}")
    return OrchestratorEvaluationResult(
        total_cases=len(cases),
        passed_cases=passed_cases,
        failures=tuple(failures),
    )


def _default_evaluation_cases(
    orchestrator: AgentOrchestrator,
) -> tuple[OrchestratorEvaluationCase, ...]:
    return (
        OrchestratorEvaluationCase(
            name="routes metadata work to metadata analyst",
            assertion=lambda: _expect_decision_role(
                orchestrator.plan_next(
                    work_id="EVAL-1",
                    work_description="Analyze metadata descriptions for analytics tables",
                    status={"status": "pending"},
                ),
                "metadata_analyst",
            ),
        ),
        OrchestratorEvaluationCase(
            name="routes review work to quality reviewer",
            assertion=lambda: _expect_decision_role(
                orchestrator.plan_next(
                    work_id="EVAL-2",
                    work_description="Review data quality issues in order totals",
                    status={"status": "pending"},
                ),
                "quality_reviewer",
            ),
        ),
        OrchestratorEvaluationCase(
            name="blocks specialist handoff when harness warnings exist",
            assertion=lambda: _expect_warning_plan(
                orchestrator.plan_multi_agent_from_harness_report(_warning_report()),
            ),
        ),
        OrchestratorEvaluationCase(
            name="creates dependency from transformation work to metadata work",
            assertion=lambda: _expect_multi_agent_dependencies(
                orchestrator.plan_multi_agent_work(
                    objective="Improve analytics schema readiness",
                    work_items=(
                        WorkItem(
                            work_id="EVAL-3",
                            description="Analyze Snowflake metadata descriptions",
                            checked=False,
                        ),
                        WorkItem(
                            work_id="EVAL-4",
                            description="Create transformation SQL for customer order marts",
                            checked=False,
                        ),
                    ),
                    status={"status": "pending"},
                ),
            ),
        ),
    )


def _expect_decision_role(
    decision: OrchestratorDecision,
    expected_role_id: str,
) -> tuple[bool, str]:
    actual = decision.next_agent.role_id
    return actual == expected_role_id, f"expected {expected_role_id}, got {actual}"


def _expect_warning_plan(plan: MultiAgentPlan) -> tuple[bool, str]:
    if plan.status != "needs_coordination":
        return False, f"expected needs_coordination status, got {plan.status}"
    if plan.assignments:
        return False, "expected warning plan to have no specialist assignments"
    if plan.should_continue:
        return False, "expected warning plan to stop specialist execution"
    return True, "warning plan is coordinated"


def _expect_multi_agent_dependencies(plan: MultiAgentPlan) -> tuple[bool, str]:
    role_ids = [assignment.agent.role_id for assignment in plan.assignments]
    if role_ids != ["metadata_analyst", "data_engineer"]:
        return False, f"unexpected assignment roles: {role_ids}"
    if plan.assignments[1].depends_on != ("A1",):
        return False, f"expected A2 to depend on A1, got {plan.assignments[1].depends_on}"
    ready_before = [assignment.assignment_id for assignment in plan.ready_assignments()]
    ready_after = [assignment.assignment_id for assignment in plan.ready_assignments(("A1",))]
    if ready_before != ["A1"]:
        return False, f"expected only A1 ready before metadata completion, got {ready_before}"
    if ready_after != ["A2"]:
        return False, f"expected A2 ready after A1 completion, got {ready_after}"
    return True, "multi-agent dependencies are correct"


def _warning_report() -> HarnessReport:
    return HarnessReport(
        repo_path="/repo",
        config_path="/repo/agent_harness.toml",
        memory=MemoryRecord(path=None, status=None, work_id=None, summary=None),
        status={"work_id": "EVAL-5", "status": "blocked"},
        next_work=WorkItem(
            work_id="EVAL-6",
            description="Analyze metadata quality",
            checked=False,
        ),
        incomplete_work=[],
        warnings=["Status and work queue disagree"],
        session_context_file="/repo/.agent_harness/session_context.md",
        generated_at="2026-08-05T12:00:00+00:00",
    )
