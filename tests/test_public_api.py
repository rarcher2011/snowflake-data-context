import openai_snowflake_agent_context as package
from openai_snowflake_agent_context import (
    DescriptionUpdateRequest,
    SchemaDescriptionAnalysis,
    SnowflakeContextConfig,
    SnowflakeDescriptionUpdatePlan,
    SnowflakeDescriptionUpdateResult,
    SnowflakeMetadataProvider,
    analyze_table_metadata_descriptions,
    build_openapi_schema,
    create_app,
)


def test_public_api_exports_core_types() -> None:
    assert package.DescriptionUpdateRequest is DescriptionUpdateRequest
    assert package.SnowflakeContextConfig is SnowflakeContextConfig
    assert package.SnowflakeDescriptionUpdatePlan is SnowflakeDescriptionUpdatePlan
    assert package.SnowflakeDescriptionUpdateResult is SnowflakeDescriptionUpdateResult
    assert package.SnowflakeMetadataProvider is SnowflakeMetadataProvider
    assert package.SchemaDescriptionAnalysis is SchemaDescriptionAnalysis
    assert package.analyze_table_metadata_descriptions is analyze_table_metadata_descriptions
    assert package.build_openapi_schema is build_openapi_schema
    assert package.create_app is create_app
    assert sorted(package.__all__) == [
        "DescriptionUpdateRequest",
        "SchemaDescriptionAnalysis",
        "SnowflakeContextConfig",
        "SnowflakeDescriptionUpdatePlan",
        "SnowflakeDescriptionUpdateResult",
        "SnowflakeMetadataProvider",
        "analyze_table_metadata_descriptions",
        "build_openapi_schema",
        "create_app",
    ]
