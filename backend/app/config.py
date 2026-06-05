from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Absolute path so the keys load no matter the working directory (the app
    # runs from backend/, the hourly refresh task runs from the repo root).
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"), extra="ignore"
    )

    app_name: str = "ChiangMaiEyes API"
    cache_dir: Path = Field(default=Path(__file__).resolve().parent.parent / "data")
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,https://chiangmaieyes.vercel.app"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"
    groq_api_keys: str | None = None
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    gistda_api_key: str | None = None
    nasa_firms_map_key: str | None = None

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def groq_key_list(self) -> list[str]:
        keys = self.groq_api_keys or self.groq_api_key
        if not keys:
            return []
        return [key.strip() for key in keys.split(",") if key.strip().startswith("gsk_")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
