import pytest

from openai_snowflake_agent_context.aws_lambda import create_lambda_handler


def test_create_lambda_handler_requires_optional_aws_extra_when_missing() -> None:
    with pytest.raises(RuntimeError, match="Install the aws extra"):
        create_lambda_handler("https://actions.example.com")

