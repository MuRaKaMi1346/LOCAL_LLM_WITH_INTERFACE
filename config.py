import json
import logging
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Resolve paths relative to this file, not the CWD —
# so imports from any working directory work correctly.
_HERE = Path(__file__).parent
_CONFIG_JSON = _HERE / "config.json"

_RUNTIME_KEYS = frozenset({
    "line_channel_access_token", "line_channel_secret",
    "ollama_base_url", "ollama_chat_model", "ollama_embed_model",
    "faculty_name", "university_name",
    "rag_top_k", "chunk_size", "chunk_overlap", "max_history_turns",
})


class Settings(BaseSettings):
    line_channel_access_token: str = Field("", env="LINE_CHANNEL_ACCESS_TOKEN")
    line_channel_secret: str = Field("", env="LINE_CHANNEL_SECRET")

    ollama_base_url: str = Field("http://localhost:11434", env="OLLAMA_BASE_URL")
    ollama_chat_model: str = Field("llama3.2", env="OLLAMA_CHAT_MODEL")
    ollama_embed_model: str = Field("nomic-embed-text", env="OLLAMA_EMBED_MODEL")

    faculty_name: str = Field("หน่วยงานของคุณ", env="FACULTY_NAME")
    university_name: str = Field("มหาวิทยาลัยตัวอย่าง", env="UNIVERSITY_NAME")

    rag_top_k: int = Field(10, env="RAG_TOP_K")
    chunk_size: int = Field(1200, env="CHUNK_SIZE")
    chunk_overlap: int = Field(150, env="CHUNK_OVERLAP")

    max_history_turns: int = Field(8, env="MAX_HISTORY_TURNS")

    # pydantic-settings v2: use SettingsConfigDict instead of inner class Config
    model_config = SettingsConfigDict(
        env_file=str(_HERE / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


def _apply_config_json(s: Settings) -> Settings:
    if not _CONFIG_JSON.exists():
        return s
    try:
        data = json.loads(_CONFIG_JSON.read_text(encoding="utf-8"))
        updates = {k: v for k, v in data.items() if k in _RUNTIME_KEYS}
        if updates:
            return s.model_copy(update=updates)
    except Exception:
        logger.warning("config.json is invalid JSON — using defaults", exc_info=True)
    return s


settings = _apply_config_json(Settings())
