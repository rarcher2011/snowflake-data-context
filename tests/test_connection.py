from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from openai_snowflake_agent_context import SnowflakeContextConfig
from openai_snowflake_agent_context.connection import (
    build_private_key_connection_kwargs,
    load_private_key_der,
)


def test_build_private_key_connection_kwargs_uses_private_key_without_password(
    tmp_path: Path,
) -> None:
    private_key_path = _write_private_key(tmp_path)
    config = SnowflakeContextConfig(
        account="test-account",
        user="analyst",
        warehouse="agent_wh",
        role="TRANSFORMER",
        database="ANALYTICS",
        schema="PUBLIC",
        private_key_path=str(private_key_path),
    )

    kwargs = build_private_key_connection_kwargs(config)

    assert kwargs["account"] == "test-account"
    assert kwargs["user"] == "analyst"
    assert kwargs["warehouse"] == "agent_wh"
    assert kwargs["role"] == "TRANSFORMER"
    assert kwargs["database"] == "ANALYTICS"
    assert kwargs["schema"] == "PUBLIC"
    assert isinstance(kwargs["private_key"], bytes)
    assert "password" not in kwargs


def test_build_private_key_connection_kwargs_accepts_explicit_key_path(
    tmp_path: Path,
) -> None:
    private_key_path = _write_private_key(tmp_path)
    config = SnowflakeContextConfig(
        account="test-account",
        user="analyst",
        warehouse="agent_wh",
    )

    kwargs = build_private_key_connection_kwargs(config, private_key_path=private_key_path)

    assert isinstance(kwargs["private_key"], bytes)


def test_build_private_key_connection_kwargs_requires_key_path() -> None:
    config = SnowflakeContextConfig(
        account="test-account",
        user="analyst",
        warehouse="agent_wh",
    )

    with pytest.raises(ValueError, match="private_key_path"):
        build_private_key_connection_kwargs(config)


def test_load_private_key_der_supports_encrypted_keys(tmp_path: Path) -> None:
    private_key_path = _write_private_key(tmp_path, passphrase="secret-passphrase")

    private_key = load_private_key_der(
        private_key_path,
        private_key_passphrase="secret-passphrase",
    )

    assert isinstance(private_key, bytes)


def _write_private_key(tmp_path: Path, passphrase: str | None = None) -> Path:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    encryption_algorithm: serialization.KeySerializationEncryption
    if passphrase is None:
        encryption_algorithm = serialization.NoEncryption()
    else:
        encryption_algorithm = serialization.BestAvailableEncryption(
            passphrase.encode("utf-8")
        )
    private_key_path = tmp_path / "snowflake_private_key.pem"
    private_key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=encryption_algorithm,
        )
    )
    return private_key_path
