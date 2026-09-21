"""Format Snowflake metadata context for agent prompts."""

from __future__ import annotations

from .metadata import TableContext


def format_table_context(
    tables: list[TableContext] | tuple[TableContext, ...],
    *,
    token_budget: int | None = None,
) -> str:
    """Return Markdown context for Snowflake tables within a simple token budget.

    The budget uses a conservative character approximation so callers can keep
    prompt context bounded without depending on a tokenizer package.
    """

    if token_budget is not None and token_budget <= 0:
        raise ValueError("token_budget must be greater than zero when provided.")

    blocks = [_format_table_block(table) for table in tables]
    markdown = "\n\n".join(blocks)
    if token_budget is None:
        return markdown

    max_chars = token_budget * 4
    truncation_notice = "\n\n[Context truncated.]"
    if len(markdown) <= max_chars:
        return markdown
    if max_chars <= len(truncation_notice):
        return markdown[:max_chars]
    return markdown[: max_chars - len(truncation_notice)].rstrip() + truncation_notice


def _format_table_block(table: TableContext) -> str:
    if table.context_markdown.strip():
        return table.context_markdown.strip()

    lines = [
        f"### {table.database}.{table.schema}.{table.name}",
        f"- Type: {table.kind}",
        f"- Description: {table.description or 'No description available.'}",
        "",
        "Columns:",
    ]
    lines.extend(f"- {column}" for column in table.columns)
    return "\n".join(lines)
