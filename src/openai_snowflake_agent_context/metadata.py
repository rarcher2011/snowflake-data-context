"""Provider interface for Snowflake metadata used by coding agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from .config import SnowflakeContextConfig

if TYPE_CHECKING:
    from .metadata_analysis import SchemaDescriptionAnalysis


@dataclass(frozen=True)
class TableContext:
    """Agent-ready metadata for a Snowflake table or view."""

    database: str
    schema: str
    name: str
    kind: str
    description: str | None
    columns: tuple[str, ...]
    context_markdown: str


class SnowflakeConnection(Protocol):
    """Minimal connection protocol expected from Snowflake connector objects."""

    def cursor(self) -> object:
        """Return a cursor-like object."""


class SnowflakeMetadataProvider:
    """Fetches and formats Snowflake metadata for OpenAI coding-agent context."""

    def __init__(self, connection: SnowflakeConnection, config: SnowflakeContextConfig) -> None:
        self._connection = connection
        self._config = config

    def describe_tables(self, table_names: list[str] | None = None) -> list[TableContext]:
        """Return table descriptions and metadata formatted for agent use.

        Implementation will query Snowflake information schema/account usage views,
        then normalize, redact, rank, and pack metadata into `TableContext` objects.
        """
        raise NotImplementedError("Snowflake metadata retrieval is not implemented yet.")

    def analyze_schema_descriptions(
        self,
        table_names: list[str] | None = None,
    ) -> SchemaDescriptionAnalysis:
        """Analyze table and column description quality for the configured schema.

        Passing `table_names=None` asks the provider to analyze all tables returned by
        `describe_tables`, which is the intended all-tables-in-schema workflow once
        live Snowflake metadata retrieval is implemented.
        """
        from .metadata_analysis import analyze_table_metadata_descriptions

        return analyze_table_metadata_descriptions(self.describe_tables(table_names))
