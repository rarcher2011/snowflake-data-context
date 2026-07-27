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
    build_private_key_connection_kwargs,
    build_sample_table_sql,
    build_openapi_schema,
    connect_with_private_key,
    create_app,
    load_private_key_der,
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
    assert package.build_private_key_connection_kwargs is build_private_key_connection_kwargs
    assert package.build_sample_table_sql is build_sample_table_sql
    assert package.build_openapi_schema is build_openapi_schema
    assert package.connect_with_private_key is connect_with_private_key
    assert package.create_app is create_app
    assert package.load_private_key_der is load_private_key_der
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
        "build_private_key_connection_kwargs",
        "build_sample_table_sql",
        "connect_with_private_key",
        "create_app",
        "load_private_key_der",
        "sample_table",
    ]
