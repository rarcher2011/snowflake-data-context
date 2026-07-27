"""Snowflake connection helpers for key-pair authentication."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes

from .config import SnowflakeContextConfig


def load_private_key_der(
    private_key_path: str | Path,
    *,
    private_key_passphrase: str | None = None,
) -> bytes:
    """Load a PEM private key and return Snowflake-compatible DER bytes."""

    password = private_key_passphrase.encode("utf-8") if private_key_passphrase else None
    private_key = serialization.load_pem_private_key(
        Path(private_key_path).expanduser().read_bytes(),
        password=password,
    )
    return _private_key_to_der(private_key)


def build_private_key_connection_kwargs(
    config: SnowflakeContextConfig,
    *,
    private_key_path: str | Path | None = None,
    private_key_passphrase: str | None = None,
) -> dict[str, Any]:
    """Build Snowflake connector kwargs for private-key authentication."""

    resolved_private_key_path = private_key_path or config.private_key_path
    if resolved_private_key_path is None:
        raise ValueError("private_key_path is required for Snowflake private-key authentication.")

    kwargs: dict[str, Any] = {
        "account": config.account,
        "user": config.user,
        "warehouse": config.warehouse,
        "private_key": load_private_key_der(
            resolved_private_key_path,
            private_key_passphrase=private_key_passphrase,
        ),
    }
    if config.role is not None:
        kwargs["role"] = config.role
    if config.database is not None:
        kwargs["database"] = config.database
    if config.schema is not None:
        kwargs["schema"] = config.schema
    return kwargs


def connect_with_private_key(
    config: SnowflakeContextConfig,
    *,
    private_key_path: str | Path | None = None,
    private_key_passphrase: str | None = None,
) -> object:
    """Create a Snowflake connector connection using private-key authentication."""

    import snowflake.connector

    return snowflake.connector.connect(
        **build_private_key_connection_kwargs(
            config,
            private_key_path=private_key_path,
            private_key_passphrase=private_key_passphrase,
        )
    )


def _private_key_to_der(private_key: PrivateKeyTypes) -> bytes:
    return private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
