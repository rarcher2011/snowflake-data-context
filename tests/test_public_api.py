import openai_snowflake_agent_context as package
from openai_snowflake_agent_context import (
    AgentAssignment,
    AgentOrchestrator,
    AgentRole,
    ColumnDescriptionSuggestion,
    ColumnDescriptionSuggestionResult,
    DataAnalystAgentContext,
    DataAnalystAgentResult,
    DescriptionUpdateRequest,
    MultiAgentPlan,
    OrchestratorDecision,
    OrchestratorEvaluationResult,
    OrchestratorState,
    SampledTableResult,
    SchemaDescriptionAnalysis,
    SnowflakeContextConfig,
    SnowflakeDescriptionUpdatePlan,
    SnowflakeDescriptionUpdateResult,
    SnowflakeMetadataProvider,
    analyze_table_metadata_descriptions,
    build_data_analyst_context,
    build_data_analyst_multi_agent_plan,
    build_default_agent_roles,
    build_private_key_connection_kwargs,
    build_sample_table_sql,
    build_openapi_schema,
    connect_with_private_key,
    create_app,
    load_private_key_der,
    run_data_analyst_agent,
    run_orchestrator_evaluation,
    sample_table,
)


def test_public_api_exports_core_types() -> None:
    assert package.AgentAssignment is AgentAssignment
    assert package.AgentOrchestrator is AgentOrchestrator
    assert package.AgentRole is AgentRole
    assert package.ColumnDescriptionSuggestion is ColumnDescriptionSuggestion
    assert package.ColumnDescriptionSuggestionResult is ColumnDescriptionSuggestionResult
    assert package.DataAnalystAgentContext is DataAnalystAgentContext
    assert package.DataAnalystAgentResult is DataAnalystAgentResult
    assert package.DescriptionUpdateRequest is DescriptionUpdateRequest
    assert package.MultiAgentPlan is MultiAgentPlan
    assert package.OrchestratorDecision is OrchestratorDecision
    assert package.OrchestratorEvaluationResult is OrchestratorEvaluationResult
    assert package.OrchestratorState is OrchestratorState
    assert package.SnowflakeContextConfig is SnowflakeContextConfig
    assert package.SnowflakeDescriptionUpdatePlan is SnowflakeDescriptionUpdatePlan
    assert package.SnowflakeDescriptionUpdateResult is SnowflakeDescriptionUpdateResult
    assert package.SnowflakeMetadataProvider is SnowflakeMetadataProvider
    assert package.SampledTableResult is SampledTableResult
    assert package.SchemaDescriptionAnalysis is SchemaDescriptionAnalysis
    assert package.analyze_table_metadata_descriptions is analyze_table_metadata_descriptions
    assert package.build_data_analyst_context is build_data_analyst_context
    assert package.build_data_analyst_multi_agent_plan is build_data_analyst_multi_agent_plan
    assert package.build_default_agent_roles is build_default_agent_roles
    assert package.build_private_key_connection_kwargs is build_private_key_connection_kwargs
    assert package.build_sample_table_sql is build_sample_table_sql
    assert package.build_openapi_schema is build_openapi_schema
    assert package.connect_with_private_key is connect_with_private_key
    assert package.create_app is create_app
    assert package.load_private_key_der is load_private_key_der
    assert package.run_data_analyst_agent is run_data_analyst_agent
    assert package.run_orchestrator_evaluation is run_orchestrator_evaluation
    assert package.sample_table is sample_table
    assert sorted(package.__all__) == [
        "AgentAssignment",
        "AgentOrchestrator",
        "AgentRole",
        "ColumnDescriptionSuggestion",
        "ColumnDescriptionSuggestionResult",
        "DataAnalystAgentContext",
        "DataAnalystAgentResult",
        "DescriptionUpdateRequest",
        "MultiAgentPlan",
        "OrchestratorDecision",
        "OrchestratorEvaluationResult",
        "OrchestratorState",
        "SampledTableResult",
        "SchemaDescriptionAnalysis",
        "SnowflakeContextConfig",
        "SnowflakeDescriptionUpdatePlan",
        "SnowflakeDescriptionUpdateResult",
        "SnowflakeMetadataProvider",
        "analyze_table_metadata_descriptions",
        "build_data_analyst_context",
        "build_data_analyst_multi_agent_plan",
        "build_default_agent_roles",
        "build_openapi_schema",
        "build_private_key_connection_kwargs",
        "build_sample_table_sql",
        "connect_with_private_key",
        "create_app",
        "load_private_key_der",
        "run_data_analyst_agent",
        "run_orchestrator_evaluation",
        "sample_table",
    ]
