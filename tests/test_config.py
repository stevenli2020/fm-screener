from pathlib import Path

import pytest

from financial_market.config import ConfigurationError, Settings


def test_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FM_DATA_SERVER_BASE_URL", "http://localhost:9000/")
    monkeypatch.setenv("FM_DATA_SERVER_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("FM_DATA_SERVER_MAX_RETRIES", "4")
    monkeypatch.setenv("FM_DATABASE_PATH", "data/test.sqlite3")
    monkeypatch.setenv("FM_RISK_RULES_PATH", "config/test-risk.json")

    settings = Settings.from_env()

    assert settings.data_server_base_url == "http://localhost:9000"
    assert settings.data_server_timeout_seconds == 3.5
    assert settings.data_server_max_retries == 4
    assert settings.database_path == Path("data/test.sqlite3")
    assert settings.risk_rules_path == Path("config/test-risk.json")


@pytest.mark.parametrize("url", ["localhost:8000", "file:///tmp/server", "http://"])
def test_settings_reject_invalid_base_url(url: str) -> None:
    with pytest.raises(ConfigurationError):
        Settings(data_server_base_url=url)


def test_settings_reject_zero_timeout() -> None:
    with pytest.raises(ConfigurationError):
        Settings(data_server_timeout_seconds=0)
