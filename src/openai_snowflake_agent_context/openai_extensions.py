"""OpenAI SDK wrapper helpers for Snowflake metadata context."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from .formatter import format_table_context
from .metadata import SnowflakeMetadataProvider

ResponseT = TypeVar("ResponseT")


def build_snowflake_context(
    provider: SnowflakeMetadataProvider,
    *,
    tables: list[str] | None = None,
    query: str | None = None,
    token_budget: int | None = None,
) -> str:
    """Build Markdown Snowflake context for an OpenAI request."""

    table_context = provider.describe_tables(tables)
    context = format_table_context(table_context, token_budget=token_budget)
    if query:
        query_note = f"User analysis goal: {query}"
        return f"{query_note}\n\n{context}" if context else query_note
    return context


def with_snowflake_context(
    openai_call: Callable[..., ResponseT],
    provider: SnowflakeMetadataProvider,
    *,
    input: object,
    instructions: str | None = None,
    tables: list[str] | None = None,
    query: str | None = None,
    token_budget: int | None = None,
    **kwargs: object,
) -> ResponseT:
    """Call an OpenAI SDK method with Snowflake metadata added to the request."""

    context = build_snowflake_context(
        provider,
        tables=tables,
        query=query,
        token_budget=token_budget,
    )
    return openai_call(
        **kwargs,
        input=input,
        instructions=_merge_instructions(instructions, context),
    )


def _merge_instructions(instructions: str | None, context: str) -> str:
    context_block = (
        f"Snowflake metadata context:\n\n{context}"
        if context
        else "Snowflake metadata context unavailable."
    )
    if instructions:
        return f"{instructions}\n\n{context_block}"
    return context_block
