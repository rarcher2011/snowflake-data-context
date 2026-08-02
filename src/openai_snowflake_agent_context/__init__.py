"""Snowflake metadata context helpers for OpenAI Python SDK workflows."""

__all__ = [
    "DescriptionUpdateRequest",
    "ColumnDescriptionSuggestion",
    "ColumnDescriptionSuggestionResult",
    "SchemaDescriptionAnalysis",
    "SnowflakeContextConfig",
    "SnowflakeDescriptionUpdatePlan",
    "SnowflakeDescriptionUpdateResult",
    "SnowflakeMetadataProvider",
    "SampledTableResult",
    "analyze_table_metadata_descriptions",
    "build_private_key_connection_kwargs",
    "build_sample_table_sql",
    "build_openapi_schema",
    "connect_with_private_key",
    "create_app",
    "load_private_key_der",
    "sample_table",
]

from .chatgpt_plugin import build_openapi_schema, create_app
from .config import SnowflakeContextConfig
from .connection import (
    build_private_key_connection_kwargs,
    connect_with_private_key,
    load_private_key_der,
)
from .description_updates import (
    DescriptionUpdateRequest,
    SnowflakeDescriptionUpdatePlan,
    SnowflakeDescriptionUpdateResult,
)
from .description_suggestions import (
    ColumnDescriptionSuggestion,
    ColumnDescriptionSuggestionResult,
)
from .metadata import SnowflakeMetadataProvider
from .metadata_analysis import SchemaDescriptionAnalysis, analyze_table_metadata_descriptions
from .sampling import SampledTableResult, build_sample_table_sql, sample_table
