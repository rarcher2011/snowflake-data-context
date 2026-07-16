import openai_snowflake_agent_context as package
from openai_snowflake_agent_context import (
    SchemaDescriptionAnalysis,
    SnowflakeContextConfig,
    SnowflakeMetadataProvider,
    analyze_table_metadata_descriptions,
)


def test_public_api_exports_core_types() -> None:
    assert package.SnowflakeContextConfig is SnowflakeContextConfig
    assert package.SnowflakeMetadataProvider is SnowflakeMetadataProvider
    assert package.SchemaDescriptionAnalysis is SchemaDescriptionAnalysis
    assert package.analyze_table_metadata_descriptions is analyze_table_metadata_descriptions
    assert sorted(package.__all__) == [
        "SchemaDescriptionAnalysis",
        "SnowflakeContextConfig",
        "SnowflakeMetadataProvider",
        "analyze_table_metadata_descriptions",
    ]
