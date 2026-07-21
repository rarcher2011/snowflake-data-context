from pathlib import Path

from scripts.deploy_aws import (
    DEFAULT_HANDLER,
    DEFAULT_RUNTIME,
    AwsDeployConfig,
    deployment_commands,
)


def test_deployment_commands_create_or_update_lambda_action_service() -> None:
    config = AwsDeployConfig(
        function_name="snowflake-agent-context-actions",
        role_arn="arn:aws:iam::123456789012:role/lambda-actions-role",
        region="us-east-1",
        server_url="https://actions.example.com",
    )

    commands = deployment_commands(config, Path("/tmp/action-service.zip"))

    assert commands[0] == [
        "aws",
        "lambda",
        "get-function",
        "--function-name",
        "snowflake-agent-context-actions",
        "--region",
        "us-east-1",
    ]
    assert commands[1] == [
        "aws",
        "lambda",
        "create-function",
        "--function-name",
        "snowflake-agent-context-actions",
        "--runtime",
        DEFAULT_RUNTIME,
        "--handler",
        DEFAULT_HANDLER,
        "--role",
        "arn:aws:iam::123456789012:role/lambda-actions-role",
        "--zip-file",
        "fileb:///tmp/action-service.zip",
        "--environment",
        "Variables={ACTION_SERVER_URL=https://actions.example.com}",
        "--region",
        "us-east-1",
    ]
    assert commands[2][0:3] == ["aws", "lambda", "update-function-code"]
    assert commands[3][0:3] == ["aws", "lambda", "update-function-configuration"]
    assert commands[4] == [
        "aws",
        "lambda",
        "create-function-url-config",
        "--function-name",
        "snowflake-agent-context-actions",
        "--auth-type",
        "NONE",
        "--region",
        "us-east-1",
    ]


def test_deployment_commands_can_skip_function_url() -> None:
    config = AwsDeployConfig(
        function_name="snowflake-agent-context-actions",
        role_arn="arn:aws:iam::123456789012:role/lambda-actions-role",
        region="us-west-2",
        server_url="https://actions.example.com",
        create_function_url=False,
    )

    commands = deployment_commands(config, Path("/tmp/action-service.zip"))

    assert len(commands) == 4
