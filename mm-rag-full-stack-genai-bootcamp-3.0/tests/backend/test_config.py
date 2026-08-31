import pytest
from pydantic import SecretStr, ValidationError

from backend.app.core.config import (
    DEFAULT_OPENAI_CHAT_MODEL,
    DEFAULT_OPENAI_EMBEDDING_MODEL,
    Settings,
)


def test_blank_openai_model_names_use_supported_defaults() -> None:
    settings = Settings(openai_chat_model="", openai_embedding_model="   ")

    assert settings.openai_chat_model == DEFAULT_OPENAI_CHAT_MODEL
    assert settings.openai_embedding_model == DEFAULT_OPENAI_EMBEDDING_MODEL


def test_openai_model_names_are_trimmed() -> None:
    settings = Settings(
        openai_chat_model="  custom-chat-model  ",
        openai_embedding_model="  custom-embedding-model  ",
    )

    assert settings.openai_chat_model == "custom-chat-model"
    assert settings.openai_embedding_model == "custom-embedding-model"


def test_s3_backend_requires_a_complete_credential_pair() -> None:
    with pytest.raises(ValidationError, match="S3 credentials are required"):
        Settings(
            object_storage_backend="s3",
            s3_access_key_id=SecretStr(""),
            s3_secret_access_key=SecretStr(""),
        )

    with pytest.raises(ValidationError, match="must be configured together"):
        Settings(
            s3_access_key_id=SecretStr("local-access"),
            s3_secret_access_key=SecretStr(""),
        )


def test_s3_configuration_is_normalized_without_exposing_secrets() -> None:
    settings = Settings(
        object_storage_backend="s3",
        s3_endpoint_url="http://127.0.0.1:8333/",
        s3_access_key_id=SecretStr("local-access"),
        s3_secret_access_key=SecretStr("local-secret"),
    )

    assert settings.s3_endpoint_url == "http://127.0.0.1:8333"
    assert "local-secret" not in repr(settings)


def test_s3_bucket_names_must_be_dns_compatible() -> None:
    with pytest.raises(ValidationError, match="DNS-compatible"):
        Settings(s3_originals_bucket="Not_A_Bucket")


def test_production_nonlocal_boundaries_require_tls_and_explicit_s3_encryption() -> None:
    with pytest.raises(ValidationError, match="server-side encryption"):
        Settings(
            app_env="production",
            object_storage_backend="s3",
            s3_endpoint_url="https://storage.example.test",
            s3_access_key_id=SecretStr("access"),
            s3_secret_access_key=SecretStr("secret"),
        )

    with pytest.raises(ValidationError, match="QDRANT_URL"):
        Settings(
            app_env="production",
            object_storage_backend="local",
            qdrant_url="http://qdrant.example.test",
        )


def test_kms_encryption_requires_a_key_identifier() -> None:
    with pytest.raises(ValidationError, match="S3_KMS_KEY_ID"):
        Settings(s3_server_side_encryption="aws:kms")
