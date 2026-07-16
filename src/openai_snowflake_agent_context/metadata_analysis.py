"""Description quality analysis for Snowflake table metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from .metadata import TableContext


QUALITY_MISSING = "missing"
QUALITY_WEAK = "weak"
QUALITY_ADEQUATE = "adequate"
QUALITY_STRONG = "strong"

GENERIC_DESCRIPTION_PATTERNS = (
    "data",
    "field",
    "column",
    "value",
    "info",
    "information",
    "identifier",
    "id",
    "name",
    "date",
    "description",
)

BUSINESS_CONTEXT_WORDS = (
    "customer",
    "order",
    "account",
    "transaction",
    "status",
    "source",
    "system",
    "business",
    "calculated",
    "derived",
    "represents",
    "used",
    "grain",
    "one row",
)


@dataclass(frozen=True)
class DescriptionQualityResult:
    """Quality score and improvement guidance for one description."""

    has_description: bool
    quality: str
    score: float
    issues: tuple[str, ...]
    recommendation: str | None


@dataclass(frozen=True)
class ColumnDescriptionAnalysis:
    """Description analysis for one table column."""

    table_identifier: str
    column_name: str
    raw_column: str
    description: str | None
    result: DescriptionQualityResult


@dataclass(frozen=True)
class TableDescriptionAnalysis:
    """Description analysis for one table and its columns."""

    table_identifier: str
    table_description: str | None
    table_result: DescriptionQualityResult
    columns: tuple[ColumnDescriptionAnalysis, ...]

    @property
    def columns_needing_improvement(self) -> tuple[ColumnDescriptionAnalysis, ...]:
        return tuple(
            column
            for column in self.columns
            if column.result.quality in {QUALITY_MISSING, QUALITY_WEAK}
        )


@dataclass(frozen=True)
class SchemaDescriptionAnalysis:
    """Description quality rollup for a schema's table metadata."""

    tables: tuple[TableDescriptionAnalysis, ...]
    total_tables: int
    total_columns: int
    described_columns: int
    missing_column_descriptions: int
    weak_column_descriptions: int
    adequate_column_descriptions: int
    strong_column_descriptions: int

    @property
    def columns_needing_improvement(self) -> tuple[ColumnDescriptionAnalysis, ...]:
        return tuple(
            column
            for table in self.tables
            for column in table.columns_needing_improvement
        )

    @property
    def description_coverage(self) -> float:
        if self.total_columns == 0:
            return 1.0
        return self.described_columns / self.total_columns


def analyze_table_metadata_descriptions(
    tables: Sequence[TableContext],
) -> SchemaDescriptionAnalysis:
    """Analyze table and column description quality for agent-readiness."""

    table_results = tuple(_analyze_table(table) for table in tables)
    columns = [column for table in table_results for column in table.columns]
    described_columns = sum(1 for column in columns if column.result.has_description)
    missing = sum(1 for column in columns if column.result.quality == QUALITY_MISSING)
    weak = sum(1 for column in columns if column.result.quality == QUALITY_WEAK)
    adequate = sum(1 for column in columns if column.result.quality == QUALITY_ADEQUATE)
    strong = sum(1 for column in columns if column.result.quality == QUALITY_STRONG)

    return SchemaDescriptionAnalysis(
        tables=table_results,
        total_tables=len(table_results),
        total_columns=len(columns),
        described_columns=described_columns,
        missing_column_descriptions=missing,
        weak_column_descriptions=weak,
        adequate_column_descriptions=adequate,
        strong_column_descriptions=strong,
    )


def _analyze_table(table: TableContext) -> TableDescriptionAnalysis:
    identifier = f"{table.database}.{table.schema}.{table.name}"
    return TableDescriptionAnalysis(
        table_identifier=identifier,
        table_description=table.description,
        table_result=score_description(table.name, table.description),
        columns=tuple(_analyze_column(identifier, column) for column in table.columns),
    )


def _analyze_column(table_identifier: str, raw_column: str) -> ColumnDescriptionAnalysis:
    column_name, description = parse_column_description(raw_column)
    return ColumnDescriptionAnalysis(
        table_identifier=table_identifier,
        column_name=column_name,
        raw_column=raw_column,
        description=description,
        result=score_description(column_name, description),
    )


def parse_column_description(raw_column: str) -> tuple[str, str | None]:
    """Extract a column name and optional description from compact metadata text."""

    column_name = raw_column.strip().split(maxsplit=1)[0] if raw_column.strip() else ""
    for separator in (" -- ", " - ", " | "):
        if separator in raw_column:
            left, right = raw_column.split(separator, 1)
            name = left.strip().split(maxsplit=1)[0] if left.strip() else column_name
            return name, _clean_description(right)

    colon_match = re.match(r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_$]*)\b.*?:\s*(?P<desc>.+)$", raw_column)
    if colon_match:
        return colon_match.group("name"), _clean_description(colon_match.group("desc"))

    return column_name, None


def score_description(name: str, description: str | None) -> DescriptionQualityResult:
    """Score a table or column description for coding-agent usefulness."""

    cleaned = _clean_description(description)
    if not cleaned:
        return DescriptionQualityResult(
            has_description=False,
            quality=QUALITY_MISSING,
            score=0.0,
            issues=("description is missing",),
            recommendation=f"Add a description that explains what {name} represents and how agents should use it.",
        )

    words = _words(cleaned)
    issues: list[str] = []
    score = 0.35

    if len(words) < 4:
        issues.append("description is too short")
    elif len(words) < 8:
        score += 0.2
    else:
        score += 0.35

    if _is_generic(cleaned):
        issues.append("description is generic")
        score -= 0.2

    if _mostly_repeats_name(name, cleaned):
        issues.append("description mostly repeats the column or table name")
        score -= 0.15

    lowered = cleaned.lower()
    if any(word in lowered for word in BUSINESS_CONTEXT_WORDS):
        score += 0.2
    else:
        issues.append("description lacks business or usage context")

    score = max(0.05, min(1.0, score))
    quality = _quality_from_score(score)
    recommendation = None
    if quality in {QUALITY_WEAK, QUALITY_ADEQUATE} and issues:
        recommendation = (
            f"Improve {name} by adding business meaning, grain/usage guidance, "
            "source context, or allowed values where relevant."
        )

    return DescriptionQualityResult(
        has_description=True,
        quality=quality,
        score=round(score, 2),
        issues=tuple(issues),
        recommendation=recommendation,
    )


def _quality_from_score(score: float) -> str:
    if score < 0.4:
        return QUALITY_WEAK
    if score < 0.75:
        return QUALITY_ADEQUATE
    return QUALITY_STRONG


def _clean_description(description: str | None) -> str | None:
    if description is None:
        return None
    cleaned = description.strip().strip("-").strip()
    return cleaned or None


def _words(value: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+", value.lower())


def _is_generic(description: str) -> bool:
    words = _words(description)
    return bool(words) and all(word in GENERIC_DESCRIPTION_PATTERNS for word in words)


def _mostly_repeats_name(name: str, description: str) -> bool:
    name_words = set(_words(name.replace("_", " ")))
    description_words = _words(description)
    if not name_words or not description_words:
        return False
    overlap = sum(1 for word in description_words if word in name_words)
    return overlap / len(description_words) >= 0.7

