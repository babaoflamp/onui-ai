from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.config import load_settings
from backend.utils import active_sessions, create_session_token, get_session


def _request(*, headers=None, cookies=None, query_params=None):
    return SimpleNamespace(
        headers=headers or {},
        cookies=cookies or {},
        query_params=query_params or {},
    )


def test_get_session_accepts_bearer_and_cookie_but_not_query_token(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.delenv("APP_ENV", raising=False)
    active_sessions.clear()
    token = create_session_token(7, "learner@example.com")

    assert get_session(_request(headers={"Authorization": f"Bearer {token}"}))["user_id"] == 7
    assert get_session(_request(cookies={"session_token": token}))["email"] == "learner@example.com"
    assert get_session(_request(query_params={"token": token})) is None


def test_load_settings_requires_secret_key_in_production(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "users.db"))
    monkeypatch.setenv("ONUI_TMP_DIR", str(tmp_path / "tmp"))

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        load_settings()


def test_load_settings_parses_security_options(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "prod-secret")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://onui.ai.kr, https://onuiai.kr")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "users.db"))
    monkeypatch.setenv("ONUI_TMP_DIR", str(tmp_path / "tmp"))

    settings = load_settings()

    assert settings.session_cookie_secure is True
    assert settings.allowed_origins == ("https://onui.ai.kr", "https://onuiai.kr")


def test_main_registers_oauth_and_cache_hooks():
    source = Path("main.py").read_text()

    assert "app.state.get_user_by_google_id = _get_user_by_google_id" in source
    assert "app.state.create_google_user = _create_google_user" in source
    assert "app.state.clear_user_cache = clear_user_cache" in source
    assert "allow_origins=list(settings.allowed_origins)" in source
