"""Snowflake table sampling helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol


class SnowflakeSamplingConnection(Protocol):
    """Minimal connection protocol for table sampling."""

    def cursor(self) -> object:
        """Return a cursor-like object."""


class SnowflakeSamplingCursor(Protocol):
    """Minimal cursor protocol for executing sampling SQL."""

    def execute(self, sql: str) -> object:
        """Execute SQL against Snowflake."""


@dataclass(frozen=True)
class SampledTableResult:
    """Result metadata for a generated Snowflake sample table."""

    source_table: str
    destination_table: str
    sample_percent: float
    sql: str
    executed: bool = True

    @property
    def sampled_table(self) -> str:
        """Return the destination table agents should use after sampling."""

        return self.destination_table

    def to_status_update(self) -> dict[str, object]:
        """Return status fields that make downstream harness runs sample-aware."""

        data = asdict(self)
        data["sampled_table"] = self.sampled_table
        return data


def sample_table(
    connection: SnowflakeSamplingConnection,
    table_name: str,
    destination_location: str,
    *,
    sample_percent: float = 1.0,
) -> SampledTableResult:
    """Create a random Snowflake sample table and return its execution metadata."""

    sql = build_sample_table_sql(
        table_name,
        destination_location,
        sample_percent=sample_percent,
    )
    cursor = connection.cursor()
    _execute(cursor, sql)
    return SampledTableResult(
        source_table=table_name,
        destination_table=destination_location,
        sample_percent=sample_percent,
        sql=sql,
        executed=True,
    )


def build_sample_table_sql(
    table_name: str,
    destination_location: str,
    *,
    sample_percent: float = 1.0,
) -> str:
    """Build SQL for a random Snowflake sample table without executing it."""

    if sample_percent <= 0 or sample_percent > 100:
        raise ValueError("sample_percent must be greater than 0 and less than or equal to 100.")

    source_identifier = quote_snowflake_identifier_path(table_name)
    destination_identifier = quote_snowflake_identifier_path(destination_location)
    sample_literal = _format_sample_percent(sample_percent)
    return (
        f"CREATE OR REPLACE TABLE {destination_identifier} AS\n"
        f"SELECT *\n"
        f"FROM {source_identifier} SAMPLE BERNOULLI ({sample_literal})"
    )


def quote_snowflake_identifier_path(identifier: str) -> str:
    """Quote a potentially dotted Snowflake identifier path."""

    parts = _split_identifier_path(identifier)
    if not parts:
        raise ValueError("Snowflake identifier cannot be empty.")
    return ".".join(_quote_identifier_part(part) for part in parts)


def _execute(cursor: object, sql: str) -> None:
    execute = getattr(cursor, "execute", None)
    if execute is None:
        raise TypeError("Snowflake cursor must expose an execute(sql) method.")
    execute(sql)


def _split_identifier_path(identifier: str) -> list[str]:
    value = identifier.strip()
    if not value:
        raise ValueError("Snowflake identifier cannot be empty.")

    parts: list[str] = []
    current: list[str] = []
    in_quotes = False
    index = 0
    while index < len(value):
        character = value[index]
        if character == '"':
            if in_quotes and index + 1 < len(value) and value[index + 1] == '"':
                current.append('"')
                index += 2
                continue
            in_quotes = not in_quotes
            index += 1
            continue
        if character == "." and not in_quotes:
            part = "".join(current).strip()
            if not part:
                raise ValueError(f"Snowflake identifier has an empty path segment: {identifier}")
            parts.append(part)
            current = []
            index += 1
            continue
        current.append(character)
        index += 1

    if in_quotes:
        raise ValueError(f"Snowflake identifier has an unterminated quote: {identifier}")

    part = "".join(current).strip()
    if not part:
        raise ValueError(f"Snowflake identifier has an empty path segment: {identifier}")
    parts.append(part)
    return parts


def _quote_identifier_part(part: str) -> str:
    return '"' + part.replace('"', '""') + '"'


def _format_sample_percent(sample_percent: float) -> str:
    normalized = float(sample_percent)
    if normalized.is_integer():
        return str(int(normalized))
    return str(normalized)
