from backend.config import load_settings


def test_load_settings_reads_environment(monkeypatch, tmp_path):
    db_path = tmp_path / "custom.db"
    tmp_dir = tmp_path / "tmp"
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("ONUI_TMP_DIR", str(tmp_dir))
    monkeypatch.setenv("MODEL_BACKEND", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.setenv("TTS_CACHE_MAX", "12")

    settings = load_settings()

    assert settings.db_path == db_path
    assert settings.db_path.parent.exists()
    assert settings.app_tmp_dir == tmp_dir
    assert settings.app_tmp_dir.exists()
    assert settings.model_backend == "openai"
    assert settings.openai_model == "gpt-test"
    assert settings.tts_cache_max == 12
    assert settings.credit_costs["tts"] == 1
