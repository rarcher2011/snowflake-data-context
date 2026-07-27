"""Configuration types for Snowflake metadata context retrieval."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SnowflakeContextConfig:
    """Runtime configuration for metadata retrieval and context packing."""

    account: str
    user: str
    warehouse: str
    role: str | None = None
    database: str | None = None
    schema: str | None = None
    private_key_path: str | None = None
    max_tables: int = 25
    max_columns_per_table: int = 80
    include_governance: bool = True
    include_samples: bool = False
    token_budget: int = 8_000
