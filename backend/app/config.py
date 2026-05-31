from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "ChiangMaiEyes API"
    cache_dir: Path = Field(default=Path(__file__).resolve().parent.parent / "data")
    cors_origins: str = "http://localhost:5173,https://chiangmaieyes.vercel.app"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"
    gistda_api_key: str | None = None
    nasa_firms_map_key: str | None = None

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
