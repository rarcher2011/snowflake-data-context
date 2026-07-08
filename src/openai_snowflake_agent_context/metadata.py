"""Provider interface for Snowflake metadata used by coding agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .config import SnowflakeContextConfig


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

