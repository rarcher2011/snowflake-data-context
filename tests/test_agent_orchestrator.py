from openai_snowflake_agent_context.agent_harness import (
    HarnessReport,
    MemoryRecord,
    WorkItem,
)
from openai_snowflake_agent_context.agent_orchestrator import (
    AgentOrchestrator,
    AgentRole,
    MultiAgentPlan,
    OrchestratorState,
    build_default_agent_roles,
)


def test_default_agent_roles_cover_core_smb_analytics_work() -> None:
    roles = build_default_agent_roles()

    assert [role.role_id for role in roles] == [
        "metadata_analyst",
        "data_engineer",
        "quality_reviewer",
        "stakeholder_liaison",
        "orchestrator",
    ]
    assert roles[0].owns_work("Analyze Snowflake metadata descriptions")
    assert roles[1].owns_work("Create transformation SQL for customer orders")
    assert roles[2].owns_work("Review data quality issues in order totals")
    assert roles[3].owns_work("Ask stakeholder to define active customer")


def test_orchestrator_routes_next_work_from_harness_report() -> None:
    report = HarnessReport(
        repo_path="/repo",
        config_path="/repo/agent_harness.toml",
        memory=MemoryRecord(
            path="/repo/.agent_harness/memory/latest.md",
            status="in_progress",
            work_id="WORK-20",
            summary="Metadata scoring started",
        ),
        status={"work_id": "WORK-20", "status": "in_progress"},
        next_work=WorkItem(
            work_id="WORK-20",
            description="Analyze metadata quality for the analytics schema",
            checked=False,
        ),
        incomplete_work=["Latest memory reports in_progress for WORK-20"],
        warnings=[],
        session_context_file="/repo/.agent_harness/session_context.md",
        generated_at="2026-08-03T12:00:00+00:00",
    )

    decision = AgentOrchestrator().plan_from_harness_report(report)

    assert decision.next_agent.role_id == "metadata_analyst"
    assert decision.work_id == "WORK-20"
    assert decision.status == "in_progress"
    assert decision.should_continue is True
    assert "Latest memory reports in_progress for WORK-20" in decision.context


def test_orchestrator_routes_warnings_to_orchestrator_role() -> None:
    report = HarnessReport(
        repo_path="/repo",
        config_path="/repo/agent_harness.toml",
        memory=MemoryRecord(path=None, status=None, work_id=None, summary=None),
        status={"work_id": "WORK-21", "status": "blocked"},
        next_work=WorkItem(
            work_id="WORK-22",
            description="Build transformation candidates",
            checked=False,
        ),
        incomplete_work=[],
        warnings=["Next work item WORK-22 differs from status file work_id WORK-21"],
        session_context_file="/repo/.agent_harness/session_context.md",
        generated_at="2026-08-03T12:00:00+00:00",
    )

    decision = AgentOrchestrator().plan_from_harness_report(report)

    assert decision.next_agent.role_id == "orchestrator"
    assert decision.status == "needs_coordination"
    assert decision.should_continue is False
    assert "Resolve harness warnings before delegating specialist work." in decision.reason


def test_orchestrator_state_serializes_for_status_files_and_actions() -> None:
    state = OrchestratorState(
        objective="Improve metadata quality",
        active_agent="metadata_analyst",
        active_work_id="WORK-30",
        status="in_progress",
        completed_work_ids=("WORK-29",),
        blocked_reasons=("Waiting for Snowflake role",),
    )

    payload = state.to_dict()

    assert payload == {
        "objective": "Improve metadata quality",
        "active_agent": "metadata_analyst",
        "active_work_id": "WORK-30",
        "status": "in_progress",
        "completed_work_ids": ["WORK-29"],
        "blocked_reasons": ["Waiting for Snowflake role"],
    }


def test_custom_role_can_be_registered_ahead_of_defaults() -> None:
    owner = AgentRole(
        role_id="governance_reviewer",
        title="Governance Reviewer",
        purpose="Review access and sensitive data concerns.",
        keywords=("pii", "sensitive", "governance"),
    )
    orchestrator = AgentOrchestrator(roles=(owner,))

    decision = orchestrator.plan_next(
        work_id="WORK-40",
        work_description="Review PII handling for customer email",
        status={"status": "pending"},
    )

    assert decision.next_agent.role_id == "governance_reviewer"
    assert "Review PII handling" in decision.context


def test_orchestrator_builds_multi_agent_plan_with_dependencies() -> None:
    orchestrator = AgentOrchestrator()

    plan = orchestrator.plan_multi_agent_work(
        objective="Improve analytics schema readiness",
        work_items=(
            WorkItem(
                work_id="WORK-50",
                description="Analyze Snowflake metadata descriptions",
                checked=False,
            ),
            WorkItem(
                work_id="WORK-51",
                description="Create transformation SQL for customer order marts",
                checked=False,
            ),
            WorkItem(
                work_id="WORK-52",
                description="Ask stakeholder to define active customer",
                checked=False,
            ),
        ),
        status={"status": "pending"},
        prior_context="Harness context loaded.",
    )

    assert isinstance(plan, MultiAgentPlan)
    assert plan.objective == "Improve analytics schema readiness"
    assert [assignment.agent.role_id for assignment in plan.assignments] == [
        "metadata_analyst",
        "data_engineer",
        "stakeholder_liaison",
    ]
    assert plan.assignments[1].depends_on == ("A1",)
    assert plan.assignments[2].depends_on == ()
    assert [assignment.assignment_id for assignment in plan.ready_assignments()] == ["A1", "A3"]
    assert [assignment.assignment_id for assignment in plan.ready_assignments(("A1",))] == ["A2", "A3"]


def test_multi_agent_plan_serializes_for_harness_status() -> None:
    plan = AgentOrchestrator().plan_multi_agent_work(
        objective="Coordinate schema discovery",
        work_items=(
            WorkItem(
                work_id="WORK-60",
                description="Review data quality issues in order totals",
                checked=False,
            ),
        ),
        status={"status": "in_progress"},
        prior_context="Use sampled table ANALYTICS.PUBLIC.ORDERS_SAMPLE.",
    )

    payload = plan.to_dict()
    markdown = plan.to_markdown()

    assert payload["objective"] == "Coordinate schema discovery"
    assert payload["coordination_agent"] == {
        "role_id": "orchestrator",
        "title": "Orchestrator",
        "purpose": "Resolve coordination, status, memory, and work-queue conflicts.",
    }
    assert payload["assignments"] == [
        {
            "assignment_id": "A1",
            "agent": {
                "role_id": "quality_reviewer",
                "title": "Quality Reviewer",
                "purpose": "Review data quality, freshness, validation, and readiness risks.",
            },
            "work_id": "WORK-60",
            "description": "Review data quality issues in order totals",
            "status": "in_progress",
            "context": (
                "Use sampled table ANALYTICS.PUBLIC.ORDERS_SAMPLE.\n"
                "Assigned work: WORK-60: Review data quality issues in order totals"
            ),
            "depends_on": [],
        }
    ]
    assert "# Multi-Agent Orchestration Plan" in markdown
    assert "Quality Reviewer" in markdown


def test_multi_agent_plan_from_harness_report_blocks_on_warnings() -> None:
    report = HarnessReport(
        repo_path="/repo",
        config_path="/repo/agent_harness.toml",
        memory=MemoryRecord(path=None, status=None, work_id=None, summary=None),
        status={"work_id": "WORK-70", "status": "blocked"},
        next_work=WorkItem(
            work_id="WORK-71",
            description="Analyze metadata quality",
            checked=False,
        ),
        incomplete_work=[],
        warnings=["Status and work queue disagree"],
        session_context_file="/repo/.agent_harness/session_context.md",
        generated_at="2026-08-04T12:00:00+00:00",
    )

    plan = AgentOrchestrator().plan_multi_agent_from_harness_report(report)

    assert plan.status == "needs_coordination"
    assert plan.assignments == ()
    assert plan.should_continue is False
    assert plan.warnings == ("Status and work queue disagree",)
