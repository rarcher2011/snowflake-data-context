#!/usr/bin/env python3
"""Package and deploy the ChatGPT Actions adapter to AWS Lambda."""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path


DEFAULT_RUNTIME = "python3.11"
DEFAULT_HANDLER = "openai_snowflake_agent_context.aws_lambda.handler"


@dataclass(frozen=True)
class AwsDeployConfig:
    """Configuration for deploying the action service to AWS Lambda."""

    function_name: str
    role_arn: str
    region: str
    server_url: str
    runtime: str = DEFAULT_RUNTIME
    handler: str = DEFAULT_HANDLER
    build_dir: Path = Path("build/aws-lambda")
    artifact_path: Path = Path("dist/aws-lambda/action-service.zip")
    create_function_url: bool = True


def build_lambda_artifact(config: AwsDeployConfig, dry_run: bool = False) -> Path:
    """Build a Lambda zip artifact containing this package and optional server deps."""

    build_dir = config.build_dir.resolve()
    artifact_path = config.artifact_path.resolve()
    if dry_run:
        return artifact_path

    if build_dir.exists():
        shutil.rmtree(build_dir)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    build_dir.mkdir(parents=True, exist_ok=True)

    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            ".[chatgpt-plugin,aws]",
            "--target",
            str(build_dir),
        ],
        dry_run=False,
    )

    if artifact_path.exists():
        artifact_path.unlink()
    with zipfile.ZipFile(artifact_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in build_dir.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(build_dir))
    return artifact_path


def deployment_commands(config: AwsDeployConfig, artifact_path: Path) -> list[list[str]]:
    """Return AWS CLI commands needed to create/update the Lambda action service."""

    env_vars = f"Variables={{ACTION_SERVER_URL={config.server_url}}}"
    commands = [
        [
            "aws",
            "lambda",
            "get-function",
            "--function-name",
            config.function_name,
            "--region",
            config.region,
        ],
        [
            "aws",
            "lambda",
            "create-function",
            "--function-name",
            config.function_name,
            "--runtime",
            config.runtime,
            "--handler",
            config.handler,
            "--role",
            config.role_arn,
            "--zip-file",
            f"fileb://{artifact_path}",
            "--environment",
            env_vars,
            "--region",
            config.region,
        ],
        [
            "aws",
            "lambda",
            "update-function-code",
            "--function-name",
            config.function_name,
            "--zip-file",
            f"fileb://{artifact_path}",
            "--region",
            config.region,
        ],
        [
            "aws",
            "lambda",
            "update-function-configuration",
            "--function-name",
            config.function_name,
            "--environment",
            env_vars,
            "--region",
            config.region,
        ],
    ]
    if config.create_function_url:
        commands.append(
            [
                "aws",
                "lambda",
                "create-function-url-config",
                "--function-name",
                config.function_name,
                "--auth-type",
                "NONE",
                "--region",
                config.region,
            ]
        )
    return commands


def deploy(config: AwsDeployConfig, dry_run: bool = False) -> None:
    """Build and deploy the Lambda action service."""

    artifact_path = build_lambda_artifact(config, dry_run=dry_run)
    commands = deployment_commands(config, artifact_path)

    if dry_run:
        for command in commands:
            print(_format_command(command))
        return

    function_exists = _run(commands[0], check=False).returncode == 0
    if function_exists:
        _run(commands[2])
        _run(commands[3])
    else:
        _run(commands[1])

    if config.create_function_url:
        _run(commands[4], check=False)


def parse_args(argv: list[str] | None = None) -> AwsDeployConfig:
    """Parse CLI arguments into an AWS deployment config."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--function-name", required=True)
    parser.add_argument("--role-arn", required=True)
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    parser.add_argument("--server-url", required=True)
    parser.add_argument("--runtime", default=DEFAULT_RUNTIME)
    parser.add_argument("--handler", default=DEFAULT_HANDLER)
    parser.add_argument("--build-dir", default="build/aws-lambda")
    parser.add_argument("--artifact-path", default="dist/aws-lambda/action-service.zip")
    parser.add_argument("--no-function-url", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    config = AwsDeployConfig(
        function_name=args.function_name,
        role_arn=args.role_arn,
        region=args.region,
        server_url=args.server_url,
        runtime=args.runtime,
        handler=args.handler,
        build_dir=Path(args.build_dir),
        artifact_path=Path(args.artifact_path),
        create_function_url=not args.no_function_url,
    )
    if args.dry_run:
        deploy(config, dry_run=True)
        raise SystemExit(0)
    return config


def main(argv: list[str] | None = None) -> int:
    config = parse_args(argv)
    deploy(config)
    return 0


def _run(command: list[str], check: bool = True, dry_run: bool = False) -> subprocess.CompletedProcess[str]:
    if dry_run:
        print(_format_command(command))
        return subprocess.CompletedProcess(command, 0, "", "")
    return subprocess.run(command, check=check, text=True)


def _format_command(command: list[str]) -> str:
    return shlex.join(command)


if __name__ == "__main__":
    raise SystemExit(main())
