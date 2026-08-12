"""Suggest Snowflake column descriptions from sample records using OpenAI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from .metadata import SnowflakeConnection, TableContext
from .metadata_analysis import parse_column_description
from .openai_responses import extract_response_text
from .sampling import quote_snowflake_identifier_path


class OpenAIResponsesResource(Protocol):
    """Minimal OpenAI Responses API surface used by this helper."""

    def create(self, **kwargs: Any) -> object:
        """Create a model response."""


class OpenAIClient(Protocol):
    """Minimal OpenAI client protocol expected by description suggestion helpers."""

    responses: OpenAIResponsesResource


@dataclass(frozen=True)
class ColumnDescriptionSuggestion:
    """Model-suggested description for one Snowflake column."""

    column_name: str
    suggested_description: str
    rationale: str | None = None


@dataclass(frozen=True)
class ColumnDescriptionSuggestionResult:
    """Suggested column descriptions and source context used to produce them."""

    table_identifier: str
    sample_sql: str
    sample_records: tuple[dict[str, object], ...]
    suggestions: tuple[ColumnDescriptionSuggestion, ...]
    raw_response_text: str

    @property
    def column_descriptions(self) -> dict[str, str]:
        """Return suggestions keyed by column name for description update workflows."""

        return {
            suggestion.column_name: suggestion.suggested_description
            for suggestion in self.suggestions
        }


def suggest_column_descriptions_from_samples(
    *,
    connection: SnowflakeConnection,
    table: TableContext,
    openai_client: OpenAIClient,
    model: str,
    sample_size: int,
) -> ColumnDescriptionSuggestionResult:
    """Sample a table and ask OpenAI for reviewable column descriptions."""

    sample_sql = build_sample_records_query(
        table_identifier=f"{table.database}.{table.schema}.{table.name}",
        sample_size=sample_size,
    )
    sample_records = fetch_sample_records(connection, sample_sql)
    response_text = _request_description_suggestions(
        openai_client=openai_client,
        model=model,
        table=table,
        sample_records=sample_records,
    )
    suggestions = _parse_suggestions(response_text)
    return ColumnDescriptionSuggestionResult(
        table_identifier=f"{table.database}.{table.schema}.{table.name}",
        sample_sql=sample_sql,
        sample_records=tuple(sample_records),
        suggestions=suggestions,
        raw_response_text=response_text,
    )


def build_sample_records_query(*, table_identifier: str, sample_size: int) -> str:
    """Build a bounded random sample query for a Snowflake table."""

    if sample_size < 1:
        raise ValueError("sample_size must be greater than zero.")
    return (
        "SELECT *\n"
        f"FROM {quote_snowflake_identifier_path(table_identifier)}\n"
        "ORDER BY RANDOM()\n"
        f"LIMIT {sample_size}"
    )


def fetch_sample_records(
    connection: SnowflakeConnection,
    sample_sql: str,
) -> list[dict[str, object]]:
    """Fetch sample records as JSON-serializable dictionaries."""

    cursor = connection.cursor()
    cursor.execute(sample_sql)
    rows = cursor.fetchall()
    column_names = _cursor_column_names(cursor)
    return [_row_to_record(row, column_names) for row in rows]


def _request_description_suggestions(
    *,
    openai_client: OpenAIClient,
    model: str,
    table: TableContext,
    sample_records: Sequence[dict[str, object]],
) -> str:
    payload = {
        "table": {
            "database": table.database,
            "schema": table.schema,
            "name": table.name,
            "kind": table.kind,
            "description": table.description,
            "columns": [_column_payload(column) for column in table.columns],
        },
        "sample_records": list(sample_records),
    }
    response = openai_client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": (
                    "You write concise Snowflake metadata descriptions for analytics teams. "
                    "Use table metadata and the provided sample records only as context. "
                    "Return JSON with a columns array; each item must contain name, "
                    "description, and optional rationale."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(payload, sort_keys=True, default=str),
            },
        ],
    )
    return extract_response_text(response)


def _column_payload(raw_column: str) -> dict[str, str | None]:
    name, description = parse_column_description(raw_column)
    parts = raw_column.strip().split(maxsplit=2)
    data_type = parts[1] if len(parts) > 1 else None
    return {
        "name": name,
        "data_type": data_type,
        "existing_description": description,
    }


def _parse_suggestions(response_text: str) -> tuple[ColumnDescriptionSuggestion, ...]:
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise ValueError("OpenAI response did not contain valid JSON suggestions.") from exc

    raw_columns = payload.get("columns", payload.get("suggestions"))
    if not isinstance(raw_columns, list):
        raise ValueError("OpenAI response must include a columns array.")

    suggestions: list[ColumnDescriptionSuggestion] = []
    for raw_column in raw_columns:
        if not isinstance(raw_column, dict):
            raise ValueError("Each column suggestion must be an object.")
        name = _required_text(raw_column, "name")
        description = _required_text(raw_column, "description")
        rationale = raw_column.get("rationale")
        suggestions.append(
            ColumnDescriptionSuggestion(
                column_name=name,
                suggested_description=description,
                rationale=str(rationale).strip() if rationale is not None else None,
            )
        )
    return tuple(suggestions)


def _cursor_column_names(cursor: object) -> list[str]:
    description = getattr(cursor, "description", None)
    if not isinstance(description, Sequence):
        return []
    names: list[str] = []
    for item in description:
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes)) and item:
            names.append(str(item[0]))
        elif hasattr(item, "name"):
            names.append(str(getattr(item, "name")))
    return names


def _row_to_record(row: object, column_names: Sequence[str]) -> dict[str, object]:
    if isinstance(row, dict):
        return dict(row)
    if isinstance(row, Sequence) and not isinstance(row, (str, bytes)):
        return {
            column_names[index] if index < len(column_names) else f"column_{index + 1}": value
            for index, value in enumerate(row)
        }
    as_dict = getattr(row, "as_dict", None)
    if callable(as_dict):
        value = as_dict()
        if isinstance(value, dict):
            return dict(value)
    return {"value": row}


def _required_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Column suggestion must include non-empty {key}.")
    return value.strip()
