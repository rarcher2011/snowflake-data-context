"""Plan and apply Snowflake table/column description updates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


@dataclass(frozen=True)
class DescriptionUpdateRequest:
    """User-provided descriptions for one Snowflake table."""

    table: str
    database: str | None = None
    schema: str | None = None
    table_description: str | None = None
    column_descriptions: dict[str, str] | None = None


@dataclass(frozen=True)
class SnowflakeDescriptionUpdateStatement:
    """One Snowflake COMMENT statement derived from user input."""

    target_type: str
    identifier: str
    sql: str


@dataclass(frozen=True)
class SnowflakeDescriptionUpdatePlan:
    """Validated COMMENT statements ready for review or execution."""

    statements: tuple[SnowflakeDescriptionUpdateStatement, ...]


@dataclass(frozen=True)
class SnowflakeDescriptionUpdateResult:
    """Result from planning and optionally applying description updates."""

    plan: SnowflakeDescriptionUpdatePlan
    applied: bool


class SnowflakeExecutableCursor(Protocol):
    """Cursor protocol required for applying COMMENT statements."""

    def execute(self, sql: str) -> object:
        """Execute one SQL statement."""


class SnowflakeExecutableConnection(Protocol):
    """Connection protocol required for applying COMMENT statements."""

    def cursor(self) -> SnowflakeExecutableCursor:
        """Return an executable cursor."""


def build_description_update_plan(
    updates: list[DescriptionUpdateRequest],
    default_database: str | None = None,
    default_schema: str | None = None,
) -> SnowflakeDescriptionUpdatePlan:
    """Build validated Snowflake COMMENT statements from user-provided descriptions."""

    statements: list[SnowflakeDescriptionUpdateStatement] = []
    for update in updates:
        database = update.database or default_database
        schema = update.schema or default_schema
        if not database:
            raise ValueError(f"Database is required for table {update.table}.")
        if not schema:
            raise ValueError(f"Schema is required for table {update.table}.")

        table_identifier = quote_qualified_identifier(database, schema, update.table)
        if update.table_description is not None:
            description = validate_description(update.table_description)
            statements.append(
                SnowflakeDescriptionUpdateStatement(
                    target_type="table",
                    identifier=table_identifier,
                    sql=f"COMMENT ON TABLE {table_identifier} IS {quote_sql_string(description)}",
                )
            )

        for column, description_value in (update.column_descriptions or {}).items():
            description = validate_description(description_value)
            column_identifier = f"{table_identifier}.{quote_identifier(column)}"
            statements.append(
                SnowflakeDescriptionUpdateStatement(
                    target_type="column",
                    identifier=column_identifier,
                    sql=f"COMMENT ON COLUMN {column_identifier} IS {quote_sql_string(description)}",
                )
            )

    return SnowflakeDescriptionUpdatePlan(statements=tuple(statements))


def apply_description_update_plan(
    connection: SnowflakeExecutableConnection,
    plan: SnowflakeDescriptionUpdatePlan,
) -> None:
    """Execute each statement in a validated description update plan."""

    cursor = connection.cursor()
    for statement in plan.statements:
        cursor.execute(statement.sql)


def quote_qualified_identifier(*parts: str) -> str:
    """Quote a Snowflake qualified identifier from validated parts."""

    return ".".join(quote_identifier(part) for part in parts)


def quote_identifier(identifier: str) -> str:
    """Validate and quote one Snowflake identifier part."""

    if not IDENTIFIER_PATTERN.match(identifier):
        raise ValueError(f"Unsafe Snowflake identifier: {identifier}")
    return f'"{identifier}"'


def quote_sql_string(value: str) -> str:
    """Quote a Snowflake SQL string literal."""

    return "'" + value.replace("'", "''") + "'"


def validate_description(description: str) -> str:
    """Validate user-provided metadata description text."""

    cleaned = description.strip()
    if not cleaned:
        raise ValueError("Description cannot be blank.")
    if "\x00" in cleaned:
        raise ValueError("Description cannot contain null bytes.")
    return cleaned

