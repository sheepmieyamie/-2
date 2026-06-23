from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / "backend" / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    tikhub_api_token: str = ""
    tikhub_base_url: str = "https://api.tikhub.io"

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-5.5"
    openai_wire_api: str = "responses"  # responses | chat
    openai_reasoning_effort: str = "high"  # low | medium | high

    database_url: str = f"sqlite:///{ROOT_DIR / 'data' / 'content_library.db'}"
    forbidden_words_path: str = str(ROOT_DIR / "data" / "forbidden_words.txt")


settings = Settings()
