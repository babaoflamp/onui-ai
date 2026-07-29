import json
import logging
import os
import re
import sqlite3
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openai import OpenAI

try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    genai = None
    GENAI_AVAILABLE = False

from backend.config import load_settings
from backend import database as _database  # Load before backend.utils to avoid legacy circular imports.
from backend.services.learning_progress_service import LearningProgressService
from backend.services.ai_services import generate_pronunciation_feedback
from backend.services.speechpro_service import (
    find_precomputed_sentence,
    get_or_build_speechpro_precomputed_sentence,
    load_speechpro_precomputed_sentences,
)
from backend.services.tts_service import convert_audio_bytes_to_wav16
from backend.utils import (
    ROLE_CHOICES,
    ROLE_INSTRUCTOR,
    ROLE_LEARNER,
    ROLE_SYSTEM_ADMIN,
    active_sessions,
    check_and_consume_credits,
    clear_user_cache,
    create_session_token,
    get_session,
    get_user_by_id,
    hash_password,
    normalize_role,
    parse_session_token,
    verify_password,
)

from backend.routes.learning_progress import router as learning_progress_router
from backend.routes.tts import router as tts_router
from backend.routes.speechpro import router as speechpro_router
from backend.routes.roleplay import router as roleplay_router
from backend.routes.lms import router as lms_router
from backend.routes.auth import router as auth_router
from backend.routes.admin import router as admin_router
from backend.routes.user import router as user_router
from backend.routes.ai_services import router as ai_services_router
from backend.routes.stt import router as stt_router
from backend.routes.media import router as media_router
from backend.routes.content import router as content_router
from backend.routes.pages import router as pages_router

def setup_logging():
    logger = logging.getLogger("uvicorn.error")
    _logs_dir = Path("logs")
    _logs_dir.mkdir(exist_ok=True)
    _fh = TimedRotatingFileHandler(
        _logs_dir / "detailed.log",
        when="midnight", interval=1, backupCount=14, encoding="utf-8",
    )
    _fh.suffix = ""
    _fh.namer = lambda n: str(Path(n).parent / (Path(n).name.replace("detailed.log.", "") + "-detailed.log"))
    _fh.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    _fh.setLevel(logging.INFO)
    
    # Avoid adding duplicate handlers if setup_logging is called multiple times
    if not any(isinstance(h, TimedRotatingFileHandler) for h in logger.handlers):
        logger.addHandler(_fh)
    return logger

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _get_user_by_email(db_path: str, email: str) -> dict | None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT id, email, nickname, password_hash, is_admin, role
            FROM users
            WHERE email = ?
            """,
            ((email or "").strip().lower(),),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _get_user_by_nickname(db_path: str, nickname: str) -> dict | None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT id, email, nickname, password_hash, is_admin, role
            FROM users
            WHERE nickname = ?
            """,
            ((nickname or "").strip(),),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _get_user_by_google_id(db_path: str, google_id: str) -> dict | None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT id, email, nickname, password_hash, is_admin, role
            FROM users
            WHERE google_id = ?
            """,
            (google_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _create_google_user(db_path: str, email: str, nickname: str, google_id: str) -> dict:
    clean_email = (email or "").strip().lower()
    clean_nickname = (nickname or clean_email.split("@")[0]).strip()
    if not clean_email or not EMAIL_REGEX.match(clean_email):
        raise HTTPException(status_code=400, detail="Google 계정 이메일이 올바르지 않습니다.")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            """
            INSERT INTO users (email, nickname, google_id, created_at, role)
            VALUES (?, ?, ?, ?, ?)
            """,
            (clean_email, clean_nickname, google_id, datetime.utcnow().isoformat(), ROLE_LEARNER),
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT id, email, nickname, password_hash, is_admin, role
            FROM users
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def _store_user_signup(db_path: str, payload: dict) -> dict:
    email = (payload.get("email") or "").strip().lower()
    nickname = (payload.get("nickname") or "").strip()
    password = payload.get("password") or ""
    if not (email and EMAIL_REGEX.match(email) and nickname and len(password) >= 8):
        raise HTTPException(status_code=400, detail="입력값이 올바르지 않습니다.")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO users (email, nickname, password_hash, created_at, role)
            VALUES (?, ?, ?, ?, ?)
            """,
            (email, nickname, hash_password(password), datetime.utcnow().isoformat(), ROLE_LEARNER),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")
    finally:
        conn.close()
    clear_user_cache()
    return {"email": email, "nickname": nickname}


def _require_authenticated_user(db_path: str, request: Request) -> dict:
    session = get_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="토큰이 없습니다.")
    user = get_user_by_id(db_path, session["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return user


def _redirect_if_unauthenticated(db_path: str, request: Request):
    try:
        _require_authenticated_user(db_path, request)
        return None
    except HTTPException:
        return RedirectResponse(url="/login")


def _get_word_score_history(db_path: str, user_id: int, limit: int = 3) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT word_id, score, created_at
            FROM word_score_history
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _get_sentence_score_history(db_path: str, user_id: int, limit: int = 3) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT sentence_id, score, created_at
            FROM sentence_score_history
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _build_gemini_client(api_key: str | None, logger: logging.Logger, *, live: bool = False):
    if not api_key or not GENAI_AVAILABLE:
        return None
    try:
        if live:
            return genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})
        return genai.Client(api_key=api_key)
    except Exception as exc:
        logger.error("[Config] Gemini client initialization failed: %s", exc)
        return None


def create_app() -> FastAPI:
    # 1. Load settings and setup logging
    settings = load_settings()
    logger = setup_logging()
    
    # 2. Initialize FastAPI app
    app = FastAPI(title="OAI Korean Learning")
    
    # Setup App State
    db_path = str(settings.db_path)
    templates = Jinja2Templates(directory="templates")
    templates.env.globals["CLARITY_PROJECT_ID"] = settings.clarity_project_id

    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    gemini_client = _build_gemini_client(settings.gemini_api_key, logger)
    gemini_live_client = _build_gemini_client(settings.gemini_api_key, logger, live=True)
    openai_client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    app.state.settings = settings
    app.state.templates = templates
    app.state.db_path = db_path
    app.state.tmp_dir = settings.app_tmp_dir
    app.state.app_tmp_dir = str(settings.app_tmp_dir)
    app.state.logger = logger
    app.state.learning_service = LearningProgressService()

    app.state.require_authenticated_user = lambda request: _require_authenticated_user(db_path, request)
    app.state.redirect_if_unauthenticated = lambda request: _redirect_if_unauthenticated(db_path, request)
    app.state.get_user_by_email = lambda email: _get_user_by_email(db_path, email)
    app.state.get_user_by_nickname = lambda nickname: _get_user_by_nickname(db_path, nickname)
    app.state.get_user_by_google_id = lambda google_id: _get_user_by_google_id(db_path, google_id)
    app.state.create_google_user = lambda email, nickname, google_id: _create_google_user(db_path, email, nickname, google_id)
    app.state.store_user_signup = lambda payload: _store_user_signup(db_path, payload)
    app.state.verify_password = verify_password
    app.state.create_session_token = create_session_token
    app.state.parse_session_token = parse_session_token
    app.state.extract_session_from_request = get_session
    app.state.active_sessions = active_sessions
    app.state.clear_user_cache = clear_user_cache
    app.state.normalize_role = normalize_role
    app.state.role_instructor = ROLE_INSTRUCTOR
    app.state.role_system_admin = ROLE_SYSTEM_ADMIN
    app.state.role_choices = ROLE_CHOICES
    app.state.oauth = oauth
    app.state.session_expiry_seconds = settings.session_expiry_seconds
    app.state.session_cookie_secure = settings.session_cookie_secure

    app.state.daily_credits = settings.daily_credits
    app.state.credit_costs = settings.credit_costs
    app.state.check_and_consume_credits = check_and_consume_credits

    app.state.model_backend = settings.model_backend
    app.state.ollama_url = settings.ollama_url
    app.state.ollama_model = settings.ollama_model
    app.state.gemini_model = settings.gemini_model
    app.state.gemini_client = gemini_client
    app.state.gemini_live_client = gemini_live_client
    app.state.openai_model = settings.openai_model
    app.state.openai_client = openai_client
    app.state.openai_api_key = settings.openai_api_key
    app.state.stt_backend = settings.stt_backend

    app.state.tts_backend = settings.tts_backend
    app.state.openai_tts_model = settings.openai_tts_model
    app.state.openai_tts_voice = settings.openai_tts_voice
    app.state.openai_tts_format = settings.openai_tts_format
    app.state.google_tts_language = settings.google_tts_language
    app.state.google_tts_voice = settings.google_tts_voice
    app.state.google_tts_audio_encoding = settings.google_tts_audio_encoding
    app.state.gemini_tts_model = settings.gemini_tts_model
    app.state.gemini_tts_voice = settings.gemini_tts_voice
    app.state.gemini_tts_mime = settings.gemini_tts_mime

    app.state.load_speechpro_precomputed_sentences = load_speechpro_precomputed_sentences
    app.state.find_precomputed_sentence = find_precomputed_sentence
    app.state.get_or_build_speechpro_precomputed_sentence = get_or_build_speechpro_precomputed_sentence
    app.state.convert_audio_bytes_to_wav16 = convert_audio_bytes_to_wav16
    app.state.generate_pronunciation_feedback = generate_pronunciation_feedback
    app.state.get_word_score_history = lambda user_id, limit=3: _get_word_score_history(db_path, user_id, limit)
    app.state.get_sentence_score_history = lambda user_id, limit=3: _get_sentence_score_history(db_path, user_id, limit)
    app.state.find_vocab_id_by_word = lambda word: None

    # 3. Mount static files
    app.mount("/static", StaticFiles(directory="static"), name="static")
    app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

    # 4. Setup CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 5. Register Routers
    app.include_router(learning_progress_router)
    app.include_router(tts_router)
    app.include_router(speechpro_router)
    app.include_router(roleplay_router)
    app.include_router(lms_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(user_router)
    app.include_router(ai_services_router)
    app.include_router(stt_router)
    app.include_router(media_router)
    app.include_router(content_router)
    app.include_router(pages_router)
    
    logger.info("FastAPI application initialized.")
    return app
