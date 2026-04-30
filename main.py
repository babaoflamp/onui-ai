import os
import io
import shutil
import csv
import sqlite3
import hashlib
import hmac
import logging
from logging.handlers import TimedRotatingFileHandler
from functools import lru_cache
from typing import Optional, Dict, List, Any
from pathlib import Path
from datetime import datetime, timedelta
import threading
import time
import uuid
import json
import re
import subprocess
import wave
import base64
import tempfile

from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import (
    JSONResponse,
    Response,
    RedirectResponse,
    FileResponse,
    StreamingResponse,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from authlib.integrations.starlette_client import OAuth
from openai import OpenAI
try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
from dotenv import load_dotenv
import requests
import uvicorn
import asyncio

# Consolidated utilities import
from backend.utils import (
    get_current_user,
    get_current_admin_user,
    get_optional_user,
    get_user_by_id,
    get_session,
    create_session_token,
    parse_session_token,
    hash_password,
    verify_password,
    load_json_data as load_json_data_utils,
    get_user_credits,
    check_and_consume_credits,
    romanize_korean,
    parse_model_output,
    ensure_wav_16k_mono,
    transcribe_with_vosk,
    active_sessions,
    normalize_role,
    ROLE_LEARNER,
    ROLE_INSTRUCTOR,
    ROLE_SYSTEM_ADMIN,
    ROLE_CHOICES,
    _get_state
)
from backend.services.learning_progress_service import LearningProgressService
from backend.services.speechpro_service import (
    call_speechpro_gtp,
    call_speechpro_model,
    call_speechpro_score,
    normalize_spaces,
    ScoreResult
)

# ==========================================
# 기본 설정 및 경로
# ==========================================
load_dotenv(override=True)
DB_PATH = Path("data/users.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
APP_TMP_DIR = Path(os.getenv("ONUI_TMP_DIR", "data/tmp"))
APP_TMP_DIR.mkdir(parents=True, exist_ok=True)

# 환경 변수 설정
os.environ["TMPDIR"] = str(APP_TMP_DIR)
os.environ["TEMP"] = str(APP_TMP_DIR)
os.environ["TMP"] = str(APP_TMP_DIR)
tempfile.tempdir = str(APP_TMP_DIR)

# 전역 객체
app = FastAPI(title="Onui AI Korean Learning")
logger = logging.getLogger("uvicorn.error")

# Write application logs to logs/detailed.log (daily rotation, 14-day retention)
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
if not any(isinstance(h, TimedRotatingFileHandler) for h in logger.handlers):
    logger.addHandler(_fh)

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# 모델/TTS 설정
MODEL_BACKEND = os.getenv("MODEL_BACKEND", "gemini")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "exaone")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
TTS_BACKEND = os.getenv("TTS_BACKEND", "gemini")
SESSION_EXPIRY_SECONDS = int(os.getenv("SESSION_EXPIRY_SECONDS", str(4 * 60 * 60)))
DAILY_CREDITS = int(os.getenv("DAILY_CREDITS", "100"))
CREDIT_COSTS = {"lesson": 3, "image": 10, "quiz": 2, "chat": 2, "tts": 1}

# TTS Configuration
GOOGLE_TTS_LANGUAGE = os.getenv("GOOGLE_TTS_LANGUAGE", "ko-KR")
GOOGLE_TTS_VOICE = os.getenv("GOOGLE_TTS_VOICE", "ko-KR-Standard-A")
GOOGLE_TTS_AUDIO_ENCODING = os.getenv("GOOGLE_TTS_AUDIO_ENCODING", "MP3")
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "tts-1")
OPENAI_TTS_VOICE = os.getenv("OPENAI_TTS_VOICE", "alloy")
OPENAI_TTS_FORMAT = os.getenv("OPENAI_TTS_FORMAT", "mp3")
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-1.5-flash")
GEMINI_TTS_MIME = os.getenv("GEMINI_TTS_MIME", "audio/wav")
TTS_CACHE_DIR = Path(os.getenv("TTS_CACHE_DIR", "data/tts_cache"))
TTS_CACHE_MAX = int(os.getenv("TTS_CACHE_MAX", "500"))
TTS_CACHE = {}

# OpenAI Client
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Gemini Client
gemini_client = None
gemini_live_client = None
if GEMINI_API_KEY and GENAI_AVAILABLE:
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        gemini_live_client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options={"api_version": "v1alpha"},
        )
        logger.info("[Config] Gemini clients initialized")
    except Exception as e:
        logger.error(f"[Config] Gemini Client initialization failed: {e}")

# OAuth
oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

# ==========================================
# 헬퍼 함수 및 데이터베이스 초기화
# ==========================================
def _init_user_db():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE, nickname TEXT, password_hash TEXT, google_id TEXT,
                native_lang TEXT, affiliation TEXT, time_pref TEXT, interests TEXT,
                goal TEXT, exam_level TEXT, reason TEXT, style TEXT, created_at TEXT,
                is_admin INTEGER DEFAULT 0, role TEXT DEFAULT 'learner',
                credits_used INTEGER DEFAULT 0, credits_reset_date TEXT
            )
        """)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sentence_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                sentence_id TEXT NOT NULL, sentence_text TEXT, level TEXT,
                score_first REAL, score_best REAL, score_latest REAL,
                accuracy_first REAL, accuracy_best REAL, accuracy_latest REAL,
                completeness_latest REAL, fluency_accuracy_latest REAL,
                attempt_count INTEGER DEFAULT 1, term_id TEXT DEFAULT '2026-1',
                device_type TEXT, ui_lang TEXT DEFAULT 'en', last_attempted_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_sentence_scores_user_sentence ON sentence_scores(user_id, sentence_id);
            CREATE TABLE IF NOT EXISTS word_score_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                word_id TEXT NOT NULL, score INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_word_score_user_word ON word_score_history(user_id, word_id, created_at);
            CREATE TABLE IF NOT EXISTS user_voice_recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, sentence_id TEXT,
                file_path TEXT, score REAL, created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
    finally:
        conn.close()

def _get_user_by_id(user_id: int) -> dict:
    return get_user_by_id(str(DB_PATH), user_id)

def _get_user_by_email(email: str) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT id, email, nickname, password_hash, is_admin, role FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
    conn.close()
    return dict(row) if row else None

def _get_user_by_nickname(nickname: str) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT id, email, nickname, password_hash, is_admin, role FROM users WHERE nickname=?", (nickname.strip(),)).fetchone()
    conn.close()
    return dict(row) if row else None

def _store_user_signup(payload: dict) -> dict:
    email = (payload.get("email") or "").strip().lower()
    nickname = (payload.get("nickname") or "").strip()
    password = payload.get("password") or ""
    if not (email and EMAIL_REGEX.match(email) and nickname and len(password) >= 8):
        raise HTTPException(status_code=400, detail="입력값이 올바르지 않습니다.")
    
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO users (email, nickname, password_hash, created_at, role) VALUES (?,?,?,?,?)",
                     (email, nickname, hash_password(password), datetime.utcnow().isoformat(), ROLE_LEARNER))
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")
    finally: conn.close()
    return {"email": email, "nickname": nickname}

def _require_authenticated_user(request: Request) -> dict:
    session = get_session(request)
    if not session: raise HTTPException(status_code=401, detail="토큰이 없습니다.")
    user = _get_user_by_id(session["user_id"])
    if not user: raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return user

def _redirect_if_unauthenticated(request: Request):
    try: _require_authenticated_user(request); return None
    except HTTPException: return RedirectResponse(url="/login")

def _get_word_score_history(user_id: int, word_id: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute("SELECT score, created_at FROM word_score_history WHERE user_id=? AND word_id=? ORDER BY created_at DESC", (user_id, word_id)).fetchall()
        return [{"score": r[0], "date": r[1]} for r in rows]
    finally: conn.close()

def _get_sentence_score_history(user_id: int, sentence_id: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute("SELECT score_latest, last_attempted_at FROM sentence_scores WHERE user_id=? AND sentence_id=? ORDER BY last_attempted_at DESC", (user_id, sentence_id)).fetchall()
        return [{"score": r[0], "date": r[1]} for r in rows]
    finally: conn.close()

@lru_cache(maxsize=32)
def load_json_data(filename):
    try:
        with open(f"data/{filename}", "r", encoding="utf-8") as f: return json.load(f)
    except Exception: return []

# SpeechPro Logic
_SPEECHPRO_SENTENCES_CACHE = None
_SPEECHPRO_RUNTIME_PRECOMPUTED_CACHE = {}
_SPEECHPRO_RUNTIME_PRECOMPUTED_LOCK = threading.Lock()

def load_speechpro_precomputed_sentences():
    global _SPEECHPRO_SENTENCES_CACHE
    if _SPEECHPRO_SENTENCES_CACHE is not None: return _SPEECHPRO_SENTENCES_CACHE
    path = "data/sp_ko_questions.csv"
    sentences = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    txt = normalize_spaces(row.get("sentence", ""))
                    sentences.append({
                        "id": 1000 + int(row.get("ko_id", 0)),
                        "sentenceKr": txt, "level": row.get("level", "초급"),
                        "syll_ltrs": row.get("syll_ltrs", ""), "syll_phns": row.get("syll_phns", ""),
                        "fst": row.get("fst", ""), "source": "precomputed"
                    })
        except Exception: pass
    _SPEECHPRO_SENTENCES_CACHE = sentences
    return sentences

def find_precomputed_sentence(text: str):
    norm = normalize_spaces(text or "")
    for s in load_speechpro_precomputed_sentences():
        if normalize_spaces(s.get("sentenceKr", "")) == norm: return s
    return None

def get_or_build_speechpro_precomputed_sentence(text: str):
    norm = normalize_spaces(text or "")
    if not norm: return None
    preset = find_precomputed_sentence(norm)
    if preset and preset.get("fst"): return preset
    with _SPEECHPRO_RUNTIME_PRECOMPUTED_LOCK:
        if norm in _SPEECHPRO_RUNTIME_PRECOMPUTED_CACHE: return _SPEECHPRO_RUNTIME_PRECOMPUTED_CACHE[norm]
    try:
        rid = f"pre_{int(time.time())}"
        gtp = call_speechpro_gtp(norm, rid)
        if gtp.error_code != 0: return None
        mdl = call_speechpro_model(norm, gtp.syll_ltrs, gtp.syll_phns, rid)
        if mdl.error_code != 0: return None
        built = {"sentenceKr": norm, "syll_ltrs": mdl.syll_ltrs, "syll_phns": mdl.syll_phns, "fst": mdl.fst, "source": "runtime"}
        with _SPEECHPRO_RUNTIME_PRECOMPUTED_LOCK: _SPEECHPRO_RUNTIME_PRECOMPUTED_CACHE[norm] = built
        return built
    except Exception: return None

async def _generate_pronunciation_feedback(text: str, score_result, ui_lang: str = "en") -> str:
    text = normalize_spaces(text or "")
    if not text:
        raise ValueError("text is required")
    if score_result is None:
        raise ValueError("score_result is required")

    score_value = round(float(getattr(score_result, "score", 0) or 0))
    details = getattr(score_result, "details", {}) or {}
    detail_json = json.dumps(details, ensure_ascii=False)

    prompt = f"""
You are a kind Korean teacher giving pronunciation feedback to a foreign learner.
Explain the pronunciation result in clear, natural English, as if you are tutoring the learner one-on-one.

Response rules:
- Write in English only, regardless of the UI language.
- Keep it to 3 short sentences maximum.
- Sound like a supportive Korean teacher: warm, clear, and practical.
- In the first sentence, give a brief overall evaluation of the learner's pronunciation.
- In the next sentence, explain the 1 or 2 most important pronunciation issues in simple English.
- In the final sentence, give one concrete practice tip the learner can try immediately.
- If helpful, mention a Korean syllable or sound pattern, but explain it in easy English.
- Do not list raw scores or JSON fields directly.
- Avoid emojis, exaggerated praise, and generic filler.

Sentence:
{text}

Score:
{score_value}

Detailed result (JSON):
{detail_json}
""".strip()

    backend = (MODEL_BACKEND or "").strip().lower()

    if backend == "gemini":
        if not gemini_client:
            raise RuntimeError("Gemini client not initialized")
        resp = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        out = (getattr(resp, "text", None) or "").strip()
    elif backend == "openai":
        if not client:
            raise RuntimeError("OpenAI client not initialized")
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
        )
        out = (resp.choices[0].message.content or "").strip()
    elif backend == "ollama":
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.4},
        }
        resp = requests.post(
            f"{OLLAMA_URL.rstrip('/')}/api/generate",
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        out = (resp.json().get("response") or "").strip()
    else:
        raise RuntimeError(f"Unsupported model backend: {MODEL_BACKEND}")

    if not out:
        raise RuntimeError("AI feedback response was empty")
    return out


def _extract_gemini_audio(result: dict) -> dict:
    candidates = result.get("candidates") or []
    for cand in candidates:
        parts = cand.get("content", {}).get("parts", []) or []
        for part in parts:
            inline = part.get("inlineData") or part.get("inline_data") or {}
            data = inline.get("data")
            mime = inline.get("mimeType") or inline.get("mime_type")
            if data:
                return {
                    "audio_data": base64.b64decode(data),
                    "content_type": mime or GEMINI_TTS_MIME,
                }
    raise RuntimeError("Gemini TTS response did not include audio data")


def _tts_cache_key(text: str, model: str, backend: str = "gemini") -> str:
    raw = f"{backend}:{model}:{text}".encode("utf-8")
    return hashlib.md5(raw).hexdigest()


def _get_tts_cache(key: str) -> Optional[Dict]:
    cached = TTS_CACHE.get(key)
    if cached:
        return cached
    meta_path = TTS_CACHE_DIR / f"{key}.json"
    audio_path = TTS_CACHE_DIR / f"{key}.bin"
    if not meta_path.exists() or not audio_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        audio_bytes = audio_path.read_bytes()
        cached = {
            "content_type": meta.get("content_type") or "application/octet-stream",
            "audio_data": audio_bytes,
        }
        TTS_CACHE[key] = cached
        return cached
    except Exception:
        return None


def _set_tts_cache(key: str, content_type: str, audio_data: bytes) -> None:
    if len(TTS_CACHE) >= TTS_CACHE_MAX:
        TTS_CACHE.clear()
    try:
        TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (TTS_CACHE_DIR / f"{key}.json").write_text(
            json.dumps({"content_type": content_type}, ensure_ascii=True),
            encoding="utf-8",
        )
        (TTS_CACHE_DIR / f"{key}.bin").write_bytes(audio_data)
        TTS_CACHE[key] = {"content_type": content_type, "audio_data": audio_data}
    except Exception:
        return


def _amplify_pcm16(
    pcm_data: bytes, target_peak: float = 1.0, max_gain: float = None
) -> bytes:
    import struct

    if not pcm_data:
        return pcm_data

    sample_count = len(pcm_data) // 2
    if sample_count == 0:
        return pcm_data

    samples = struct.unpack("<" + "h" * sample_count, pcm_data)
    peak = max((abs(s) for s in samples), default=0)
    if peak == 0:
        return pcm_data

    target = int(32767 * target_peak)
    gain = target / peak
    if max_gain is not None:
        gain = min(gain, max_gain)
    if gain <= 1.0:
        return pcm_data

    amplified = [max(-32768, min(32767, int(s * gain))) for s in samples]
    return struct.pack("<" + "h" * sample_count, *amplified)


def _pcm16_to_wav(
    pcm_data: bytes, sample_rate: int = 24000, channels: int = 1
) -> bytes:
    import struct

    bits_per_sample = 16
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    data_size = len(pcm_data)
    riff_size = 36 + data_size

    header = b"".join(
        [
            b"RIFF",
            struct.pack("<I", riff_size),
            b"WAVE",
            b"fmt ",
            struct.pack("<I", 16),
            struct.pack("<H", 1),
            struct.pack("<H", channels),
            struct.pack("<I", sample_rate),
            struct.pack("<I", byte_rate),
            struct.pack("<H", block_align),
            struct.pack("<H", bits_per_sample),
            b"data",
            struct.pack("<I", data_size),
        ]
    )
    return header + pcm_data


def _call_gemini_tts_api(text: str, model: str = None) -> dict:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not configured")

    gemini_model = model or GEMINI_TTS_MODEL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={GEMINI_API_KEY}"
    prompts = [
        f"Speak the following Korean text aloud. Output audio only. Transcript: {text}",
        f"Generate speech audio only for the following transcript:\n{text}",
    ]

    last_error = None
    for prompt in prompts:
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["AUDIO"]},
        }
        try:
            resp = requests.post(url, json=payload, timeout=60)
        except requests.exceptions.RequestException as e:
            last_error = RuntimeError(f"Failed to connect to Gemini API: {e}")
            continue

        if not resp.ok:
            error_text = resp.text.strip()
            if len(error_text) > 1000:
                error_text = error_text[:1000] + "...(truncated)"
            last_error = RuntimeError(
                f"Gemini TTS API error {resp.status_code} for model {gemini_model}: {error_text}"
            )
            continue

        try:
            return _extract_gemini_audio(resp.json())
        except Exception as e:
            last_error = e

    raise RuntimeError(str(last_error) if last_error else "Gemini TTS failed")

def _convert_audio_bytes_to_wav16(audio_bytes: bytes) -> bytes:
    if not audio_bytes: raise ValueError("audio bytes empty")
    with tempfile.TemporaryDirectory(dir=str(APP_TMP_DIR)) as tmpdir:
        src, dst = os.path.join(tmpdir, "in.bin"), os.path.join(tmpdir, "out.wav")
        with open(src, "wb") as f: f.write(audio_bytes)
        try: ensure_wav_16k_mono(src, dst)
        except Exception: raise RuntimeError("ffmpeg failed")
        with open(dst, "rb") as f: return f.read()

# ==========================================
# 미들웨어 및 로깅
# ==========================================
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        skip = path.startswith("/static") or path.startswith("/uploads")
        ip = request.client.host if request.client else "-"
        user_info = "Guest"
        if not skip:
            session = get_session(request)
            if session:
                user = _get_user_by_id(session["user_id"])
                if user: user_info = f"{user['nickname']} ({user['email']})"
        try:
            response = await call_next(request)
            if not skip:
                logger.info(f"[REQUEST] {request.method} {path} | User: {user_info} | IP: {ip} | Status: {response.status_code}")
            return response
        except Exception as e:
            logger.error(f"[ERROR] {path} - {str(e)}", exc_info=True)
            return JSONResponse(status_code=500, content={"error": "Internal Server Error"})

app.add_middleware(LoggingMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# ==========================================
# 앱 상태 및 라우터
# ==========================================
templates = Jinja2Templates(directory="templates")
templates.env.globals["CLARITY_PROJECT_ID"] = os.getenv("CLARITY_PROJECT_ID", "")
app.state.templates = templates
learning_service = LearningProgressService()
app.state.learning_service = learning_service
app.state.db_path = str(DB_PATH)
app.state.require_authenticated_user = _require_authenticated_user
app.state.redirect_if_unauthenticated = _redirect_if_unauthenticated
app.state.normalize_role = normalize_role
app.state.role_instructor = ROLE_INSTRUCTOR
app.state.role_system_admin = ROLE_SYSTEM_ADMIN
app.state.role_choices = ROLE_CHOICES
app.state.oauth = oauth
app.state.session_expiry_seconds = SESSION_EXPIRY_SECONDS
app.state.check_and_consume_credits = check_and_consume_credits
app.state.credit_costs = CREDIT_COSTS
app.state.active_sessions = active_sessions
app.state.logger = logger
app.state.model_backend = MODEL_BACKEND
app.state.ollama_model = OLLAMA_MODEL
app.state.gemini_model = GEMINI_MODEL
app.state.gemini_client = gemini_client
app.state.gemini_live_client = gemini_live_client
app.state.openai_model = OPENAI_MODEL
app.state.openai_client = client
app.state.openai_api_key = OPENAI_API_KEY
app.state.tts_backend = TTS_BACKEND
app.state.openai_tts_model = OPENAI_TTS_MODEL
app.state.openai_tts_voice = OPENAI_TTS_VOICE
app.state.openai_tts_format = OPENAI_TTS_FORMAT
app.state.gemini_tts_model = GEMINI_TTS_MODEL
app.state.gemini_tts_mime = GEMINI_TTS_MIME
app.state.call_gemini_tts_api = _call_gemini_tts_api
app.state.tts_cache_key = _tts_cache_key
app.state.get_tts_cache = _get_tts_cache
app.state.set_tts_cache = _set_tts_cache
app.state.amplify_pcm16 = _amplify_pcm16
app.state.pcm16_to_wav = _pcm16_to_wav
app.state.stt_backend = os.getenv("STT_BACKEND", "openai")

# Missing Auth Hooks
app.state.get_user_by_email = _get_user_by_email
app.state.get_user_by_nickname = _get_user_by_nickname
app.state.store_user_signup = _store_user_signup
app.state.verify_password = verify_password
app.state.create_session_token = create_session_token
app.state.parse_session_token = parse_session_token
app.state.extract_session_from_request = get_session

# SpeechPro hooks
app.state.load_speechpro_precomputed_sentences = load_speechpro_precomputed_sentences
app.state.find_precomputed_sentence = find_precomputed_sentence
app.state.get_or_build_speechpro_precomputed_sentence = get_or_build_speechpro_precomputed_sentence
app.state.generate_pronunciation_feedback = _generate_pronunciation_feedback
app.state.convert_audio_bytes_to_wav16 = _convert_audio_bytes_to_wav16
app.state.get_word_score_history = _get_word_score_history
app.state.get_sentence_score_history = _get_sentence_score_history
app.state.find_vocab_id_by_word = lambda w: None

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

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

@app.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    return FileResponse("static/robots.txt", media_type="text/plain")

@app.on_event("startup")
def startup_event():
    _init_user_db()
    logger.info("Application started.")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=9002, reload=True)
