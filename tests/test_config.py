from dataclasses import FrozenInstanceError

import pytest

from openai_snowflake_agent_context import SnowflakeContextConfig


def test_config_defaults_are_safe_for_metadata_only_context() -> None:
    config = SnowflakeContextConfig(
        account="test-account",
        user="analyst",
        warehouse="agent_wh",
    )

    assert config.role is None
    assert config.database is None
    assert config.schema is None
    assert config.max_tables == 25
    assert config.max_columns_per_table == 80
    assert config.include_governance is True
    assert config.include_samples is False
    assert config.token_budget == 8_000


def test_config_is_immutable_after_creation() -> None:
    config = SnowflakeContextConfig(
        account="test-account",
        user="analyst",
        warehouse="agent_wh",
    )

    with pytest.raises(FrozenInstanceError):
        config.token_budget = 16_000  # type: ignore[misc]

