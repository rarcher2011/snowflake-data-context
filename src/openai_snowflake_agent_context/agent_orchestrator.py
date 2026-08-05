"""Lightweight orchestration layer for long-running analytics agents."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Sequence

from .agent_harness import HarnessReport, WorkItem


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
        words = set(re.findall(r"[a-z0-9_]+", normalized))
        for keyword in self.keywords:
            normalized_keyword = keyword.lower()
            if " " in normalized_keyword:
                if normalized_keyword in normalized:
                    return True
            elif normalized_keyword in words:
                return True
        return False


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


@dataclass(frozen=True)
class AgentAssignment:
    """One specialist agent assignment in a coordinated multi-agent plan."""

    assignment_id: str
    agent: AgentRole
    work_id: str | None
    description: str
    status: str
    context: str
    depends_on: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly assignment payload."""

        return {
            "assignment_id": self.assignment_id,
            "agent": {
                "role_id": self.agent.role_id,
                "title": self.agent.title,
                "purpose": self.agent.purpose,
            },
            "work_id": self.work_id,
            "description": self.description,
            "status": self.status,
            "context": self.context,
            "depends_on": list(self.depends_on),
        }


@dataclass(frozen=True)
class MultiAgentPlan:
    """Coordinated plan for work that can span multiple specialist agents."""

    objective: str
    coordination_agent: AgentRole
    assignments: tuple[AgentAssignment, ...]
    status: str
    shared_context: str
    warnings: tuple[str, ...] = ()

    @property
    def should_continue(self) -> bool:
        """Return whether at least one assignment is ready to run."""

        return bool(self.ready_assignments())

    def ready_assignments(
        self,
        completed_assignment_ids: Sequence[str] | None = None,
    ) -> tuple[AgentAssignment, ...]:
        """Return assignments whose dependencies are complete."""

        completed = set(completed_assignment_ids or ())
        return tuple(
            assignment
            for assignment in self.assignments
            if assignment.assignment_id not in completed
            and assignment.status not in {"blocked", "completed"}
            and all(dependency in completed for dependency in assignment.depends_on)
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly plan payload for harness status or APIs."""

        return {
            "objective": self.objective,
            "coordination_agent": {
                "role_id": self.coordination_agent.role_id,
                "title": self.coordination_agent.title,
                "purpose": self.coordination_agent.purpose,
            },
            "status": self.status,
            "shared_context": self.shared_context,
            "warnings": list(self.warnings),
            "should_continue": self.should_continue,
            "assignments": [assignment.to_dict() for assignment in self.assignments],
        }

    def to_markdown(self) -> str:
        """Render the multi-agent plan as human-readable handoff context."""

        lines = [
            "# Multi-Agent Orchestration Plan",
            "",
            f"- Objective: {self.objective}",
            f"- Coordination agent: {self.coordination_agent.title} ({self.coordination_agent.role_id})",
            f"- Status: {self.status}",
            f"- Continue: {'yes' if self.should_continue else 'no'}",
            "",
            "## Assignments",
        ]
        if not self.assignments:
            lines.append("- No assignments.")
        for assignment in self.assignments:
            dependencies = ", ".join(assignment.depends_on) if assignment.depends_on else "none"
            lines.extend(
                [
                    f"- {assignment.assignment_id}: {assignment.agent.title}",
                    f"  - Work ID: {assignment.work_id or 'none'}",
                    f"  - Status: {assignment.status}",
                    f"  - Depends on: {dependencies}",
                    f"  - Description: {assignment.description}",
                ]
            )
        if self.warnings:
            lines.extend(["", "## Warnings"])
            lines.extend(f"- {warning}" for warning in self.warnings)
        lines.extend(["", "## Shared Context", self.shared_context or "No shared context."])
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

    def plan_multi_agent_from_harness_report(
        self,
        report: HarnessReport,
        *,
        objective: str | None = None,
    ) -> MultiAgentPlan:
        """Create a multi-agent plan from harness startup state."""

        work_items = (report.next_work,) if report.next_work else ()
        return self.plan_multi_agent_work(
            objective=objective or _objective_from_report(report),
            work_items=work_items,
            status=report.status,
            prior_context=_context_from_report(report),
            warnings=tuple(report.warnings),
        )

    def plan_multi_agent_work(
        self,
        *,
        objective: str,
        work_items: Sequence[WorkItem],
        status: dict[str, Any] | None = None,
        prior_context: str | None = None,
        warnings: Sequence[str] = (),
    ) -> MultiAgentPlan:
        """Build coordinated assignments for multiple specialist agents."""

        status = status or {}
        status_value = "needs_coordination" if warnings else str(status.get("status", "pending"))
        if warnings:
            return MultiAgentPlan(
                objective=objective,
                coordination_agent=self._fallback_role,
                assignments=(),
                status=status_value,
                shared_context=prior_context or "",
                warnings=tuple(warnings),
            )

        assignments: list[AgentAssignment] = []
        metadata_assignment_ids: list[str] = []
        for index, work_item in enumerate(work_items, start=1):
            selected_role = self._select_role(work_item.description)
            assignment_id = f"A{index}"
            depends_on = _dependencies_for_role(selected_role, metadata_assignment_ids)
            assignment = AgentAssignment(
                assignment_id=assignment_id,
                agent=selected_role,
                work_id=work_item.work_id,
                description=work_item.description,
                status=str(status.get("status", "pending")),
                context=_join_context(
                    prior_context,
                    f"Assigned work: {work_item.work_id}: {work_item.description}",
                ),
                depends_on=depends_on,
            )
            assignments.append(assignment)
            if selected_role.role_id == "metadata_analyst":
                metadata_assignment_ids.append(assignment_id)

        return MultiAgentPlan(
            objective=objective,
            coordination_agent=self._fallback_role,
            assignments=tuple(assignments),
            status=status_value,
            shared_context=prior_context or "",
            warnings=tuple(warnings),
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


def _dependencies_for_role(
    role: AgentRole,
    metadata_assignment_ids: Sequence[str],
) -> tuple[str, ...]:
    if role.role_id in {"data_engineer", "quality_reviewer"}:
        return tuple(metadata_assignment_ids)
    return ()


def _objective_from_report(report: HarnessReport) -> str:
    if report.next_work is not None:
        return report.next_work.description
    summary = report.memory.summary
    if summary:
        return summary
    return "Coordinate long-running analytics work"
