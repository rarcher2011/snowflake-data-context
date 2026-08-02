"""Provider interface for Snowflake metadata used by coding agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from .config import SnowflakeContextConfig

if TYPE_CHECKING:
    from .description_updates import (
        DescriptionUpdateRequest,
        SnowflakeDescriptionUpdateResult,
    )
    from .description_suggestions import ColumnDescriptionSuggestionResult, OpenAIClient
    from .metadata_analysis import SchemaDescriptionAnalysis
    from .sampling import SampledTableResult


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


class SnowflakeCursor(Protocol):
    """Minimal cursor protocol expected from Snowflake connector objects."""

    def execute(self, sql: str) -> object:
        """Execute one SQL statement."""

    def fetchall(self) -> list[object]:
        """Return all rows from the last executed statement."""


class SnowflakeConnection(Protocol):
    """Minimal connection protocol expected from Snowflake connector objects."""

    def cursor(self) -> SnowflakeCursor:
        """Return a cursor-like object."""


class SnowflakeMetadataProvider:
    """Fetches and formats Snowflake metadata for OpenAI coding-agent context."""

    def __init__(self, connection: SnowflakeConnection, config: SnowflakeContextConfig) -> None:
        self._connection = connection
        self._config = config

    def describe_tables(self, table_names: list[str] | None = None) -> list[TableContext]:
        """Return table descriptions and metadata formatted for agent use.

        Queries Snowflake `INFORMATION_SCHEMA.TABLES` and
        `INFORMATION_SCHEMA.COLUMNS`, then normalizes the result into compact
        `TableContext` objects for downstream analysis and agent context.
        """

        requested_tables = _normalize_requested_tables(table_names, self._config)
        cursor = self._connection.cursor()
        table_rows = _fetch_rows(cursor, _build_tables_query(self._config))
        column_rows = _fetch_rows(cursor, _build_columns_query(self._config))

        tables = [
            _table_row_to_context(
                row,
                _columns_for_table(row, column_rows),
            )
            for row in table_rows
        ]
        if requested_tables:
            tables = [
                table
                for table in tables
                if _table_matches_requested(table, requested_tables)
            ]
        return tables[: self._config.max_tables]

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

    def update_descriptions(
        self,
        updates: list[DescriptionUpdateRequest],
        apply: bool = False,
    ) -> SnowflakeDescriptionUpdateResult:
        """Plan and optionally apply Snowflake table/column description updates.

        The default `apply=False` returns validated COMMENT statements for review.
        Set `apply=True` only when the caller explicitly wants to execute the
        generated statements against the configured Snowflake connection.
        """
        from .description_updates import (
            SnowflakeDescriptionUpdateResult,
            apply_description_update_plan,
            build_description_update_plan,
        )

        plan = build_description_update_plan(
            updates,
            default_database=self._config.database,
            default_schema=self._config.schema,
        )
        if apply:
            apply_description_update_plan(self._connection, plan)
        return SnowflakeDescriptionUpdateResult(plan=plan, applied=apply)

    def sample_table(
        self,
        table_name: str,
        destination_location: str,
        *,
        sample_percent: float = 1.0,
    ) -> SampledTableResult:
        """Create a random sample table and return the sampled-table metadata."""

        from .sampling import sample_table

        return sample_table(
            self._connection,
            table_name,
            destination_location,
            sample_percent=sample_percent,
        )

    def suggest_column_descriptions(
        self,
        table_name: str,
        openai_client: OpenAIClient,
        *,
        model: str = "gpt-4.1-mini",
        sample_size: int = 5,
    ) -> ColumnDescriptionSuggestionResult:
        """Sample a table and ask OpenAI for suggested column descriptions."""

        from .description_suggestions import suggest_column_descriptions_from_samples

        tables = self.describe_tables([table_name])
        if not tables:
            raise ValueError(f"No Snowflake table metadata found for {table_name}.")
        return suggest_column_descriptions_from_samples(
            connection=self._connection,
            table=tables[0],
            openai_client=openai_client,
            model=model,
            sample_size=sample_size,
        )


def _fetch_rows(cursor: SnowflakeCursor, sql: str) -> list[object]:
    cursor.execute(sql)
    return cursor.fetchall()


def _build_tables_query(config: SnowflakeContextConfig) -> str:
    source = _information_schema_source(config, "TABLES")
    predicates = ["TABLE_TYPE IN ('BASE TABLE', 'VIEW')"]
    if config.schema:
        predicates.append(f"UPPER(TABLE_SCHEMA) = UPPER({_quote_sql_string(config.schema)})")
    return (
        "SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE, COMMENT\n"
        f"FROM {source}\n"
        f"WHERE {' AND '.join(predicates)}\n"
        "ORDER BY TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME"
    )


def _build_columns_query(config: SnowflakeContextConfig) -> str:
    source = _information_schema_source(config, "COLUMNS")
    predicates: list[str] = []
    if config.schema:
        predicates.append(f"UPPER(TABLE_SCHEMA) = UPPER({_quote_sql_string(config.schema)})")
    where_clause = f"\nWHERE {' AND '.join(predicates)}" if predicates else ""
    return (
        "SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, COMMENT, "
        "ORDINAL_POSITION\n"
        f"FROM {source}"
        f"{where_clause}\n"
        "ORDER BY TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION"
    )


def _information_schema_source(config: SnowflakeContextConfig, view_name: str) -> str:
    if config.database:
        return f"{config.database}.INFORMATION_SCHEMA.{view_name}"
    return f"INFORMATION_SCHEMA.{view_name}"


def _table_row_to_context(row: object, column_rows: list[object]) -> TableContext:
    database = str(_row_value(row, "TABLE_CATALOG", 0))
    schema = str(_row_value(row, "TABLE_SCHEMA", 1))
    name = str(_row_value(row, "TABLE_NAME", 2))
    kind = str(_row_value(row, "TABLE_TYPE", 3))
    description = _optional_string(_row_value(row, "COMMENT", 4))
    columns = tuple(_format_column(column_row) for column_row in column_rows)
    return TableContext(
        database=database,
        schema=schema,
        name=name,
        kind=kind,
        description=description,
        columns=columns,
        context_markdown=_format_context_markdown(
            database=database,
            schema=schema,
            name=name,
            kind=kind,
            description=description,
            columns=columns,
        ),
    )


def _columns_for_table(table_row: object, column_rows: list[object]) -> list[object]:
    table_key = (
        _normalize_identifier(str(_row_value(table_row, "TABLE_CATALOG", 0))),
        _normalize_identifier(str(_row_value(table_row, "TABLE_SCHEMA", 1))),
        _normalize_identifier(str(_row_value(table_row, "TABLE_NAME", 2))),
    )
    return [
        column_row
        for column_row in column_rows
        if (
            _normalize_identifier(str(_row_value(column_row, "TABLE_CATALOG", 0))),
            _normalize_identifier(str(_row_value(column_row, "TABLE_SCHEMA", 1))),
            _normalize_identifier(str(_row_value(column_row, "TABLE_NAME", 2))),
        )
        == table_key
    ]


def _format_column(row: object) -> str:
    name = str(_row_value(row, "COLUMN_NAME", 3))
    data_type = str(_row_value(row, "DATA_TYPE", 4))
    comment = _optional_string(_row_value(row, "COMMENT", 5))
    if comment:
        return f"{name} {data_type} -- {comment}"
    return f"{name} {data_type}"


def _format_context_markdown(
    *,
    database: str,
    schema: str,
    name: str,
    kind: str,
    description: str | None,
    columns: tuple[str, ...],
) -> str:
    lines = [
        f"### {database}.{schema}.{name}",
        f"- Type: {kind}",
        f"- Description: {description or 'No description available.'}",
        "",
        "Columns:",
    ]
    lines.extend(f"- {column}" for column in columns)
    return "\n".join(lines)


def _normalize_requested_tables(
    table_names: list[str] | None,
    config: SnowflakeContextConfig,
) -> set[tuple[str | None, str | None, str]]:
    if not table_names:
        return set()
    requested: set[tuple[str | None, str | None, str]] = set()
    for table_name in table_names:
        parts = [part.strip().strip('"') for part in table_name.split(".") if part.strip()]
        if len(parts) == 1:
            requested.add(
                (
                    _normalize_optional_identifier(config.database),
                    _normalize_optional_identifier(config.schema),
                    _normalize_identifier(parts[0]),
                )
            )
        elif len(parts) == 2:
            requested.add(
                (
                    _normalize_optional_identifier(config.database),
                    _normalize_identifier(parts[0]),
                    _normalize_identifier(parts[1]),
                )
            )
        elif len(parts) == 3:
            requested.add(
                (
                    _normalize_identifier(parts[0]),
                    _normalize_identifier(parts[1]),
                    _normalize_identifier(parts[2]),
                )
            )
        else:
            raise ValueError(f"Expected table name, schema.table, or database.schema.table: {table_name}")
    return requested


def _table_matches_requested(
    table: TableContext,
    requested_tables: set[tuple[str | None, str | None, str]],
) -> bool:
    table_database = _normalize_identifier(table.database)
    table_schema = _normalize_identifier(table.schema)
    table_name = _normalize_identifier(table.name)
    for database, schema, name in requested_tables:
        if name != table_name:
            continue
        if database is not None and database != table_database:
            continue
        if schema is not None and schema != table_schema:
            continue
        return True
    return False


def _row_value(row: object, key: str, index: int) -> Any:
    if isinstance(row, dict):
        if key in row:
            return row[key]
        lowered = key.lower()
        if lowered in row:
            return row[lowered]
    if isinstance(row, (tuple, list)):
        return row[index]
    if hasattr(row, key):
        return getattr(row, key)
    return getattr(row, key.lower())


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _quote_sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _normalize_identifier(identifier: str) -> str:
    return identifier.strip().strip('"').upper()


def _normalize_optional_identifier(identifier: str | None) -> str | None:
    if identifier is None:
        return None
    return _normalize_identifier(identifier)
