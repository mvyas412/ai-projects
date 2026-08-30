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
