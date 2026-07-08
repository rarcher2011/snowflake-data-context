import openai_snowflake_agent_context as package
from openai_snowflake_agent_context import SnowflakeContextConfig, SnowflakeMetadataProvider


def test_public_api_exports_core_types() -> None:
    assert package.SnowflakeContextConfig is SnowflakeContextConfig
    assert package.SnowflakeMetadataProvider is SnowflakeMetadataProvider
    assert sorted(package.__all__) == [
        "SnowflakeContextConfig",
        "SnowflakeMetadataProvider",
    ]

