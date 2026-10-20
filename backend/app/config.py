import os
from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_GISTDA_DISASTER_API_KEY = os.getenv("DEFAULT_GISTDA_DISASTER_API_KEY")


class Settings(BaseSettings):
    # Absolute path so the keys load no matter the working directory (the app
    # runs from backend/, the hourly refresh task runs from the repo root).
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"), extra="ignore"
    )

    app_name: str = "ChiangMaiEyes API"
    cache_dir: Path = Field(
        default_factory=lambda: Path("/tmp") if os.getenv("VERCEL") else Path(__file__).resolve().parent / "data"
    )
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,https://chiangmaieyes.vercel.app"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"
    groq_api_keys: str | None = None
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    gistda_api_key: str | None = None
    gistda_disaster_api_key: str | None = DEFAULT_GISTDA_DISASTER_API_KEY
    nasa_firms_map_key: str | None = None
    # RFD Firemap is useful enrichment, but it is not cloud-friendly because it
    # blocks some serverless infrastructure. Keep it opt-in so production can
    # run from NASA/GISTDA without a local Thailand PC.
    hotspot_include_rfd: bool = False
    # Keep demo/seed layers out of production by default. Enable only for local
    # prototypes or design reviews where clearly-labelled sample data is useful.
    allow_prototype_data: bool = False
    earth_engine_enabled: bool = False
    earth_engine_project: str | None = None
    earth_engine_service_account: str | None = None
    earth_engine_private_key_path: Path | None = None
    # Copernicus Data Space (CDSE) OAuth client for real Sentinel-2 dryness.
    # Free and operational/government-usable (unlike GEE noncommercial tier).
    copernicus_client_id: str | None = None
    copernicus_client_secret: str | None = None
    aqicn_token: str | None = None
    satellite_layers_file: Path | None = None
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    supabase_anon_key: str | None = None
    resend_api_key: str | None = None
    resend_from_email: str | None = None
    resend_webhook_secret: str | None = None
    # Real community delivery stays disabled until a sender domain is verified.
    community_email_enabled: bool = False
    community_email_test_recipient: str | None = None
    community_job_secret: str | None = None
    # LINE Official Account (Messaging API). Alerts stay off until both are set.
    line_channel_secret: str | None = None
    line_channel_access_token: str | None = None
    line_basic_id: str = '@241mevgs'
    # Public dust alerts stay paused until district values come from real
    # stations (only two, both in Mueang, today). Set LINE_DUST_ALERTS_ENABLED
    # to turn the chat commands and the sends back on.
    line_dust_alerts_enabled: bool = False
    community_scheduler_enabled: bool = False
    community_site_url: str = 'https://chiangmaieyes.vercel.app'
    remote_snapshot_base_url: str | None = (
        "https://raw.githubusercontent.com/67010655/ChiangMaiEyes/"
        "codex/production-wind-chip"
    )

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
