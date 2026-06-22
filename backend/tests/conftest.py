import pytest

from app import config


@pytest.fixture(autouse=True)
def isolate_dotenv(monkeypatch):
    """Keep tests hermetic: don't read the developer's real backend/.env (which
    may hold live Supabase/API credentials) so `Settings()` reflects only what a
    test passes explicitly."""
    monkeypatch.setitem(config.Settings.model_config, "env_file", None)
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()
