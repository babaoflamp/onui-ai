from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_csv(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development").strip().lower())
    db_path: Path = field(default_factory=lambda: Path(os.getenv("DB_PATH", "data/users.db")))
    app_tmp_dir: Path = field(default_factory=lambda: Path(os.getenv("ONUI_TMP_DIR", "data/tmp")))
    allowed_origins: tuple[str, ...] = field(default_factory=lambda: _parse_csv(
        os.getenv("ALLOWED_ORIGINS"),
        (
            "http://localhost:9002",
            "http://127.0.0.1:9002",
            "https://opportunity.ai.kr",
            "https://onui.ai.kr",
        ),
    ))

    model_backend: str = field(default_factory=lambda: os.getenv("MODEL_BACKEND", "gemini"))
    ollama_url: str = field(default_factory=lambda: os.getenv("OLLAMA_URL", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "exaone"))
    gemini_api_key: str | None = field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))
    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    tts_backend: str = field(default_factory=lambda: os.getenv("TTS_BACKEND", "gemini"))
    google_tts_language: str = field(default_factory=lambda: os.getenv("GOOGLE_TTS_LANGUAGE", "ko-KR"))
    google_tts_voice: str = field(default_factory=lambda: os.getenv("GOOGLE_TTS_VOICE", "ko-KR-Standard-A"))
    google_tts_audio_encoding: str = field(default_factory=lambda: os.getenv("GOOGLE_TTS_AUDIO_ENCODING", "MP3"))
    openai_tts_model: str = field(default_factory=lambda: os.getenv("OPENAI_TTS_MODEL", "tts-1"))
    openai_tts_voice: str = field(default_factory=lambda: os.getenv("OPENAI_TTS_VOICE", "alloy"))
    openai_tts_format: str = field(default_factory=lambda: os.getenv("OPENAI_TTS_FORMAT", "mp3"))
    gemini_tts_model: str = field(default_factory=lambda: os.getenv("GEMINI_TTS_MODEL", "gemini-1.5-flash"))
    gemini_tts_voice: str = field(default_factory=lambda: os.getenv("GEMINI_TTS_VOICE", "Aoede"))
    gemini_tts_mime: str = field(default_factory=lambda: os.getenv("GEMINI_TTS_MIME", "audio/wav"))
    tts_cache_dir: Path = field(default_factory=lambda: Path(os.getenv("TTS_CACHE_DIR", "data/tts_cache")))
    tts_cache_max: int = field(default_factory=lambda: int(os.getenv("TTS_CACHE_MAX", "500")))

    session_expiry_seconds: int = field(default_factory=lambda: int(os.getenv("SESSION_EXPIRY_SECONDS", str(4 * 60 * 60))))
    session_cookie_secure: bool = field(default_factory=lambda: _parse_bool(os.getenv("SESSION_COOKIE_SECURE"), False))
    secret_key: str | None = field(default_factory=lambda: os.getenv("SECRET_KEY") or None)
    daily_credits: int = field(default_factory=lambda: int(os.getenv("DAILY_CREDITS", "100")))
    credit_costs: dict[str, int] = field(default_factory=lambda: {
        "lesson": 3,
        "image": 10,
        "quiz": 2,
        "chat": 2,
        "tts": 1,
        "voice": 5,
    })

    stt_backend: str = field(default_factory=lambda: os.getenv("STT_BACKEND", "openai"))
    clarity_project_id: str = field(default_factory=lambda: os.getenv("CLARITY_PROJECT_ID", ""))
    google_client_id: str | None = field(default_factory=lambda: os.getenv("GOOGLE_CLIENT_ID"))
    google_client_secret: str | None = field(default_factory=lambda: os.getenv("GOOGLE_CLIENT_SECRET"))


def load_settings() -> Settings:
    settings = Settings()
    if settings.app_env == "production" and not settings.secret_key:
        raise RuntimeError("SECRET_KEY must be set when APP_ENV=production")
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.app_tmp_dir.mkdir(parents=True, exist_ok=True)
    return settings
