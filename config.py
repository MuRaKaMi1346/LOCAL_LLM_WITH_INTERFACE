from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    line_channel_access_token: str = Field(..., env="LINE_CHANNEL_ACCESS_TOKEN")
    line_channel_secret: str = Field(..., env="LINE_CHANNEL_SECRET")

    ollama_base_url: str = Field("http://localhost:11434", env="OLLAMA_BASE_URL")
    ollama_chat_model: str = Field("llama3.2", env="OLLAMA_CHAT_MODEL")
    ollama_embed_model: str = Field("nomic-embed-text", env="OLLAMA_EMBED_MODEL")

    faculty_name: str = Field("หน่วยงานของคุณ", env="FACULTY_NAME")
    university_name: str = Field("มหาวิทยาลัยตัวอย่าง", env="UNIVERSITY_NAME")

    rag_top_k: int = Field(5, env="RAG_TOP_K")
    chunk_size: int = Field(800, env="CHUNK_SIZE")
    chunk_overlap: int = Field(100, env="CHUNK_OVERLAP")

    max_history_turns: int = Field(8, env="MAX_HISTORY_TURNS")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
