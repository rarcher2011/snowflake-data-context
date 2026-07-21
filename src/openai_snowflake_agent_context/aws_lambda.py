"""AWS Lambda entrypoint for the ChatGPT Actions adapter."""

from __future__ import annotations

import os
from typing import Any

from .chatgpt_plugin import create_app

_HANDLER: Any | None = None


def create_lambda_handler(server_url: str | None = None) -> Any:
    """Create a Mangum Lambda handler for the ChatGPT Actions FastAPI app."""

    try:
        from mangum import Mangum  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on optional AWS extra
        raise RuntimeError(
            "Install the aws extra to use the Lambda handler: pip install -e '.[aws]'"
        ) from exc

    action_server_url = server_url or os.environ.get("ACTION_SERVER_URL") or "https://example.com"
    return Mangum(create_app(action_server_url))


def handler(event: dict[str, Any], context: Any) -> Any:
    """AWS Lambda handler for API Gateway or Lambda Function URL events."""

    global _HANDLER
    if _HANDLER is None:
        _HANDLER = create_lambda_handler()
    return _HANDLER(event, context)
