from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str
    celery_broker_url: str
    celery_result_backend: str

    s3_endpoint: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str
    s3_region: str = "us-east-1"

    whisper_backend: str = "mlx"            # mlx | faster | openai
    whisper_model: str = "large-v3"
    whisper_language: str = "yue"           # Cantonese
    whisper_initial_prompt_file: str | None = None
    openai_api_key: str | None = None

    dashscope_api_key: str
    qwen_model: str = "qwen2.5-72b-instruct"
    qwen_fallback_model: str = "qwen2.5-14b-instruct"
    dashscope_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

    embedding_backend: str = "dashscope"
    embedding_model: str = "text-embedding-v3"
    embedding_dim: int = 1024

    log_level: str = "INFO"

    @property
    def whisper_initial_prompt(self) -> str:
        if not self.whisper_initial_prompt_file:
            return ""
        p = Path(self.whisper_initial_prompt_file)
        if not p.exists():
            return ""
        return p.read_text(encoding="utf-8").strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()
