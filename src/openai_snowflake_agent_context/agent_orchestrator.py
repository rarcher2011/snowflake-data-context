"""Lightweight orchestration layer for long-running analytics agents."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

from .agent_harness import HarnessReport


@dataclass(frozen=True)
class AgentRole:
    """Specialist agent role that can own a class of analytics work."""

    role_id: str
    title: str
    purpose: str
    keywords: tuple[str, ...]

    def owns_work(self, work_description: str) -> bool:
        """Return whether this role should handle the described work."""

        normalized = work_description.lower()
        return any(keyword.lower() in normalized for keyword in self.keywords)


@dataclass(frozen=True)
class OrchestratorState:
    """Serializable status for the active orchestrated agent run."""

    objective: str
    active_agent: str | None = None
    active_work_id: str | None = None
    status: str = "pending"
    completed_work_ids: tuple[str, ...] = ()
    blocked_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly status payload for harness status files."""

        data = asdict(self)
        data["completed_work_ids"] = list(self.completed_work_ids)
        data["blocked_reasons"] = list(self.blocked_reasons)
        return data


@dataclass(frozen=True)
class OrchestratorDecision:
    """Next agent assignment selected by the orchestrator."""

    next_agent: AgentRole
    work_id: str | None
    status: str
    reason: str
    context: str
    should_continue: bool

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly decision payload for APIs or status files."""

        return {
            "next_agent": {
                "role_id": self.next_agent.role_id,
                "title": self.next_agent.title,
                "purpose": self.next_agent.purpose,
            },
            "work_id": self.work_id,
            "status": self.status,
            "reason": self.reason,
            "context": self.context,
            "should_continue": self.should_continue,
        }

    def to_markdown(self) -> str:
        """Render the decision as human-readable context for the next agent."""

        lines = [
            "# Agent Orchestrator Decision",
            "",
            f"- Next agent: {self.next_agent.title} ({self.next_agent.role_id})",
            f"- Work ID: {self.work_id or 'none'}",
            f"- Status: {self.status}",
            f"- Continue: {'yes' if self.should_continue else 'no'}",
            f"- Reason: {self.reason}",
            "",
            "## Context",
            self.context or "No additional context.",
        ]
        return "\n".join(lines)


class AgentOrchestrator:
    """Routes harness work to specialist agent roles."""

    def __init__(self, roles: Sequence[AgentRole] | None = None) -> None:
        default_roles = build_default_agent_roles()
        self._roles = tuple(roles or ()) + default_roles
        self._fallback_role = default_roles[-1]

    def plan_from_harness_report(self, report: HarnessReport) -> OrchestratorDecision:
        """Create the next orchestration decision from harness startup state."""

        if report.warnings:
            return OrchestratorDecision(
                next_agent=self._fallback_role,
                work_id=_status_work_id(report.status) or _next_work_id(report),
                status="needs_coordination",
                reason="Resolve harness warnings before delegating specialist work.",
                context=_context_from_report(report),
                should_continue=False,
            )

        if report.next_work is None:
            return OrchestratorDecision(
                next_agent=self._fallback_role,
                work_id=_status_work_id(report.status),
                status="idle",
                reason="No unchecked work item was found in the harness queue.",
                context=_context_from_report(report),
                should_continue=False,
            )

        return self.plan_next(
            work_id=report.next_work.work_id,
            work_description=report.next_work.description,
            status=report.status,
            prior_context=_context_from_report(report),
        )

    def plan_next(
        self,
        *,
        work_id: str | None,
        work_description: str,
        status: dict[str, Any] | None = None,
        prior_context: str | None = None,
    ) -> OrchestratorDecision:
        """Route one work item to the most appropriate specialist role."""

        status = status or {}
        selected_role = self._select_role(work_description)
        status_value = str(status.get("status", "pending"))
        return OrchestratorDecision(
            next_agent=selected_role,
            work_id=work_id,
            status=status_value,
            reason=f"{selected_role.title} best matches the current work description.",
            context=_join_context(
                prior_context,
                f"Current work: {work_description}",
            ),
            should_continue=status_value.lower() not in {"blocked", "complete", "completed"},
        )

    def _select_role(self, work_description: str) -> AgentRole:
        for role in self._roles:
            if role.owns_work(work_description):
                return role
        return self._fallback_role


def build_default_agent_roles() -> tuple[AgentRole, ...]:
    """Return default specialist roles for SMB analytics workflows."""

    return (
        AgentRole(
            role_id="metadata_analyst",
            title="Metadata Analyst",
            purpose="Assess Snowflake metadata, descriptions, table context, and data gaps.",
            keywords=(
                "metadata",
                "description",
                "schema",
                "table",
                "column",
                "discovery",
            ),
        ),
        AgentRole(
            role_id="data_engineer",
            title="Data Engineer",
            purpose="Plan reviewable SQL, transformations, sampling, and data model changes.",
            keywords=(
                "transformation",
                "transform",
                "sql",
                "model",
                "view",
                "sample",
                "pipeline",
            ),
        ),
        AgentRole(
            role_id="quality_reviewer",
            title="Quality Reviewer",
            purpose="Review data quality, freshness, validation, and readiness risks.",
            keywords=(
                "quality",
                "freshness",
                "validation",
                "issue",
                "risk",
                "monitor",
            ),
        ),
        AgentRole(
            role_id="stakeholder_liaison",
            title="Stakeholder Liaison",
            purpose="Identify business questions and human decisions needed to continue.",
            keywords=(
                "stakeholder",
                "question",
                "define",
                "owner",
                "business",
                "approval",
            ),
        ),
        AgentRole(
            role_id="orchestrator",
            title="Orchestrator",
            purpose="Resolve coordination, status, memory, and work-queue conflicts.",
            keywords=(
                "orchestrator",
                "coordinate",
                "status",
                "memory",
                "blocked",
                "handoff",
            ),
        ),
    )


def _context_from_report(report: HarnessReport) -> str:
    lines = [
        f"Repo: {report.repo_path}",
        f"Generated at: {report.generated_at}",
        f"Memory: {report.memory.path or 'none'}",
        f"Memory status: {report.memory.status or 'unknown'}",
        f"Memory work ID: {report.memory.work_id or 'unknown'}",
        f"Status: {report.status.get('status', 'unknown')}",
        f"Status work ID: {report.status.get('work_id', 'unknown')}",
    ]
    if report.next_work:
        lines.append(f"Next work: {report.next_work.work_id}: {report.next_work.description}")
    if report.incomplete_work:
        lines.append("Incomplete work:")
        lines.extend(f"- {item}" for item in report.incomplete_work)
    if report.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in report.warnings)
    return "\n".join(lines)


def _join_context(*parts: str | None) -> str:
    return "\n".join(part for part in parts if part)


def _status_work_id(status: dict[str, Any]) -> str | None:
    work_id = status.get("work_id")
    return str(work_id) if work_id is not None else None


def _next_work_id(report: HarnessReport) -> str | None:
    if report.next_work is None:
        return None
    return report.next_work.work_id
