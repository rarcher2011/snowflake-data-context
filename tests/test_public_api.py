import openai_snowflake_agent_context as package
from openai_snowflake_agent_context import (
    DescriptionUpdateRequest,
    SampledTableResult,
    SchemaDescriptionAnalysis,
    SnowflakeContextConfig,
    SnowflakeDescriptionUpdatePlan,
    SnowflakeDescriptionUpdateResult,
    SnowflakeMetadataProvider,
    analyze_table_metadata_descriptions,
    build_sample_table_sql,
    build_openapi_schema,
    create_app,
    sample_table,
)


def test_public_api_exports_core_types() -> None:
    assert package.DescriptionUpdateRequest is DescriptionUpdateRequest
    assert package.SnowflakeContextConfig is SnowflakeContextConfig
    assert package.SnowflakeDescriptionUpdatePlan is SnowflakeDescriptionUpdatePlan
    assert package.SnowflakeDescriptionUpdateResult is SnowflakeDescriptionUpdateResult
    assert package.SnowflakeMetadataProvider is SnowflakeMetadataProvider
    assert package.SampledTableResult is SampledTableResult
    assert package.SchemaDescriptionAnalysis is SchemaDescriptionAnalysis
    assert package.analyze_table_metadata_descriptions is analyze_table_metadata_descriptions
    assert package.build_sample_table_sql is build_sample_table_sql
    assert package.build_openapi_schema is build_openapi_schema
    assert package.create_app is create_app
    assert package.sample_table is sample_table
    assert sorted(package.__all__) == [
        "DescriptionUpdateRequest",
        "SampledTableResult",
        "SchemaDescriptionAnalysis",
        "SnowflakeContextConfig",
        "SnowflakeDescriptionUpdatePlan",
        "SnowflakeDescriptionUpdateResult",
        "SnowflakeMetadataProvider",
        "analyze_table_metadata_descriptions",
        "build_openapi_schema",
        "build_sample_table_sql",
        "create_app",
        "sample_table",
    ]
