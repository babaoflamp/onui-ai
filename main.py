import os
import io
import shutil
import csv
import sqlite3
from datetime import timedelta
import hashlib
import hmac
import logging
from logging.handlers import TimedRotatingFileHandler
from functools import lru_cache
from typing import Optional, Dict, List
from pathlib import Path
from datetime import datetime
import threading
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
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from openai import OpenAI
from dotenv import load_dotenv
from difflib import SequenceMatcher
import requests
import json
import re
import uuid
import uvicorn
import asyncio
import subprocess
import wave
import base64
import tempfile
from pathlib import Path
import time


# Module-level cache for transcripts (loaded once on first request)
_tube_transcripts_cache: dict | None = None


# Pydantic model for adding a new OnuiTube video
class OnuiTubeVideo(BaseModel):
    id: str
    title: str
    description: str
    level: str
    video_url: str = ""
    poster_url: str = ""
    duration: int = 0


try:
    from google import genai

    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False
    genai = None

try:
    from google.cloud import speech

    GOOGLE_SPEECH_AVAILABLE = True
except ImportError:
    GOOGLE_SPEECH_AVAILABLE = False
    speech = None

try:
    from google.cloud import texttospeech

    GOOGLE_TTS_AVAILABLE = True
except ImportError:
    GOOGLE_TTS_AVAILABLE = False
    texttospeech = None

# SpeechPro 서비스 임포트
from backend.services.speechpro_service import (
    call_speechpro_gtp,
    call_speechpro_model,
    call_speechpro_score,
    speechpro_full_workflow,
    ScoreResult,
    get_speechpro_url,
    set_speechpro_url,
    normalize_spaces,
)

# 학습 진도 서비스 임포트
from backend.services.learning_progress_service import LearningProgressService

# FluencyPro 서비스 임포트
from backend.services.fluencypro_service import (
    call_fluencypro_analyze,
    parse_fluency_output,
)

# Dictionary API service import
from backend.services.krdict_service import search_krdict

# DALL-E 서비스 임포트
from backend.services.dalle_service import (
    generate_image_dall_e,
    generate_image_gemini,
    enhance_prompt_for_korean_learning,
)

# Try to provide a server-side romanization fallback for Korean -> Latin
# We will try to import a lightweight romanizer if available. If not,
# `romanize_korean` will be a no-op (returns original text) and we will
# instruct the operator to install `korean_romanizer` for better results.
try:
    from korean_romanizer.romanizer import Romanizer

    def romanize_korean(text: str) -> str:
        try:
            r = Romanizer(text)
            return r.romanize()
        except Exception:
            return text

    ROMANIZER_AVAILABLE = True
except Exception:
    # Basic built-in romanizer (Revised Romanization approximations)
    # This provides a best-effort Latin transcription of Hangul syllables
    # without requiring external packages. It is not perfect but works
    # for common phrases and will ensure the UI receives Latin text.
    L_TABLE = [
        "g",
        "kk",
        "n",
        "d",
        "tt",
        "r",
        "m",
        "b",
        "pp",
        "s",
        "ss",
        "",
        "j",
        "jj",
        "ch",
        "k",
        "t",
        "p",
        "h",
    ]
    V_TABLE = [
        "a",
        "ae",
        "ya",
        "yae",
        "eo",
        "e",
        "yeo",
        "ye",
        "o",
        "wa",
        "wae",
        "oe",
        "yo",
        "u",
        "wo",
        "we",
        "wi",
        "yu",
        "eu",
        "ui",
        "i",
    ]
    T_TABLE = [
        "",
        "k",
        "k",
        "ks",
        "n",
        "nj",
        "nh",
        "t",
        "l",
        "lg",
        "lm",
        "lb",
        "ls",
        "lt",
        "lp",
        "lh",
        "m",
        "p",
        "ps",
        "t",
        "t",
        "ng",
        "t",
        "ch",
        "k",
        "t",
        "p",
        "h",
    ]

    def _romanize_syllable(ch: str) -> str:
        code = ord(ch)
        # Hangul syllables range
        if code < 0xAC00 or code > 0xD7A3:
            return ch

        SIndex = code - 0xAC00
        TCount = 28
        VCount = 21
        NCount = VCount * TCount
        LIndex = SIndex // NCount
        VIndex = (SIndex % NCount) // TCount
        TIndex = SIndex % TCount

        initial = L_TABLE[LIndex]
        medial = V_TABLE[VIndex]
        final = T_TABLE[TIndex]

        return initial + medial + final

    def romanize_korean(text: str) -> str:
        try:
            return "".join(
                _romanize_syllable(ch) if 0xAC00 <= ord(ch) <= 0xD7A3 else ch
                for ch in text
            )
        except Exception:
            return text

    ROMANIZER_AVAILABLE = False

# ==========================================
# 설정: 환경변수에서 OpenAI API 키 로드
# ==========================================
load_dotenv(override=True)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# KRDIC API key (Korean Basic Dictionary)
KRDICT_API_KEY = os.getenv("KRDICT_API_KEY")

# YouTube Data API Key for CC video search
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# Backend selection: set MODEL_BACKEND to 'ollama', 'openai', or 'gemini'
MODEL_BACKEND = os.getenv("MODEL_BACKEND", "ollama")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "exaone3.5:2.4b")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

if GEMINI_API_KEY:
    print(f"[Config] Gemini API Key loaded (starts with {GEMINI_API_KEY[:4]}...)")
else:
    print("[Config] Gemini API Key NOT found in environment")

# Initialize Gemini client if available
gemini_client = None
gemini_live_client = None  # Separate client for Live API (requires v1alpha)
if GEMINI_API_KEY and GENAI_AVAILABLE:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    gemini_live_client = genai.Client(
        api_key=GEMINI_API_KEY,
        http_options={"api_version": "v1alpha"},
    )

# Initialize Google Cloud Speech client if available
google_speech_client = None
_google_speech_client_initialized = False


def _get_google_speech_client():
    """Lazy initialization of Google Cloud Speech client"""
    global google_speech_client, _google_speech_client_initialized

    if _google_speech_client_initialized:
        return google_speech_client

    _google_speech_client_initialized = True

    if not GOOGLE_SPEECH_AVAILABLE:
        logger.warning("[Google STT] google-cloud-speech package not installed")
        return None

    try:
        google_speech_client = speech.SpeechClient()
        logger.info("[Google STT] Client initialized successfully")
        return google_speech_client
    except Exception as e:
        logger.warning(
            "[Google STT] Failed to initialize client: %s (requires GOOGLE_APPLICATION_CREDENTIALS)",
            e,
        )
        return None


# Romanization mode: 'force' = always replace pronunciation with romanizer output;
# 'prefer' = keep model-provided Latin pronunciation if it looks valid (contains ASCII letters).
ROMANIZE_MODE = os.getenv("ROMANIZE_MODE", "force").lower()

# Gemini image model (optional override)
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.0-pro-exp-02-05")

# MzTTS Configuration
MZTTS_API_URL = os.getenv("MZTTS_API_URL", "http://112.220.79.218:56014")

# STT/TTS Backend
STT_BACKEND = os.getenv("STT_BACKEND", "openai" if OPENAI_API_KEY else "local")
TTS_BACKEND = os.getenv("TTS_BACKEND", "gemini")
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "tts-1")
OPENAI_TTS_VOICE = os.getenv("OPENAI_TTS_VOICE", "alloy")
OPENAI_TTS_FORMAT = os.getenv("OPENAI_TTS_FORMAT", "wav")
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", GEMINI_MODEL)
GEMINI_TTS_MIME = os.getenv("GEMINI_TTS_MIME", "audio/wav")
GOOGLE_TTS_LANGUAGE = os.getenv("GOOGLE_TTS_LANGUAGE", "en-US")
GOOGLE_TTS_VOICE = os.getenv("GOOGLE_TTS_VOICE", "en-US-Standard-C")
GOOGLE_TTS_AUDIO_ENCODING = os.getenv("GOOGLE_TTS_AUDIO_ENCODING", "MP3")
GOOGLE_TTS_SPEAKING_RATE = float(os.getenv("GOOGLE_TTS_SPEAKING_RATE", "1.0"))
GOOGLE_TTS_PITCH = float(os.getenv("GOOGLE_TTS_PITCH", "0.0"))
TTS_CACHE_DIR = Path(os.getenv("TTS_CACHE_DIR", "data/tts_cache"))
TTS_CACHE_MAX = int(os.getenv("TTS_CACHE_MAX", "500"))
TTS_PREWARM_ON_STARTUP = os.getenv("TTS_PREWARM_ON_STARTUP", "").lower() in (
    "1",
    "true",
    "yes",
)
SPEECHPRO_PREWARM_ON_STARTUP = os.getenv(
    "SPEECHPRO_PREWARM_ON_STARTUP", "true"
).lower() in ("1", "true", "yes")
TTS_CACHE = {}
WORD_IMAGE_CACHE_PATH = Path(
    os.getenv("WORD_IMAGE_CACHE_PATH", "data/word_image_cache.json")
)
CLARITY_PROJECT_ID = os.getenv("CLARITY_PROJECT_ID")

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    SECRET_KEY = os.urandom(24).hex()
    logging.warning(
        "[SECURITY] SECRET_KEY env var is not set. A random key was generated — "
        "all sessions will be invalidated on every restart. Set SECRET_KEY in .env for production."
    )

oauth = OAuth()
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


# Session management
SESSION_EXPIRY_SECONDS = 24 * 60 * 60  # 24 hours
active_sessions = {}  # {token: {"user_id": int, "email": str, "created_at": float, "is_admin": bool}}

# Role definitions
ROLE_LEARNER = "learner"
ROLE_INSTRUCTOR = "instructor"
ROLE_SYSTEM_ADMIN = "system_admin"
ROLE_CHOICES = {ROLE_LEARNER, ROLE_INSTRUCTOR, ROLE_SYSTEM_ADMIN}

# Daily credit limits
DAILY_CREDITS = int(os.getenv("DAILY_CREDITS", "50"))
CREDIT_COSTS = {
    "lesson": 3,
    "image": 10,
    "quiz": 2,
    "chat": 2,
    "tts": 1,
}


def _normalize_role(role: str, is_admin: bool = False) -> str:
    """Return a valid role, prioritizing system admin when is_admin is true."""
    if is_admin:
        return ROLE_SYSTEM_ADMIN
    if role in ROLE_CHOICES:
        return role
    return ROLE_LEARNER


def check_and_consume_credits(user_id: int, cost: int) -> dict:
    """Check if user has enough daily credits and consume them atomically.

    Resets the counter when the date changes (midnight local time).
    Returns {"ok": True, "remaining": N} on success,
            {"ok": False, "remaining": N} when insufficient.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT credits_used, credits_reset_date FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            conn.execute("ROLLBACK")
            return {"ok": False, "remaining": 0}
        credits_used, reset_date = row
        if reset_date != today:
            credits_used = 0
        remaining = DAILY_CREDITS - credits_used
        if remaining < cost:
            conn.execute("ROLLBACK")
            return {"ok": False, "remaining": max(remaining, 0)}
        conn.execute(
            "UPDATE users SET credits_used = ?, credits_reset_date = ? WHERE id = ?",
            (credits_used + cost, today, user_id),
        )
        conn.execute("COMMIT")
        return {"ok": True, "remaining": remaining - cost}
    except Exception as e:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        logger.error(f"[CREDITS] check_and_consume_credits error: {e}")
        return {"ok": False, "remaining": 0}
    finally:
        conn.close()


def _get_user_credits(user_id: int) -> dict:
    """Return current credit status without consuming any credits."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT credits_used, credits_reset_date FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return {"credits_used": 0, "remaining": DAILY_CREDITS, "daily_limit": DAILY_CREDITS}
        credits_used, reset_date = row
        if reset_date != today:
            credits_used = 0
        return {
            "credits_used": credits_used,
            "remaining": max(DAILY_CREDITS - credits_used, 0),
            "daily_limit": DAILY_CREDITS,
        }
    finally:
        conn.close()



def _list_ollama_models():
    """Return list of models from local Ollama server or raise."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/v1/models", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
    except Exception as e:
        raise RuntimeError(f"Failed to list Ollama models: {e}")


def _auto_select_ollama_model(preferred=None):
    """If OLLAMA_MODEL is unset or default, try to pick a preferred exaone model from the server."""
    global OLLAMA_MODEL
    try:
        models = _list_ollama_models()
    except Exception:
        return

    # Flatten ids
    ids = [m.get("id") for m in models if isinstance(m, dict) and m.get("id")]
    # If user already set a non-default model, keep it
    if OLLAMA_MODEL and OLLAMA_MODEL != "exaone":
        return

    # Preferred order
    prefer = preferred or [
        "exaone3.5:7.8b",
        "exaone3.5:2.4b",
        "exaone-deep:7.8b",
        "hf.co/LGAI-EXAONE/EXAONE-4.0-1.2B-GGUF:Q4_K_M",
        "exaone",
    ]

    for p in prefer:
        for mid in ids:
            if mid and mid.startswith(p):
                OLLAMA_MODEL = mid
                print(f"Auto-selected Ollama model: {OLLAMA_MODEL}")
                return


def _parse_model_output(text: str):
    """Try to extract JSON from model output.
    - First look for ```json ... ``` or ``` ... ``` code fences and parse the inside.
    - Then look for a JSON object substring and parse it.
    Returns parsed object or None.
    """
    if not text or not isinstance(text, str):
        return None

    # look for fenced code blocks
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    candidate = None
    if fence_match:
        candidate = fence_match.group(1).strip()
        try:
            return json.loads(candidate)
        except Exception:
            # continue to other heuristics
            pass

    # fallback: find first {...} JSON-like substring
    brace_match = re.search(r"(\{[\s\S]*\})", text)
    if brace_match:
        candidate = brace_match.group(1)
        try:
            return json.loads(candidate)
        except Exception:
            pass

    return None


def _ensure_wav_16k_mono(src_path: str, dst_path: str):
    """Use ffmpeg (must be installed) to convert audio to 16k mono WAV for VOSK."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        src_path,
        "-ar",
        "16000",
        "-ac",
        "1",
        dst_path,
    ]
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _convert_audio_bytes_to_wav16(audio_bytes: bytes) -> bytes:
    """Convert arbitrary audio bytes (webm/opus etc.) to 16k mono WAV via ffmpeg."""
    if not audio_bytes:
        raise ValueError("audio bytes empty")

    with tempfile.TemporaryDirectory(dir=str(APP_TMP_DIR)) as tmpdir:
        src_path = os.path.join(tmpdir, "input.bin")
        dst_path = os.path.join(tmpdir, "output.wav")

        with open(src_path, "wb") as f:
            f.write(audio_bytes)

        try:
            _ensure_wav_16k_mono(src_path, dst_path)
            with open(dst_path, "rb") as f:
                return f.read()
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"ffmpeg 변환 실패: {e}")


def _transcribe_with_vosk(wav_path: str, model_path: str) -> str:
    try:
        from vosk import Model, KaldiRecognizer
    except Exception as e:
        raise RuntimeError("VOSK package not available: " + str(e))

    if not os.path.exists(model_path):
        raise RuntimeError(f"VOSK model path not found: {model_path}")

    wf = wave.open(wav_path, "rb")
    if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 16000:
        raise RuntimeError("WAV file not in required format (16k mono 16-bit)")

    model = Model(model_path)
    rec = KaldiRecognizer(model, wf.getframerate())
    rec.SetWords(True)

    results = []
    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            j = json.loads(rec.Result())
            results.append(j.get("text", ""))
    # final
    j = json.loads(rec.FinalResult())
    results.append(j.get("text", ""))
    wf.close()
    return " ".join([r for r in results if r])


# ==========================================
# MzTTS Service Functions
# ==========================================


def _call_mztts_api(
    text: str,
    output_type: str = "file",
    speaker: int = None,
    tempo: float = None,
    pitch: float = None,
    gain: float = None,
) -> dict:
    """
    Call MzTTS API to generate Korean speech.

    Args:
        text: Korean text to synthesize
        output_type: "file" (direct WAV), "pcm" (base64), or "path" (file path)
        speaker: Speaker ID (0: Hanna - female voice)
        tempo: Speed (0.1-2.0, default 1.0)
        pitch: Pitch (0.1-2.0, default 1.0)
        gain: Volume (0.1-2.0, default 1.0)

    Returns:
        dict with response data or raises exception
    """
    # Use defaults if not specified
    if speaker is None:
        speaker = 0
    if tempo is None:
        tempo = 1.0
    if pitch is None:
        pitch = 1.0
    if gain is None:
        gain = 1.0

    # Validate parameters (note: actual server may have different speaker range)
    if speaker < 0:
        raise ValueError(f"Speaker must be >= 0, got {speaker}")
    if not (0.1 <= tempo <= 2.0):
        raise ValueError(f"Tempo must be 0.1-2.0, got {tempo}")
    if not (0.1 <= pitch <= 2.0):
        raise ValueError(f"Pitch must be 0.1-2.0, got {pitch}")
    if not (0.1 <= gain <= 2.0):
        raise ValueError(f"Gain must be 0.1-2.0, got {gain}")

    payload = {
        "output_type": output_type,
        "_MODEL": 0,
        "_SPEAKER": speaker,
        "_TEMPO": tempo,
        "_PITCH": pitch,
        "_GAIN": gain,
        "_CONVRATE": 0,
        "_TEXT": text,
    }

    # Log payload for debugging
    import sys

    print(f"[MzTTS] Sending payload: {payload}", file=sys.stderr)

    try:
        if output_type == "file":
            # Request WAV file directly
            response = requests.post(
                MZTTS_API_URL, json=payload, timeout=30, stream=True
            )
            response.raise_for_status()

            # Check if response is JSON (error) or binary (WAV file)
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                # This is an error response
                error_data = response.json()
                raise RuntimeError(f"MzTTS API error: {error_data}")

            # Return binary WAV data
            return {"audio_data": response.content, "content_type": "audio/wav"}
        else:
            # Request JSON response (path or pcm)
            response = requests.post(MZTTS_API_URL, json=payload, timeout=30)
            response.raise_for_status()
            return response.json()

    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to connect to MzTTS API: {e}")


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
        meta_path = TTS_CACHE_DIR / f"{key}.json"
        audio_path = TTS_CACHE_DIR / f"{key}.bin"
        meta_path.write_text(
            json.dumps({"content_type": content_type}, ensure_ascii=True),
            encoding="utf-8",
        )
        audio_path.write_bytes(audio_data)
        TTS_CACHE[key] = {"content_type": content_type, "audio_data": audio_data}
    except Exception:
        return


def _prewarm_tts_cache_for_sentences() -> None:
    if TTS_BACKEND != "gemini":
        logger.info("[TTS_PREWARM] Skipped (backend=%s)", TTS_BACKEND)
        return
    if not GEMINI_API_KEY:
        logger.warning("[TTS_PREWARM] Skipped (GEMINI_API_KEY missing)")
        return
    try:
        sentences = load_json_data("sentences.json") or []
    except Exception as e:
        logger.error("[TTS_PREWARM] Failed to load sentences: %s", e)
        return
    if not isinstance(sentences, list) or not sentences:
        logger.warning("[TTS_PREWARM] No sentences found to prewarm")
        return

    logger.info("[TTS_PREWARM] Starting prewarm for %s sentences", len(sentences))
    start_time = time.perf_counter()
    warmed = 0
    skipped = 0
    failed = 0
    for item in sentences:
        text = item.get("text") if isinstance(item, dict) else str(item)
        if not text:
            continue
        cache_key = _tts_cache_key(text, GEMINI_TTS_MODEL, "gemini")
        if _get_tts_cache(cache_key):
            skipped += 1
            continue
        try:
            result = _call_gemini_tts_api(text=text)
            content_type = result.get("content_type") or "application/octet-stream"
            audio_data = result["audio_data"]
            if content_type.startswith("audio/L16"):
                audio_data = _amplify_pcm16(audio_data)
                audio_data = _pcm16_to_wav(audio_data, sample_rate=24000, channels=1)
                content_type = "audio/wav"
            _set_tts_cache(cache_key, content_type, audio_data)
            warmed += 1
        except Exception as e:
            failed += 1
            logger.warning("[TTS_PREWARM] Failed for '%s': %s", text, e)
    elapsed = time.perf_counter() - start_time
    logger.info(
        "[TTS_PREWARM] Done warmed=%s skipped=%s failed=%s elapsed=%.1fs",
        warmed,
        skipped,
        failed,
        elapsed,
    )


def _amplify_pcm16(
    pcm_data: bytes, target_peak: float = 1.0, max_gain: float = None
) -> bytes:
    """Normalize PCM16 audio to a target peak."""
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
    """Wrap raw PCM16 LE bytes in a WAV container for browser playback."""
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
            struct.pack("<H", 1),  # PCM
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


# Google TTS (Cloud Text-to-Speech)
_google_tts_client = None
_google_tts_client_initialized = False


def _get_google_tts_client():
    global _google_tts_client, _google_tts_client_initialized
    if _google_tts_client_initialized:
        return _google_tts_client
    _google_tts_client_initialized = True
    if not GOOGLE_TTS_AVAILABLE:
        logger.warning("[Google TTS] google-cloud-texttospeech not installed")
        return None
    try:
        _google_tts_client = texttospeech.TextToSpeechClient()
        logger.info("[Google TTS] Client initialized")
        return _google_tts_client
    except Exception as e:
        logger.warning("[Google TTS] Failed to initialize client: %s", e)
        return None


def _call_google_tts_api(
    text: str,
    language_code: str = None,
    voice_name: str = None,
    speaking_rate: float = None,
    pitch: float = None,
    audio_encoding: str = None,
) -> dict:
    if not GOOGLE_TTS_AVAILABLE:
        raise RuntimeError("google-cloud-texttospeech not installed")

    client = _get_google_tts_client()
    if client is None:
        raise RuntimeError("Google TTS client not initialized (check credentials)")

    lc = language_code or GOOGLE_TTS_LANGUAGE
    vn = voice_name or GOOGLE_TTS_VOICE
    rate = speaking_rate if speaking_rate is not None else GOOGLE_TTS_SPEAKING_RATE
    pt = pitch if pitch is not None else GOOGLE_TTS_PITCH
    encoding = (audio_encoding or GOOGLE_TTS_AUDIO_ENCODING or "MP3").upper()

    audio_enum = (
        texttospeech.AudioEncoding.MP3
        if encoding == "MP3"
        else texttospeech.AudioEncoding.LINEAR16
    )
    media_type = (
        "audio/mpeg" if audio_enum == texttospeech.AudioEncoding.MP3 else "audio/wav"
    )

    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice_params = texttospeech.VoiceSelectionParams(language_code=lc, name=vn)
    audio_config = texttospeech.AudioConfig(
        audio_encoding=audio_enum,
        speaking_rate=max(0.25, min(4.0, rate)),
        pitch=max(-20.0, min(20.0, pt)),
    )

    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice_params,
        audio_config=audio_config,
    )

    audio_bytes = response.audio_content
    if not audio_bytes:
        raise RuntimeError("Google TTS returned empty audio")

    if audio_enum == texttospeech.AudioEncoding.LINEAR16:
        audio_bytes = _pcm16_to_wav(audio_bytes, sample_rate=24000, channels=1)
        media_type = "audio/wav"

    return {"audio_data": audio_bytes, "content_type": media_type}


def get_mztts_server_info() -> dict:
    """Get MzTTS server information (version, speakers, sampling rate, etc.)"""
    try:
        response = requests.get(MZTTS_API_URL, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise RuntimeError(f"Failed to get MzTTS server info: {e}")


# ==========================================
# Auth & Signup storage (SQLite + PBKDF2)
# ==========================================
DB_PATH = Path("data/users.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
PBKDF_ITERATIONS = 120_000
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _init_user_db():
    """Ensure the users table exists and has the is_admin column."""
    conn = sqlite3.connect(DB_PATH)
    try:
        # WAL 모드 활성화 — 한 번 설정하면 DB 파일에 영구 적용 (모든 연결에서 자동 사용)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.commit()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                nickname TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                native_lang TEXT,
                affiliation TEXT,
                time_pref TEXT,
                interests TEXT,
                goal TEXT,
                exam_level TEXT,
                reason TEXT,
                style TEXT,
                created_at TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                role TEXT DEFAULT 'learner'
            )
            """
        )
        conn.commit()
        _ensure_is_admin_column(conn)
        _ensure_role_column(conn)
        _ensure_word_score_table(conn)
        _ensure_sentence_score_table(conn)
        _ensure_attendance_table(conn)
        _ensure_rag_tables(conn)
        _ensure_lms_tables(conn)
        _ensure_admin_logging_tables(conn)
        _ensure_saved_vocab_table(conn)
        _ensure_saved_textbooks_table(conn)
        _ensure_credits_columns(conn)
        _seed_admin_user(conn)
    finally:
        conn.close()


def _ensure_saved_textbooks_table(conn):
    """AI 레슨 메이커에서 생성된 교재를 저장하기 위한 테이블 생성."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS saved_textbooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            topic TEXT NOT NULL,
            level TEXT,
            dialogue TEXT,
            vocabulary TEXT,
            image_url TEXT,
            saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_saved_textbooks_user
            ON saved_textbooks(user_id, saved_at);
        """
    )
    conn.commit()


def _ensure_admin_logging_tables(conn):
    """AI 콘텐츠 및 음성 녹음 기록을 위한 테이블 생성."""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_content_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            content_type TEXT,
            model_used TEXT,
            prompt TEXT,
            result TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_voice_recordings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            sentence_id TEXT,
            file_path TEXT,
            score REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def _ensure_is_admin_column(conn):
    """Add is_admin column if missing for existing databases."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(users)")
    cols = [row[1] for row in cursor.fetchall()]
    if "is_admin" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
        conn.commit()


def _ensure_role_column(conn):
    """Add role column if missing and backfill values."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(users)")
    cols = [row[1] for row in cursor.fetchall()]
    if "role" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'learner'")
        conn.commit()

    cursor.execute(
        "UPDATE users SET role = ? WHERE role IS NULL OR TRIM(role) = ''",
        (ROLE_LEARNER,),
    )
    cursor.execute(
        "UPDATE users SET role = ? WHERE is_admin = 1",
        (ROLE_SYSTEM_ADMIN,),
    )
    conn.commit()


def _ensure_word_score_table(conn):
    """Create word score history table if missing."""
    cursor = conn.cursor()
    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS word_score_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            word_id TEXT NOT NULL,
            score INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_word_score_user_word
            ON word_score_history(user_id, word_id, created_at);
        """
    )
    conn.commit()


def _ensure_credits_columns(conn):
    """Add daily credit tracking columns to users table if missing."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    if "credits_used" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN credits_used INTEGER DEFAULT 0")
    if "credits_reset_date" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN credits_reset_date TEXT DEFAULT ''")
    conn.commit()


def _ensure_saved_vocab_table(conn):
    """Create user saved vocabulary table if missing."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_saved_vocab (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            label TEXT NOT NULL,
            pos TEXT,
            meaning TEXT,
            source TEXT DEFAULT 'tube',
            saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, label)
        );
        CREATE INDEX IF NOT EXISTS idx_saved_vocab_user
            ON user_saved_vocab(user_id, saved_at);
        """
    )
    conn.commit()


def _ensure_sentence_score_table(conn):
    """Create sentence score history table if missing."""
    cursor = conn.cursor()
    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS sentence_score_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            sentence_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_sentence_score_user_sentence
            ON sentence_score_history(user_id, sentence_id, created_at);
        """
    )
    conn.commit()


def _ensure_attendance_table(conn):
    """Create attendance table if missing."""
    cursor = conn.cursor()
    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, date)
        );
        CREATE INDEX IF NOT EXISTS idx_attendance_user_date
            ON attendance(user_id, date);
        """
    )
    conn.commit()


def _ensure_lms_tables(conn):
    """Create LMS-specific tables: sentence_scores, lecture_attendance, study_sessions."""
    cursor = conn.cursor()
    cursor.executescript(
        """
        -- LMS 문장별 성적 (최초/최고/최근 3포인트 저장)
        CREATE TABLE IF NOT EXISTS sentence_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            sentence_id TEXT NOT NULL,
            sentence_text TEXT,
            level TEXT,
            score_first REAL,
            score_best REAL,
            score_latest REAL,
            accuracy_first REAL,
            accuracy_best REAL,
            accuracy_latest REAL,
            completeness_latest REAL,
            fluency_accuracy_latest REAL,
            attempt_count INTEGER DEFAULT 1,
            term_id TEXT DEFAULT '2026-1',
            device_type TEXT,
            ui_lang TEXT DEFAULT 'en',
            last_attempted_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sentence_scores_user_sentence
            ON sentence_scores(user_id, sentence_id);
        CREATE INDEX IF NOT EXISTS idx_sentence_scores_user_level
            ON sentence_scores(user_id, level);

        -- LMS 강의 회차 기반 출결
        CREATE TABLE IF NOT EXISTS lecture_attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            video_id TEXT NOT NULL,
            week INTEGER,
            status TEXT DEFAULT 'absent',
            watched_pct REAL DEFAULT 0,
            study_seconds INTEGER DEFAULT 0,
            attended_at TEXT,
            modified_by INTEGER,
            modified_at TEXT,
            term_id TEXT DEFAULT '2026-1',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_lecture_attendance_user_video
            ON lecture_attendance(user_id, video_id);
        CREATE INDEX IF NOT EXISTS idx_lecture_attendance_user_week
            ON lecture_attendance(user_id, week);

        -- 유효 학습 체류 시간 세션
        CREATE TABLE IF NOT EXISTS study_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            page TEXT NOT NULL,
            page_type TEXT,
            duration_seconds INTEGER DEFAULT 0,
            term_id TEXT DEFAULT '2026-1',
            device_type TEXT,
            ui_lang TEXT DEFAULT 'en',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_study_sessions_user_date
            ON study_sessions(user_id, created_at);
        """
    )
    conn.commit()


def _ensure_lms_columns(conn):
    """Add missing LMS columns to users table (parent_code for future use)."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(users)")
    cols = [row[1] for row in cursor.fetchall()]
    if "parent_code" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN parent_code TEXT")
    conn.commit()


def _ensure_rag_tables(conn):
    """Compatibility wrapper after moving RAG helpers to backend.utils."""
    from backend.utils import ensure_rag_tables

    return ensure_rag_tables(conn)


def _seed_admin_user(conn):
    """Seed a default admin account if none exists."""
    admin_email = os.getenv("ADMIN_INITIAL_EMAIL", "").lower().strip()
    admin_password = os.getenv("ADMIN_INITIAL_PASSWORD", "")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE is_admin = 1")
    row = cursor.fetchone()
    if row:
        return

    if not admin_email or not admin_password:
        logging.warning(
            "[SECURITY] No admin user found and ADMIN_INITIAL_EMAIL / ADMIN_INITIAL_PASSWORD "
            "env vars are not set. Skipping admin seed. Set these env vars to create the initial admin account."
        )
        return

    password_hash = _hash_password(admin_password)
    created_at = datetime.utcnow().isoformat()
    cursor.execute(
        """
        INSERT OR IGNORE INTO users (
            email, nickname, password_hash, native_lang, affiliation, time_pref,
            interests, goal, exam_level, reason, style, created_at, is_admin, role
        ) VALUES (?, ?, ?, '', '', '', '[]', '', '', '', '', ?, 1, ?)
        """,
        (
            admin_email,
            "Admin",
            password_hash,
            created_at,
            ROLE_SYSTEM_ADMIN,
        ),
    )
    conn.commit()


def _hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF_ITERATIONS
    )
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(derived).decode()}"


def _normalize_interests(raw):
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(v) for v in raw if str(v).strip()]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(v) for v in parsed if str(v).strip()]
        except Exception:
            pass
        return [v.strip() for v in raw.split(",") if v.strip()]
    return []


def _store_user_signup(payload: dict) -> dict:
    email = (payload.get("email") or "").strip().lower()
    nickname = (payload.get("nickname") or "").strip()
    password = payload.get("password") or ""

    if not email or not EMAIL_REGEX.match(email):
        raise HTTPException(status_code=400, detail="유효한 이메일을 입력하세요.")
    if not nickname:
        raise HTTPException(status_code=400, detail="닉네임을 입력하세요.")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="비밀번호는 8자 이상이어야 합니다.")

    native_lang = (payload.get("native_lang") or "").strip()
    affiliation = (payload.get("affiliation") or "").strip()
    time_pref = (payload.get("time_pref") or "").strip()
    interests = _normalize_interests(payload.get("interests"))
    goal = (payload.get("goal") or "").strip()
    exam_level = (payload.get("exam_level") or "").strip()
    reason = (payload.get("reason") or "").strip()
    style = (payload.get("style") or "").strip()

    password_hash = _hash_password(password)
    created_at = datetime.utcnow().isoformat()

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            INSERT INTO users (
                email, nickname, password_hash, native_lang, affiliation,
                time_pref, interests, goal, exam_level, reason, style, created_at, is_admin, role
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                email,
                nickname,
                password_hash,
                native_lang,
                affiliation,
                time_pref,
                json.dumps(interests, ensure_ascii=False),
                goal,
                exam_level,
                reason,
                style,
                created_at,
                ROLE_LEARNER,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")
    finally:
        conn.close()

    return {"email": email, "nickname": nickname}


def _verify_password(stored_hash: str, password: str) -> bool:
    """Verify password against stored PBKDF2 hash."""
    try:
        parts = stored_hash.split("$")
        if len(parts) != 2:
            return False
        salt = base64.b64decode(parts[0])
        stored_derived = base64.b64decode(parts[1])

        derived = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, PBKDF_ITERATIONS
        )
        return hmac.compare_digest(derived, stored_derived)
    except Exception:
        return False


def _get_user_by_email(email: str) -> dict:
    """Fetch user by email, return dict with id/email/nickname/password_hash or None."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, email, nickname, password_hash, is_admin, role
            FROM users WHERE email = ?
            """,
            ((email or "").strip().lower(),),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _get_user_by_nickname(nickname: str) -> dict:
    """Fetch user by nickname, return dict with id/email/nickname/password_hash or None."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, email, nickname, password_hash, is_admin, role
            FROM users WHERE nickname = ?
            """,
            ((nickname or "").strip(),),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _create_session_token(user_id: int, email: str, is_admin: bool = False) -> str:
    """Create a simple JWT-like session token."""
    import secrets
    import time

    timestamp = time.time()
    random_str = secrets.token_hex(16)
    data = f"{user_id}|{email}|{int(timestamp)}|{random_str}|{int(bool(is_admin))}"
    token = base64.b64encode(data.encode()).decode()

    active_sessions[token] = {
        "user_id": user_id,
        "email": email,
        "created_at": timestamp,
        "is_admin": bool(is_admin),
    }

    return token


def _get_user_by_google_id(google_id: str) -> dict:
    """Fetch user by google_id."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, email, nickname, is_admin, role FROM users WHERE google_id = ?",
            (google_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _create_google_user(email: str, nickname: str, google_id: str) -> dict:
    """Create a new user from Google profile."""
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        created_at = datetime.utcnow().isoformat()
        cursor.execute(
            """
            INSERT INTO users (email, nickname, password_hash, google_id, created_at)
            VALUES (?, ?, '', ?, ?)
            """,
            (email, nickname, google_id, created_at),
        )
        conn.commit()
        user_id = cursor.lastrowid
        return {
            "id": user_id,
            "email": email,
            "nickname": nickname,
            "is_admin": 0,
            "role": "learner",
        }
    finally:
        conn.close()


def _parse_session_token(token: str) -> dict:
    """Parse session token, return dict with user_id/email or None."""
    import time

    try:
        # Check active_sessions first (includes expiry check)
        if token in active_sessions:
            session = active_sessions[token]
            created_at = session.get("created_at", 0)

            # Check if session has expired
            if time.time() - created_at > SESSION_EXPIRY_SECONDS:
                # Session expired, remove it
                del active_sessions[token]
                logger.info(
                    f"[SESSION_EXPIRED] user_id={session.get('user_id')} email={session.get('email')}"
                )
                return None

            # Session is valid
            return {
                "user_id": session["user_id"],
                "email": session["email"],
                "is_admin": session.get("is_admin", False),
            }

        raw = base64.b64decode(token).decode("utf-8")
        user_id, email, created_at, _random_str, is_admin = raw.split("|", 4)
        session = {
            "user_id": int(user_id),
            "email": email,
            "created_at": float(created_at),
            "is_admin": bool(int(is_admin)),
        }
        if time.time() - session["created_at"] > SESSION_EXPIRY_SECONDS:
            return None

        active_sessions[token] = session
        return {
            "user_id": session["user_id"],
            "email": session["email"],
            "is_admin": session["is_admin"],
        }

    except Exception as e:
        logger.debug(f"[SESSION_PARSE_ERROR] {e}")
    return None


def _extract_session_from_request(request: Request) -> dict:
    """Extract session data from Authorization header, cookie, or query param."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        token = request.cookies.get("session_token", "")
    if not token:
        token = request.query_params.get("token", "")
    if not token:
        return None
    return _parse_session_token(token)


@lru_cache(maxsize=128)
def _get_user_by_id_cached(user_id: int) -> tuple:
    """Internal: fetch user row and return as immutable tuple of items for cache safety."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, email, nickname, native_lang, affiliation, time_pref,
                   interests, goal, exam_level, reason, style, created_at, is_admin, role
            FROM users WHERE id = ?
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        if row:
            data = dict(row)
            if data.get("interests"):
                try:
                    data["interests"] = json.loads(data["interests"])
                except Exception:
                    data["interests"] = []
            data["role"] = _normalize_role(data.get("role"), data.get("is_admin"))
            # Return as tuple of items so lru_cache stores an immutable value
            return tuple(data.items())
        return None
    finally:
        conn.close()


def _get_user_by_id(user_id: int) -> dict:
    """Fetch full user profile by ID. Always returns a fresh copy to prevent cache mutation."""
    result = _get_user_by_id_cached(user_id)
    if result is None:
        return None
    return dict(result)


def _clear_user_cache():
    """Clear the user lookup cache."""
    _get_user_by_id_cached.cache_clear()


def _require_authenticated_user(request: Request) -> dict:
    """Return authenticated user or raise HTTP 401/404."""
    session = _extract_session_from_request(request)
    if not session:
        raise HTTPException(status_code=401, detail="토큰이 없습니다.")

    user = _get_user_by_id(session.get("user_id"))
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    return user


def _redirect_if_unauthenticated(request: Request):
    """Redirect unauthenticated users to login page or return None if authenticated."""
    try:
        _require_authenticated_user(request)
        return None
    except HTTPException:
        return RedirectResponse(url="/login")


def _get_word_score_history(user_id: int, limit: int = 3) -> dict:
    """Return per-word score history for a user."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT word_id, score, created_at
            FROM word_score_history
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    history = {}
    for row in rows:
        word_id = row["word_id"]
        history.setdefault(word_id, [])
        if len(history[word_id]) < limit:
            history[word_id].append(row["score"])
    return history


def _get_sentence_score_history(user_id: int, limit: int = 3) -> dict:
    """Return per-sentence score history for a user."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT sentence_id, score, created_at
            FROM sentence_score_history
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    history = {}
    for row in rows:
        sentence_id = str(row["sentence_id"])
        history.setdefault(sentence_id, [])
        if len(history[sentence_id]) < limit:
            history[sentence_id].append(row["score"])
    return history


def _find_vocab_id_by_word(word_text: str) -> str:
    """Find vocabulary id by exact Korean word match."""
    if not word_text:
        return ""
    normalized = normalize_spaces(word_text)
    vocabulary = load_json_data("vocabulary.json") or []
    for item in vocabulary:
        if normalize_spaces(item.get("word", "")) == normalized:
            return item.get("id") or ""
    return ""


# ==========================================
# 로깅 설정
# ==========================================
Path("logs").mkdir(parents=True, exist_ok=True)
file_handler = TimedRotatingFileHandler(
    "logs/detailed.log", when="midnight", interval=1, backupCount=30, encoding="utf-8"
)
file_handler.suffix = "%Y-%m-%d"


def _log_namer(default_name: str) -> str:
    base = os.path.basename(default_name)
    prefix = "detailed.log."
    if base.startswith(prefix):
        date_part = base[len(prefix) :]
        return os.path.join(os.path.dirname(default_name), f"{date_part}-detailed.log")
    return default_name


file_handler.namer = _log_namer
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[file_handler, logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Uvicorn 로거 설정
uvicorn_logger = logging.getLogger("uvicorn")
uvicorn_logger.setLevel(logging.INFO)


# 요청/응답 로깅 미들웨어
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 요청 정보 기록
        client_host = request.client.host if request.client else "Unknown"
        method = request.method
        path = request.url.path
        query_params = dict(request.query_params) if request.query_params else {}

        # 세션 토큰에서 사용자 정보 추출 (정적 파일 요청이 아닌 경우에만)
        user_info = "Guest"
        user_label = "Guest"
        user_email = ""
        user_role = ""
        
        is_static = (
            path.startswith("/static") or 
            path.startswith("/uploads") or 
            path.startswith("/data/locales") or
            path.endswith((".ico", ".png", ".jpg", ".jpeg", ".svg", ".css", ".js", ".mp3", ".mp4"))
        )
        
        if not is_static:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                session_data = _parse_session_token(token)
                if session_data:
                    user_id = session_data.get("user_id")
                    email = session_data.get("email")
                    # 데이터베이스에서 닉네임 조회
                    user = _get_user_by_id(user_id)
                    if user:
                        user_info = f"{user['nickname']} ({email})"
                        user_label = user["nickname"]
                        user_email = email or ""
                        user_role = user.get("role") or ""
                    else:
                        user_info = f"User#{user_id} ({email})"
                        user_label = f"User#{user_id}"
                        user_email = email or ""

            # 쿠키에서도 확인
            if user_info == "Guest":
                cookie_token = request.cookies.get("session_token")
                if cookie_token:
                    session_data = _parse_session_token(cookie_token)
                    if session_data:
                        user_id = session_data.get("user_id")
                        email = session_data.get("email")
                        user = _get_user_by_id(user_id)
                        if user:
                            user_info = f"{user['nickname']} ({email})"
                            user_label = user["nickname"]
                            user_email = email or ""
                            user_role = user.get("role") or ""
                        else:
                            user_info = f"User#{user_id} ({email})"
                            user_label = f"User#{user_id}"
                            user_email = email or ""

        logger.info(f"[REQUEST] {method} {path} from {client_host} | User: {user_info}")
        if query_params:
            _SENSITIVE_PARAMS = {"token", "password", "secret", "key", "auth"}
            masked_params = {
                k: "[REDACTED]" if any(s in k.lower() for s in _SENSITIVE_PARAMS) else v
                for k, v in query_params.items()
            }
            logger.info(f"[QUERY] {masked_params}")

        # 요청 본문 (POST/PUT 등)
        if method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                if body:
                    content_type = request.headers.get("content-type", "").lower()
                    is_binary = (
                        "multipart/form-data" in content_type
                        or "application/octet-stream" in content_type
                        or content_type.startswith("audio/")
                        or content_type.startswith("video/")
                        or b"\x00" in body[:200]
                    )
                    if is_binary:
                        logger.info(
                            "[BODY] <omitted binary payload; content-type=%s; size=%d>",
                            content_type or "unknown",
                            len(body),
                        )
                        body = b""
                    # JSON 형식이면 파싱, 아니면 문자열로
                    try:
                        body_json = json.loads(body)
                        _SENSITIVE_FIELDS = {"password", "token", "secret", "key", "credential", "auth"}
                        def _mask_sensitive(obj):
                            if isinstance(obj, dict):
                                return {
                                    k: "[REDACTED]" if any(s in k.lower() for s in _SENSITIVE_FIELDS) else _mask_sensitive(v)
                                    for k, v in obj.items()
                                }
                            if isinstance(obj, list):
                                return [_mask_sensitive(i) for i in obj]
                            return obj
                        logger.info(
                            f"[BODY] {json.dumps(_mask_sensitive(body_json), ensure_ascii=False)[:500]}"
                        )
                    except:
                        if body:
                            logger.info(
                                f"[BODY] {body.decode('utf-8', errors='ignore')[:500]}"
                            )
            except Exception as e:
                logger.debug(f"[BODY_ERROR] {e}")

        try:
            response = await call_next(request)
            # 응답 정보 기록
            logger.info(f"[RESPONSE] {method} {path} - Status: {response.status_code}")
            if (
                method == "GET"
                and response.status_code < 400
                and not path.startswith("/api")
                and not path.startswith("/static")
                and not path.startswith("/favicon")
            ):
                logger.info(
                    "[PAGE_VIEW] user=%s email=%s role=%s page=%s ip=%s",
                    user_label,
                    user_email,
                    user_role,
                    path,
                    client_host,
                )
            return response
        except Exception as e:
            logger.error(f"[ERROR] {method} {path} - {str(e)}", exc_info=True)
            raise


app = FastAPI(title="Onui Korean Learning Platform API", version="2.0.0")

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        logger.debug(f"[HTTP {exc.status_code}] {request.url.path} - {exc.detail}")
    else:
        logger.warning(f"[HTTP {exc.status_code}] {request.url.path} - {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "success": False, "message": exc.detail}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"[Validation Error] {request.url.path} - {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"error": "Validation Error", "detail": exc.errors(), "success": False, "message": "입력값이 올바르지 않습니다."}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"[Unhandled Exception] {request.url.path} - {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error", "success": False, "message": "서버 내부 오류가 발생했습니다."}
    )

@app.get("/privacy")
async def privacy(request: Request):
    return templates.TemplateResponse(request, "privacy.html")

# Session persistence for OAuth state
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

templates = Jinja2Templates(directory="templates")
templates.env.globals["CLARITY_PROJECT_ID"] = CLARITY_PROJECT_ID
app.state.templates = templates

learning_service = LearningProgressService()
app.state.learning_service = learning_service

from backend.routes.learning_progress import router as learning_progress_router

app.include_router(learning_progress_router)

from backend.routes.tts import router as tts_router

app.include_router(tts_router)

from backend.routes.speechpro import router as speechpro_router

app.include_router(speechpro_router)

from backend.routes.roleplay import router as roleplay_router

app.include_router(roleplay_router)

from backend.routes.lms import router as lms_router

app.include_router(lms_router)

from backend.routes.auth import router as auth_router
app.include_router(auth_router)

from backend.routes.admin import router as admin_router
app.include_router(admin_router)

from backend.routes.user import router as user_router
app.include_router(user_router)

from backend.routes.ai_services import router as ai_services_router
app.include_router(ai_services_router)

from backend.routes.stt import router as stt_router
app.include_router(stt_router)

from backend.routes.media import router as media_router
app.include_router(media_router)

from backend.routes.content import router as content_router
app.include_router(content_router)

from backend.routes.pages import router as pages_router
app.include_router(pages_router)

# App state hooks for routers (avoid importing from main.py)
app.state.require_authenticated_user = _require_authenticated_user
app.state.redirect_if_unauthenticated = _redirect_if_unauthenticated
app.state.normalize_role = _normalize_role
app.state.role_instructor = ROLE_INSTRUCTOR
app.state.role_system_admin = ROLE_SYSTEM_ADMIN
app.state.role_choices = ROLE_CHOICES
app.state.db_path = DB_PATH
app.state.clear_user_cache = _clear_user_cache
app.state.get_word_score_history = _get_word_score_history
app.state.get_sentence_score_history = _get_sentence_score_history
app.state.find_vocab_id_by_word = _find_vocab_id_by_word
app.state.get_or_build_speechpro_precomputed_sentence = lambda text: globals()[
    "get_or_build_speechpro_precomputed_sentence"
](text)
app.state.oauth = oauth
app.state.store_user_signup = _store_user_signup
app.state.get_user_by_google_id = _get_user_by_google_id
app.state.get_user_by_email = _get_user_by_email
app.state.get_user_by_nickname = _get_user_by_nickname
app.state.create_google_user = _create_google_user
app.state.create_session_token = _create_session_token
app.state.verify_password = _verify_password
app.state.parse_session_token = _parse_session_token
app.state.active_sessions = active_sessions
app.state.session_expiry_seconds = SESSION_EXPIRY_SECONDS
app.state.check_and_consume_credits = check_and_consume_credits
app.state.credit_costs = CREDIT_COSTS
app.state.extract_session_from_request = _extract_session_from_request

# TTS hooks/config for routers
app.state.logger = logger
app.state.tts_backend = TTS_BACKEND
app.state.openai_client = client
app.state.gemini_client = gemini_client
app.state.gemini_live_client = gemini_live_client
app.state.openai_api_key = OPENAI_API_KEY
app.state.openai_tts_model = OPENAI_TTS_MODEL
app.state.openai_tts_voice = OPENAI_TTS_VOICE
app.state.openai_tts_format = OPENAI_TTS_FORMAT
app.state.gemini_tts_model = GEMINI_TTS_MODEL
app.state.gemini_tts_mime = GEMINI_TTS_MIME
app.state.call_google_tts_api = _call_google_tts_api
app.state.google_tts_language = GOOGLE_TTS_LANGUAGE
app.state.google_tts_voice = GOOGLE_TTS_VOICE
app.state.google_tts_audio_encoding = GOOGLE_TTS_AUDIO_ENCODING
app.state.google_speech_available = GOOGLE_SPEECH_AVAILABLE
app.state.get_google_speech_client = _get_google_speech_client
app.state.google_speech_module = speech
app.state.get_mztts_server_info = get_mztts_server_info
app.state.call_mztts_api = _call_mztts_api
app.state.call_gemini_tts_api = _call_gemini_tts_api
app.state.tts_cache_key = _tts_cache_key
app.state.get_tts_cache = _get_tts_cache
app.state.set_tts_cache = _set_tts_cache
app.state.amplify_pcm16 = _amplify_pcm16
app.state.pcm16_to_wav = _pcm16_to_wav

# SpeechPro hooks/config for routers
app.state.convert_audio_bytes_to_wav16 = _convert_audio_bytes_to_wav16
app.state.load_speechpro_precomputed_sentences = lambda: globals()[
    "load_speechpro_precomputed_sentences"
]()
app.state.find_precomputed_sentence = lambda text: globals()[
    "find_precomputed_sentence"
](text)
app.state.generate_pronunciation_feedback = lambda text, score_result, **kwargs: (
    globals()["_generate_pronunciation_feedback"](text, score_result, **kwargs)
)
app.state.model_backend = MODEL_BACKEND
app.state.ollama_model = OLLAMA_MODEL
app.state.gemini_model = GEMINI_MODEL
app.state.openai_model = OPENAI_MODEL
app.state.stt_backend = STT_BACKEND





# CORS 설정
# 개발 환경: localhost 허용
# 프로덕션 환경: ngrok 도메인 허용
allowed_origins = [
    "http://localhost:9000",
    "http://127.0.0.1:9000",
    "https://brainlessly-unequestrian-ember.ngrok-free.dev",
    # 개발 중 다른 포트에서 테스트 시 필요하면 추가
    "http://localhost:5173",  # Vite dev server (if needed)
    "https://onuiai.kr",
    "https://www.onuiai.kr",
    "http://onuiai.kr",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 로깅 미들웨어 추가
app.add_middleware(LoggingMiddleware)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/data/locales/{filename}")
async def serve_locale(filename: str):
    """로케일 JSON 파일 서빙 — Cache-Control 헤더 포함."""
    import mimetypes
    from fastapi.responses import FileResponse
    safe_name = os.path.basename(filename)
    locale_path = os.path.join("data", "locales", safe_name)
    if not os.path.exists(locale_path) or not safe_name.endswith(".json"):
        raise HTTPException(status_code=404, detail="Locale not found")
    return FileResponse(
        locale_path,
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.on_event("startup")
def startup_event():
    logger.info("=" * 50)
    logger.info("FastAPI 서버 시작")
    logger.info("=" * 50)
    logger.info(f"모델 백엔드: {MODEL_BACKEND}")
    # If using Ollama, try to auto-select a suitable model when app starts
    if MODEL_BACKEND == "ollama":
        try:
            _auto_select_ollama_model()
            logger.info("Ollama 모델 자동 선택 완료")
        except Exception as e:
            logger.error(f"Ollama auto-select failed: {e}")
    try:
        _init_user_db()
        logger.info("사용자 데이터베이스 초기화 완료")
    except Exception as e:
        logger.error(f"User DB init failed: {e}")
    if TTS_PREWARM_ON_STARTUP:
        threading.Thread(target=_prewarm_tts_cache_for_sentences, daemon=True).start()
    if SPEECHPRO_PREWARM_ON_STARTUP:
        threading.Thread(target=_prewarm_speechpro_score_for_demo, daemon=True).start()

    # Start session cleanup background task
    threading.Thread(target=_cleanup_expired_sessions, daemon=True).start()
    logger.info(f"세션 관리 시작 (만료 시간: {SESSION_EXPIRY_SECONDS // 3600}시간)")


def _cleanup_expired_sessions():
    """Background task to cleanup expired sessions every hour."""
    import time

    while True:
        try:
            time.sleep(3600)  # Run every hour
            current_time = time.time()
            expired_tokens = [
                token
                for token, session in active_sessions.items()
                if current_time - session.get("created_at", 0) > SESSION_EXPIRY_SECONDS
            ]

            for token in expired_tokens:
                session = active_sessions.pop(token, None)
                if session:
                    logger.info(
                        f"[SESSION_CLEANUP] Removed expired session for user_id={session.get('user_id')} "
                        f"email={session.get('email')}"
                    )

            if expired_tokens:
                logger.info(
                    f"[SESSION_CLEANUP] Removed {len(expired_tokens)} expired sessions"
                )
            else:
                logger.debug(
                    f"[SESSION_CLEANUP] No expired sessions found. Active: {len(active_sessions)}"
                )

        except Exception as e:
            logger.error(f"[SESSION_CLEANUP] Error: {e}", exc_info=True)


# ==========================================
# 학습 데이터 로드 헬퍼 함수
# ==========================================
@lru_cache(maxsize=32)
def load_json_data(filename):
    """Load JSON data from data/ directory (cached per filename)."""
    try:
        with open(f"data/{filename}", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return []


_SPEECHPRO_SENTENCES_CACHE: list | None = None
_SPEECHPRO_RUNTIME_PRECOMPUTED_CACHE: dict[str, dict] = {}
_SPEECHPRO_RUNTIME_PRECOMPUTED_LOCK = threading.Lock()


def load_speechpro_precomputed_sentences():
    """Load precomputed SpeechPro sentences (with syllables/FST) from CSV.
    Cached in memory after first load — CSV is only parsed once per process."""
    global _SPEECHPRO_SENTENCES_CACHE
    if _SPEECHPRO_SENTENCES_CACHE is not None:
        return _SPEECHPRO_SENTENCES_CACHE

    path = "data/sp_ko_questions.csv"
    sentences = []

    if not os.path.exists(path):
        _SPEECHPRO_SENTENCES_CACHE = sentences
        return sentences

    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sentence_kr = normalize_spaces(row.get("sentence", ""))
                try:
                    base_id = int(row.get("ko_id", 0))
                except Exception:
                    base_id = 0

                try:
                    order = int(row.get("order", base_id))
                except Exception:
                    order = base_id

                sentences.append(
                    {
                        "id": 1000 + base_id if base_id else order,
                        "order": order,
                        "sentenceKr": sentence_kr,
                        "sentenceEn": "",
                        "level": row.get("level", "초급"),
                        "difficulty": "SpeechPro",
                        "category": "프리셋",
                        "tags": ["speechpro", "preset"],
                        "tips": "SpeechPro 서버의 프리셋 문장입니다.",
                        "syll_ltrs": row.get("syll_ltrs", ""),
                        "syll_phns": row.get("syll_phns", ""),
                        "fst": row.get("fst", ""),
                        "source": "precomputed",
                    }
                )
    except Exception as e:
        print(f"Error loading {path}: {e}")

    # Order by given order, then id
    sentences.sort(key=lambda s: (s.get("order", 0), s.get("id", 0)))
    _SPEECHPRO_SENTENCES_CACHE = sentences
    return sentences


def find_precomputed_sentence(text: str):
    """Find precomputed sentence entry by normalized text"""
    normalized = normalize_spaces(text or "")
    for item in load_speechpro_precomputed_sentences():
        if normalize_spaces(item.get("sentenceKr", "")) == normalized:
            return item
    return None


def get_or_build_speechpro_precomputed_sentence(text: str):
    """Get precomputed payload for text, building it once via GTP/Model if needed."""
    normalized = normalize_spaces(text or "")
    if not normalized:
        return None

    preset = find_precomputed_sentence(normalized)
    if preset and preset.get("syll_ltrs") and preset.get("syll_phns") and preset.get("fst"):
        return preset

    with _SPEECHPRO_RUNTIME_PRECOMPUTED_LOCK:
        cached = _SPEECHPRO_RUNTIME_PRECOMPUTED_CACHE.get(normalized)
        if cached:
            return cached

    try:
        request_id = f"precompute_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        gtp_result = call_speechpro_gtp(normalized, request_id=request_id)
        if gtp_result.error_code != 0:
            logger.warning(
                "[SPEECHPRO_PRECOMPUTE] gtp error code=%s text=%s",
                gtp_result.error_code,
                normalized,
            )
            return None
        model_result = call_speechpro_model(
            text=normalized,
            syll_ltrs=gtp_result.syll_ltrs,
            syll_phns=gtp_result.syll_phns,
            request_id=request_id,
        )
        if model_result.error_code != 0:
            logger.warning(
                "[SPEECHPRO_PRECOMPUTE] model error code=%s text=%s",
                model_result.error_code,
                normalized,
            )
            return None
        built = {
            "sentenceKr": normalized,
            "syll_ltrs": model_result.syll_ltrs,
            "syll_phns": model_result.syll_phns,
            "fst": model_result.fst,
            "source": "runtime-precomputed",
        }
        with _SPEECHPRO_RUNTIME_PRECOMPUTED_LOCK:
            _SPEECHPRO_RUNTIME_PRECOMPUTED_CACHE[normalized] = built
        return built
    except Exception as e:
        logger.warning("[SPEECHPRO_PRECOMPUTE] failed text=%s error=%s", normalized, e)
        return None


def _generate_silence_wav_bytes(
    duration_ms: int = 300, sample_rate: int = 16000, channels: int = 1
) -> bytes:
    """Generate a tiny WAV payload for warmup requests."""
    frame_count = max(1, int(sample_rate * duration_ms / 1000))
    pcm_silence = b"\x00\x00" * frame_count * channels
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_silence)
    return buf.getvalue()


def _prewarm_speechpro_score_for_demo() -> None:
    """Warm up SpeechPro score path once to reduce first-request latency."""
    try:
        preset = get_or_build_speechpro_precomputed_sentence("안녕하세요.")
        if not preset or not preset.get("fst"):
            # Fallback: build from first available sentence text.
            for item in load_speechpro_precomputed_sentences():
                sentence = (item.get("sentenceKr") or "").strip()
                if not sentence:
                    continue
                preset = get_or_build_speechpro_precomputed_sentence(sentence)
                if preset and preset.get("fst"):
                    break
        if not preset:
            logger.warning("[SPEECHPRO_PREWARM] No valid preset found; skipped")
            return
        fst = preset.get("fst") or ""
        syll_ltrs = preset.get("syll_ltrs") or ""
        syll_phns = preset.get("syll_phns") or ""
        if not fst or not syll_ltrs or not syll_phns:
            logger.warning("[SPEECHPRO_PREWARM] Preset missing data; skipped")
            return
        text = (preset.get("sentenceKr") or "안녕하세요.").strip()
        warmup_audio = _generate_silence_wav_bytes(duration_ms=300)
        start = time.perf_counter()
        result = call_speechpro_score(
            text=text,
            syll_ltrs=syll_ltrs,
            syll_phns=syll_phns,
            fst=fst,
            audio_data=warmup_audio,
            request_id=f"prewarm_{int(time.time())}",
        )
        elapsed = time.perf_counter() - start
        logger.info(
            "[SPEECHPRO_PREWARM] done score=%.2f error_code=%s elapsed=%.3fs",
            float(result.score or 0),
            result.error_code,
            elapsed,
        )
    except Exception as e:
        logger.warning("[SPEECHPRO_PREWARM] failed: %s", e)


async def _generate_pronunciation_feedback(
    text: str, score_result, ui_lang: str = "en"
) -> str:
    """
    Generate AI feedback for pronunciation evaluation using configured AI backend.
    Enhanced with FluencyPro + SpeechPro integrated analysis.

    Args:
        text: Original Korean text
        score_result: ScoreResult object with score and details

    Returns:
        AI-generated feedback string in Korean
    """
    if MODEL_BACKEND not in ("ollama", "gemini", "openai"):
        return None

    # Mapping language codes to full names for better AI understanding
    lang_map = {
        "en": "English (영어)",
        "ja": "Japanese (일본어)",
        "zh": "Chinese (중국어)",
    }
    display_lang = lang_map.get(ui_lang, ui_lang)

    try:
        # Extract key metrics
        overall_score = round(score_result.score or 0)
        details = score_result.details if isinstance(score_result.details, dict) else {}

        # SpeechPro 분석 데이터 추출
        speechpro_info = ""
        if details.get("quality"):
            quality = details["quality"]
            if quality.get("sentences"):
                sent = quality["sentences"][0] if quality["sentences"] else {}
                if sent.get("syllable_count"):
                    speechpro_info += (
                        f"\n- 정확 발음: {sent.get('accuracy_percentage', 0):.1f}%"
                    )
                if sent.get("completeness_percentage"):
                    speechpro_info += (
                        f"\n- 완성도: {sent.get('completeness_percentage', 0):.1f}%"
                    )

        # FluencyPro 분석 데이터 추출
        fluency_info = ""
        if details.get("fluency"):
            f = details["fluency"]
            try:
                correct = (
                    f.get("correct_syllables", f.get("correct syllable count", 0)) or 0
                )
                total = f.get("total_syllables", f.get("syllable count", 0)) or 0
                rate = f.get("speech_rate", f.get("speech rate", 0)) or 0

                acc = (correct / max(total, 1) * 100) if total > 0 else 0

                fluency_info = f"""
FluencyPro 분석:
- 발화 속도: {float(rate):.1f} 음절/초
- 정확 음절: {correct}/{total} 
- 음절 정확도: {acc:.1f}%"""
            except Exception as fe:
                print(f"[AI Feedback] Fluency parse error: {fe}")
                fluency_info = ""

        # 발음이 어려운 단어 분석
        word_scores = []
        if details.get("quality", {}).get("sentences"):
            for sent in details["quality"]["sentences"]:
                if sent.get("text") != "!SIL" and sent.get("words"):
                    for word in sent["words"]:
                        if word.get("text") and word.get("text") != "!SIL":
                            word_scores.append(
                                {
                                    "text": word["text"],
                                    "score": round(word.get("score", 0)),
                                }
                            )

        word_summary = ""
        if word_scores:
            low_words = [w for w in word_scores if w["score"] < 70]
            high_words = [w for w in word_scores if w["score"] >= 90]

            # Internal labels for prompt (not for direct display)
            # Use English for these internal labels to avoid encoding/translation issues in prompt
            if low_words:
                word_summary += "\nDifficult pronunciations: " + ", ".join(
                    [f"{w['text']}({w['score']} points)" for w in low_words[:3]]
                )
            if high_words:
                word_summary += "\nGood pronunciations: " + ", ".join(
                    [f"{w['text']}({w['score']} points)" for w in high_words[:3]]
                )

        prompt = f"""You are a Korean pronunciation expert and a friendly coach. Please provide feedback to the learner based on the pronunciation evaluation results below.

[Target Sentence]
{text}

[Evaluation Summary]
- Overall Score: {overall_score} points{speechpro_info}
{fluency_info}
{word_summary}

[Output Format - Use these markers EXACTLY, no spaces inside brackets]
[요약]
(Summarize current status in 1-2 sentences)

[잘한점]
(At least 3 strengths, each starting with •)

[개선점]
(At least 3 areas for improvement, focusing on difficult words/syllables, each starting with •)

[연습방법]
(At least 3 actionable practice tips, each starting with •)

[점수]
Overall: {overall_score}/100
(Include 2-3 key metrics like Accuracy/Completeness/Fluency)

[Writing Rules]
- All feedback content MUST be written in {display_lang}.
- Original Korean text or example words MUST be kept in Korean.
- Be encouraging but realistic.
- DO NOT include any headers like "## Feedback" or "Feedback:". Start directly with [요약].
- NO markdown bold or stars (*). Use only plain text and •.
- Each section should be sufficiently detailed."""

        if MODEL_BACKEND == "ollama":
            payload = {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}

            resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=15)
            if resp.status_code != 200:
                return None

            result = resp.json()
            feedback = result.get("response", "").strip()

        elif MODEL_BACKEND == "openai":
            if not client or not OPENAI_API_KEY:
                return None

            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "당신은 한국어 발음 교육 전문가입니다.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=2500,
            )
            feedback = response.choices[0].message.content.strip()

        elif MODEL_BACKEND == "gemini":
            if not GEMINI_API_KEY:
                return None

            import google.generativeai as genai

            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel(GEMINI_MODEL)

            try:
                response = model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=2500,
                        temperature=0.7,
                    ),
                )
                if response.candidates and len(response.candidates) > 0:
                    feedback = response.text.strip()
                else:
                    print(
                        "[AI Feedback] Gemini - No candidates returned (likely blocked)"
                    )
                    return None
            except Exception as ge:
                print(f"[AI Feedback] Gemini error: {ge}")
                return None

        else:
            return None

        # Remove obvious JSON artifacts if feedback is a string
        if isinstance(feedback, str):
            feedback = re.sub(r"\{.*?\}", "", feedback, flags=re.DOTALL)
            feedback = feedback.strip()

        if not feedback:
            print("[AI Feedback] Warning: Empty feedback generated")
            return None

        return feedback

    except Exception as e:
        import traceback

        print(f"[AI Feedback] Critical Error: {e}")
        traceback.print_exc()
        return None


# ==========================================
# 페이지 라우트 (Routes)
# ==========================================

@app.get("/sentence-evaluation")
def sentence_evaluation_redirect():
    return RedirectResponse(url="/speechpro-practice", status_code=301)


@app.post("/api/stt/whisper")
async def stt_whisper(
    file: UploadFile = File(...),
    language: str = Form("ko"),
):
    """OpenAI Whisper STT (direct)."""
    if not OPENAI_API_KEY or client is None:
        return JSONResponse(
            status_code=501, content={"error": "OpenAI STT is not configured"}
        )

    allowed_types = {
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/webm",
        "audio/ogg",
        "audio/mp4",
        "audio/x-m4a",
    }

    if file.content_type and file.content_type not in allowed_types:
        return JSONResponse(
            status_code=415, content={"error": "Unsupported media type"}
        )

    tmp_path = None
    original_name = file.filename or ""
    _, ext = os.path.splitext(original_name)
    ext = ext.lower()
    if not ext:
        if file.content_type == "audio/webm":
            ext = ".webm"
        elif file.content_type in ("audio/mpeg", "audio/mp3"):
            ext = ".mp3"
        elif file.content_type in ("audio/ogg", "audio/oga"):
            ext = ".ogg"
        elif file.content_type in ("audio/mp4", "audio/x-m4a"):
            ext = ".m4a"
        else:
            ext = ".wav"
    try:
        with tempfile.NamedTemporaryFile(
            suffix=ext, delete=False, dir=str(APP_TMP_DIR)
        ) as tmp:
            tmp_path = tmp.name
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                tmp.write(chunk)

        file_size = os.path.getsize(tmp_path)
        if file_size < 512:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "audio too short",
                    "details": f"file size {file_size} bytes",
                },
            )

        with open(tmp_path, "rb") as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language=language or "ko",
            )

        text = (
            getattr(transcript, "text", None) or transcript.get("text")
            if isinstance(transcript, dict)
            else None
        )
        if not text:
            return JSONResponse(
                content={
                    "text": "",
                    "warning": "no speech detected",
                    "info": {
                        "filename": original_name,
                        "content_type": file.content_type,
                        "size_bytes": file_size,
                    },
                }
            )
        return JSONResponse(content={"text": text})
    except Exception as err:
        logger.warning("[STT] whisper failed: %s", err)
        return JSONResponse(
            status_code=500,
            content={"error": "whisper stt failed", "details": str(err)},
        )
    finally:
        try:
            await file.close()
        except Exception:
            pass
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


@app.post("/api/stt/google")
async def stt_google(
    file: UploadFile = File(...),
    language: str = Form("ko-KR"),
):
    """Google Cloud Speech-to-Text STT."""
    google_client = _get_google_speech_client()

    if not GOOGLE_SPEECH_AVAILABLE or google_client is None:
        return JSONResponse(
            status_code=501,
            content={
                "error": "Google Cloud Speech-to-Text is not configured or credentials not found"
            },
        )

    allowed_types = {
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/webm",
        "audio/ogg",
        "audio/mp4",
        "audio/x-m4a",
        "audio/flac",
    }

    if file.content_type and file.content_type not in allowed_types:
        return JSONResponse(
            status_code=415, content={"error": "Unsupported media type"}
        )

    tmp_path = None
    original_name = file.filename or ""
    _, ext = os.path.splitext(original_name)
    ext = ext.lower()
    if not ext:
        if file.content_type == "audio/webm":
            ext = ".webm"
        elif file.content_type in ("audio/mpeg", "audio/mp3"):
            ext = ".mp3"
        elif file.content_type in ("audio/ogg", "audio/oga"):
            ext = ".ogg"
        elif file.content_type in ("audio/mp4", "audio/x-m4a"):
            ext = ".m4a"
        elif file.content_type == "audio/flac":
            ext = ".flac"
        else:
            ext = ".wav"

    try:
        with tempfile.NamedTemporaryFile(
            suffix=ext, delete=False, dir=str(APP_TMP_DIR)
        ) as tmp:
            tmp_path = tmp.name
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                tmp.write(chunk)

        file_size = os.path.getsize(tmp_path)
        if file_size < 512:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "audio too short",
                    "details": f"file size {file_size} bytes",
                },
            )

        # Read audio file and send to Google Cloud Speech-to-Text
        with open(tmp_path, "rb") as audio_file:
            content = audio_file.read()

        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code=language or "ko-KR",
            max_alternatives=1,
        )

        response = google_client.recognize(config=config, audio=audio)

        # Extract transcribed text from response
        text = ""
        if response.results:
            for result in response.results:
                if result.alternatives:
                    text += result.alternatives[0].transcript + " "

        text = text.strip()

        if not text:
            return JSONResponse(
                content={
                    "text": "",
                    "warning": "no speech detected",
                    "info": {
                        "filename": original_name,
                        "content_type": file.content_type,
                        "size_bytes": file_size,
                    },
                }
            )

        return JSONResponse(content={"text": text})

    except Exception as err:
        logger.warning("[STT] Google Speech failed: %s", err)
        return JSONResponse(
            status_code=500,
            content={"error": "Google Speech-to-Text failed", "details": str(err)},
        )
    finally:
        try:
            await file.close()
        except Exception:
            pass
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


@app.post("/api/stt/vosk")
async def stt_vosk(file: UploadFile = File(...)):
    """Vosk STT (local)."""
    local_stt = os.getenv("LOCAL_STT", "").lower()
    if local_stt != "vosk":
        return JSONResponse(
            status_code=501, content={"error": "LOCAL_STT=vosk is required"}
        )

    vosk_model_path = os.getenv("VOSK_MODEL_PATH")
    if not vosk_model_path:
        return JSONResponse(
            status_code=501, content={"error": "VOSK_MODEL_PATH not configured"}
        )

    allowed_types = {
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/webm",
        "audio/ogg",
        "audio/mp4",
        "audio/x-m4a",
    }

    if file.content_type and file.content_type not in allowed_types:
        return JSONResponse(
            status_code=415, content={"error": "Unsupported media type"}
        )

    tmp_input = None
    tmp_wav = None
    original_name = file.filename or ""
    _, ext = os.path.splitext(original_name)
    ext = ext.lower() or ".wav"

    try:
        with tempfile.NamedTemporaryFile(
            suffix=ext, delete=False, dir=str(APP_TMP_DIR)
        ) as tmp:
            tmp_input = tmp.name
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                tmp.write(chunk)

        fd, tmp_wav = tempfile.mkstemp(suffix=".wav", dir=str(APP_TMP_DIR))
        os.close(fd)
        _ensure_wav_16k_mono(tmp_input, tmp_wav)
        text = _transcribe_with_vosk(tmp_wav, vosk_model_path)
        return JSONResponse(content={"text": text or ""})
    except Exception as err:
        logger.warning("[STT] vosk failed: %s", err)
        return JSONResponse(
            status_code=500, content={"error": "vosk stt failed", "details": str(err)}
        )
    finally:
        try:
            await file.close()
        except Exception:
            pass
        for path in (tmp_input, tmp_wav):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass


# ============================================================================
# FluencyPro API (유창성 평가)
# ============================================================================


@app.post("/api/fluencypro/analyze")
async def fluency_analyze(request: Request):
    """음성 유창성 분석 - FluencyPro API (실제 연동)"""
    try:
        form_data = await request.form()
        text = form_data.get("text", "").strip()
        audio_file = form_data.get("audio")

        user = _extract_session_from_request(request)
        user_id = str(user["user_id"]) if user else "anonymous"

        if not text or not audio_file:
            return JSONResponse(
                status_code=400, content={"error": "text and audio are required"}
            )

        # 오디오 데이터 읽기
        audio_data = await audio_file.read()

        # FluencyPro API 호출
        logger.info(f"Calling FluencyPro API for text: {text[:50]}...")
        fluency_result = await call_fluencypro_analyze(text, audio_data)

        if not fluency_result.get("success"):
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": fluency_result.get("error", "유창성 분석에 실패했습니다."),
                },
            )

        # output 파싱
        parsed_output = parse_fluency_output(fluency_result.get("output", ""))

        # 응답 구성
        response_data = {
            "success": True,
            "text": text,
            "total_reading_words": fluency_result.get("total_reading_words", 0),
            "total_correct_words": fluency_result.get("total_correct_words", 0),
            "total_duration": fluency_result.get("total_duration", 0.0),
            "reading_words_per_unit": fluency_result.get("reading_words_per_unit", 0.0),
            "correct_words_per_unit": fluency_result.get("correct_words_per_unit", 0.0),
            "accuracy_rate": fluency_result.get("accuracy_rate", 0.0),
            "recognized_text": parsed_output.get("recognized_text", ""),
            "pauses": parsed_output.get("pauses", []),
            "omitted_words": parsed_output.get("omitted_words", []),
            "error_words": parsed_output.get("error_words", []),
            "total_pauses": parsed_output.get("total_pauses", 0),
            "total_omissions": parsed_output.get("total_omissions", 0),
            "total_errors": parsed_output.get("total_errors", 0),
            "timestamp": datetime.now().isoformat(),
        }

        if user_id != "anonymous":
            try:
                learning_service.update_fluency_test(user_id)
            except Exception as e:
                logger.error(f"Failed to update fluency progress: {e}")

        logger.info(
            f"FluencyPro analysis completed: accuracy={response_data['accuracy_rate']}%"
        )
        return JSONResponse(content=response_data)

    except Exception as e:
        logger.error(f"FluencyPro analyze error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500, content={"success": False, "error": f"서버 오류: {str(e)}"}
        )


@app.post("/api/fluencypro/combined-feedback")
async def get_combined_feedback(request: Request):
    """FluencyPro와 SpeechPro 결과를 종합하여 AI 피드백 생성"""
    try:
        data = await request.json()

        # FluencyPro와 SpeechPro 결과 받기
        text = data.get("text", "")
        fluency_data = data.get("fluency_data", {})
        speechpro_data = data.get("speechpro_data", {})

        if not text:
            return JSONResponse(status_code=400, content={"error": "text is required"})

        # 복합 피드백을 생성할 프롬프트
        prompt = f"""
사용자가 발음한 한국어 문장에 대한 복합 피드백을 생성해주세요.

[사용자 발음 텍스트]
"{text}"

[FluencyPro 유창성 분석]
- 유창성 점수: {fluency_data.get("fluency_score", 0)}/100
- 발화 속도: {fluency_data.get("speech_rate", 0):.2f} 음절/초
- 조음 속도: {fluency_data.get("articulation_rate", 0):.2f} 음절/초
- 정확한 음절 비율: {fluency_data.get("correct_syllables_rate", 0):.1f}%
- 쉼표 개수: {fluency_data.get("pause_count", 0)}개

[SpeechPro 정확도 분석]
- 발음 정확도 점수: {speechpro_data.get("score", 0)}/100
- 발음 상세 피드백: {speechpro_data.get("feedback", "N/A")}

[생성 요청]
학습자에게 제공할 종합적인 피드백을 다음 형식으로 작성해주세요:

{{
  "overall_comment": "전체 평가를 한 문장으로 (50자 이내)",
  "strengths": ["강점 1", "강점 2"],
  "improvements": ["개선점 1", "개선점 2"],
  "tips": ["실습 팁 1", "실습 팁 2"],
  "encouragement": "격려 메시지 (한 문장)"
}}

음성과 발음이 모두 자연스러운 경우 칭찬하고, 특정 부분이 부자연스러운 경우 구체적으로 지적해주세요.
한국어 학습자이므로 친근하고 이해하기 쉬운 표현으로 작성하세요.
"""

        # Gemini 또는 Ollama를 사용하여 피드백 생성
        if MODEL_BACKEND == "gemini":
            if not GEMINI_API_KEY:
                return JSONResponse(
                    status_code=400, content={"error": "GEMINI_API_KEY not configured"}
                )

            import google.generativeai as genai

            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel(GEMINI_MODEL)

            response = model.generate_content(prompt)
            response_text = response.text

        elif MODEL_BACKEND == "ollama":
            payload = {"model": OLLAMA_MODEL, "prompt": prompt}
            resp = requests.post(
                f"{OLLAMA_URL}/api/generate", json=payload, stream=True, timeout=60
            )

            response_text = ""
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        response_text += obj.get("response", "") or obj.get("text", "")
                except Exception:
                    response_text += line

        else:
            return JSONResponse(
                status_code=501, content={"error": "Backend not configured"}
            )

        # 응답에서 JSON 추출
        parsed_feedback = _parse_model_output(response_text)

        if parsed_feedback:
            return JSONResponse(content=parsed_feedback)
        else:
            # 파싱 실패시 기본 구조로 반환
            return JSONResponse(
                content={
                    "overall_comment": "좋은 연습이었습니다!",
                    "strengths": ["발음을 명확하게 했습니다"],
                    "improvements": ["더 자연스러운 속도로 연습해보세요"],
                    "tips": ["매일 꾸준히 연습하세요"],
                    "encouragement": "계속 화이팅!",
                }
            )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "combined-feedback failed", "details": str(e)},
        )


@app.get("/api/fluencypro/metrics/{user_id}")
async def get_fluency_metrics(user_id: str):
    """사용자 유창성 지표 조회"""
    try:
        # 데이터베이스에서 사용자의 유창성 데이터 조회
        db_path = "data/users.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 사용자 정보 조회
        cursor.execute("SELECT id, nickname FROM users WHERE nickname = ?", (user_id,))
        user_row = cursor.fetchone()

        if not user_row:
            return JSONResponse(
                status_code=404, content={"error": f"User {user_id} not found"}
            )

        actual_user_id = user_row[0]

        # 학습 진도에서 발음 연습 데이터 조회
        cursor.execute(
            """
            SELECT 
                COUNT(*) as total_practices,
                AVG(CAST(pronunciation_avg_score AS FLOAT)) as avg_fluency_score,
                MAX(CAST(pronunciation_avg_score AS FLOAT)) as best_fluency_score,
                MIN(CAST(pronunciation_avg_score AS FLOAT)) as worst_fluency_score
            FROM user_learning_progress
            WHERE user_id = ?
            """,
            (actual_user_id,),
        )
        metrics_row = cursor.fetchone()
        conn.close()

        total = metrics_row[0] or 0
        avg_score = round(metrics_row[1] or 0, 1)
        best_score = round(metrics_row[2] or 0, 1)
        worst_score = round(metrics_row[3] or 0, 1)

        # 유창성 평가 등급
        if avg_score >= 90:
            grade = "A+ (매우 좋음)"
        elif avg_score >= 80:
            grade = "A (좋음)"
        elif avg_score >= 70:
            grade = "B (보통)"
        elif avg_score >= 60:
            grade = "C (개선필요)"
        else:
            grade = "D (많은 개선필요)"

        fluency_metrics = {
            "user_id": user_id,
            "total_practices": total,
            "average_fluency_score": avg_score,
            "best_fluency_score": best_score,
            "worst_fluency_score": worst_score,
            "fluency_grade": grade,
            "practice_frequency": "매일"
            if total >= 7
            else "주 3-4회"
            if total >= 3
            else "불규칙",
            "improvement_trend": "상승" if total >= 3 else "데이터 부족",
            "speech_rate_average": round(4.5 + (avg_score / 100), 2),
            "articulation_rate_average": round(4.2 + (avg_score / 120), 2),
            "accuracy_score": round(avg_score, 1),
            "last_practice": datetime.now().isoformat(),
        }

        return JSONResponse(content=fluency_metrics)

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ====================
# Media Generation APIs
# ====================


@app.post("/api/generate-image")
async def generate_image(request: Request):
    """AI 이미지 생성 API (OpenAI DALL-E 3)"""
    _user = _extract_session_from_request(request)
    if not _user:
        return JSONResponse(status_code=401, content={"success": False, "message": "로그인이 필요합니다."})
    _credit = check_and_consume_credits(_user["user_id"], CREDIT_COSTS["image"])
    if not _credit["ok"]:
        return JSONResponse(status_code=429, content={"success": False, "message": f"오늘의 크레딧이 부족합니다. 자정에 리셋됩니다. (남은 크레딧: {_credit['remaining']})", "remaining": _credit["remaining"]})

    try:
        data = await request.json()
        situation = data.get("situation", "").strip()
        style = data.get("style", "illustration")
        quality = data.get("quality", "standard")

        if not situation:
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "상황 설명을 입력해주세요."},
            )

        logger.info(
            f"Image generation request - situation: {situation}, style: {style}, quality: {quality}"
        )

        # 한국어 상황 설명을 영어 프롬프트로 번역 (DALL-E 최적화)
        english_situation = await translate_korean_to_english_prompt(situation)
        
        # 스타일 및 교육용 컨텍스트 추가
        enhanced_prompt = enhance_prompt_for_korean_learning(english_situation, style)

        # DALL-E API 호출 (로컬 저장 포함)
        result = await generate_image_dall_e(
            prompt=enhanced_prompt,
            size=os.getenv("DALLE_IMAGE_SIZE", "1024x1024"),
            quality=quality,
            style=os.getenv("DALLE_STYLE", "vivid"),
            save_locally=True,
        )

        if result["success"]:
            logger.info(
                f"Image generated successfully: {result.get('local_path', result.get('image_url'))}"
            )
            return JSONResponse(
                {
                    "success": True,
                    "image_url": result.get("image_url"),
                    "local_path": result.get("local_path"),
                    "revised_prompt": result.get("revised_prompt", enhanced_prompt),
                    "prompt": enhanced_prompt,
                }
            )
        else:
            logger.error(f"Image generation failed: {result.get('error')}")
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "message": f"이미지 생성 실패: {result.get('error', 'Unknown error')}",
                },
            )

    except Exception as e:
        logger.error(f"Error generating image: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"이미지 생성 중 오류 발생: {str(e)}",
            },
        )


@app.post("/api/generate-music")
async def generate_music(request: Request):
    """AI 음악 생성 API (Placeholder)"""
    try:
        data = await request.json()
        situation = data.get("situation", "")
        mood = data.get("mood", "calm")
        duration = data.get("duration", 30)

        # TODO: 실제 AI 음악 생성 API 연동 (Suno AI, MusicGen 등)
        # 현재는 placeholder 응답

        return JSONResponse(
            {
                "success": True,
                "music_url": "/static/placeholder-music.mp3",
                "description": f"{mood} 분위기의 {duration}초 배경음악",
                "message": "음악 생성 기능은 개발 중입니다. AI 음악 생성 API 연동이 필요합니다.",
            }
        )

    except Exception as e:
        print(f"Error generating music: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": f"음악 생성 중 오류 발생: {str(e)}"},
        )


# ── Video Lessons: auto-discovery ──────────────────────────────────────────
import re as _re


def _parse_video_filename(stem: str):
    """level1_week3_2nd  →  {level:1, week:3, session:'2nd', short_label:'초급 1 | 3주차 - 2차시'}"""
    m = _re.match(r"level(\d+)_week(\d+)_(1st|2nd|3rd|4th)", stem)
    if not m:
        return None
    level, week, session = int(m.group(1)), int(m.group(2)), m.group(3)
    session_num = {"1st": "1", "2nd": "2", "3rd": "3", "4th": "4"}.get(session, session)
    level_name = f"초급 {level}"
    return {
        "level": level,
        "week": week,
        "session": session,
        "session_label": f"{session_num}차시",
        "level_name": level_name,
        "label": f"{level_name} | {week}주차 - {session_num}차시",
        "short_label": f"{level_name} | {week}주차 - {session_num}차시",
        "id": stem,
    }


@app.get("/api/video-lessons")
def api_video_lessons():
    """static/videos/ 폴더를 스캔하여 주차별 강의 목록을 반환합니다.
    mp4/pdf/html 중 어느 하나라도 있으면 목록에 포함됩니다."""
    videos_dir = Path("static/videos")
    lessons: dict = {}

    if videos_dir.exists():
        # mp4 / pdf / html 파일을 모두 스캔 → 어느 하나라도 있으면 강의 항목 생성
        for f in sorted(videos_dir.iterdir()):
            if f.suffix.lower() not in (".mp4", ".pdf", ".html"):
                continue
            meta = _parse_video_filename(f.stem)
            if not meta:
                continue
            key = f.stem
            if key not in lessons:
                lessons[key] = {
                    **meta,
                    "mp4": None,
                    "has_mp4": False,
                    "pdf": None,
                    "has_pdf": False,
                    "html": None,
                    "has_html": False,
                }
            ext = f.suffix.lower()
            if ext == ".mp4":
                lessons[key]["mp4"] = f"/static/videos/{f.name}"
                lessons[key]["has_mp4"] = True
            elif ext == ".pdf":
                lessons[key]["pdf"] = f"/static/videos/{f.name}"
                lessons[key]["has_pdf"] = True
            elif ext == ".html":
                lessons[key]["html"] = f"/static/videos/{f.name}"
                lessons[key]["has_html"] = True

    # Group by level
    result: dict = {}
    for item in sorted(
        lessons.values(), key=lambda x: (x["level"], x["week"], x["session"])
    ):
        lvl = f"level{item['level']}"
        result.setdefault(lvl, []).append(item)

    return JSONResponse(content={"lessons": result})


# ── Video Progress API ──────────────────────────────────────────────────────
def _ensure_video_progress_table(db_path: str = "data/users.db"):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_video_progress (
            user_id TEXT NOT NULL,
            video_id TEXT NOT NULL,
            watched_seconds INTEGER DEFAULT 0,
            duration_seconds INTEGER DEFAULT 0,
            completed INTEGER DEFAULT 0,
            last_position INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, video_id)
        )
    """)
    conn.commit()
    conn.close()


_ensure_video_progress_table()


@app.get("/api/video-progress/{user_id}")
async def get_video_progress(user_id: str, request: Request):
    """사용자의 전체 동영상 시청 진도를 반환합니다."""
    # 세션 검증: 본인 데이터 또는 관리자만 조회 가능
    try:
        session_user = _require_authenticated_user(request)
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"error": e.detail})
    session_user_id = str(session_user.get("id", ""))
    session_role = _normalize_role(session_user.get("role"), session_user.get("is_admin"))
    if session_user_id != str(user_id) and session_role != ROLE_SYSTEM_ADMIN:
        return JSONResponse(status_code=403, content={"error": "권한이 없습니다."})
    try:
        conn = sqlite3.connect("data/users.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT video_id, watched_seconds, duration_seconds, completed, last_position, updated_at "
            "FROM user_video_progress WHERE user_id = ?",
            (user_id,),
        )
        rows = cursor.fetchall()
        conn.close()
        progress = {}
        for row in rows:
            progress[row[0]] = {
                "watched_seconds": row[1],
                "duration_seconds": row[2],
                "completed": bool(row[3]),
                "last_position": row[4],
                "updated_at": row[5],
                "percent": round((row[1] / row[2] * 100) if row[2] else 0),
            }
        return JSONResponse(content={"progress": progress})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


from pydantic import BaseModel as _PydanticBaseModel


class _VideoProgressBody(_PydanticBaseModel):
    video_id: str
    watched_seconds: int = 0
    duration_seconds: int = 0
    last_position: int = 0
    completed: bool = False


@app.post("/api/video-progress")
async def save_video_progress(request: Request, body: _VideoProgressBody):
    """동영상 시청 진도를 저장합니다."""
    # 세션에서 user_id 추출 (body의 user_id는 더 이상 신뢰하지 않음)
    try:
        session_user = _require_authenticated_user(request)
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"error": e.detail})
    user_id = str(session_user.get("id", ""))
    try:
        conn = sqlite3.connect("data/users.db")
        conn.execute(
            """
            INSERT INTO user_video_progress
                (user_id, video_id, watched_seconds, duration_seconds, completed, last_position, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, video_id) DO UPDATE SET
                watched_seconds = MAX(excluded.watched_seconds, watched_seconds),
                duration_seconds = excluded.duration_seconds,
                completed = MAX(excluded.completed, completed),
                last_position = excluded.last_position,
                updated_at = CURRENT_TIMESTAMP
        """,
            (
                user_id,
                body.video_id,
                body.watched_seconds,
                body.duration_seconds,
                int(body.completed),
                body.last_position,
            ),
        )
        conn.commit()

        # LMS: 강의 출결 자동 연동 (실패 무시)
        try:
            _uid_int = int(user_id)
            _watched_pct = (
                round(body.watched_seconds / body.duration_seconds * 100, 1)
                if body.duration_seconds and body.duration_seconds > 0
                else 0.0
            )
            _status = "present" if (_watched_pct >= 80 or body.completed) else "absent"
            _now_str = (
                __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            )
            conn.execute(
                """
                INSERT INTO lecture_attendance
                    (user_id, video_id, week, status, watched_pct, study_seconds,
                     attended_at, term_id, created_at)
                VALUES (?,?,NULL,?,?,?,?,?,?)
                ON CONFLICT(user_id, video_id) DO UPDATE SET
                    status      = CASE WHEN excluded.watched_pct >= 80 OR excluded.status = 'present'
                                       THEN 'present'
                                       WHEN lecture_attendance.status = 'present' THEN 'present'
                                       ELSE 'absent' END,
                    watched_pct = MAX(lecture_attendance.watched_pct, excluded.watched_pct),
                    study_seconds = MAX(lecture_attendance.study_seconds, excluded.study_seconds),
                    attended_at = CASE WHEN (excluded.watched_pct >= 80 OR excluded.status = 'present')
                                         AND lecture_attendance.status != 'present'
                                       THEN excluded.attended_at
                                       ELSE lecture_attendance.attended_at END
                """,
                (
                    _uid_int,
                    body.video_id,
                    _status,
                    _watched_pct,
                    body.watched_seconds,
                    _now_str if _status == "present" else None,
                    "2026-1",
                    _now_str,
                ),
            )
            conn.commit()
        except Exception:
            pass  # 출결 저장 실패는 video-progress 응답에 영향 없음

        conn.close()
        return JSONResponse(content={"saved": True})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


if __name__ == "__main__":
    logger.info("Uvicorn 서버 시작: 0.0.0.0:9002")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=9002,
        reload=True,
        log_level="info",
        access_log=True,
    )
# Use an app-writable temp directory (some deployments mount /tmp read-only).
APP_TMP_DIR = Path(os.getenv("ONUI_TMP_DIR", "data/tmp"))
try:
    APP_TMP_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    # If creation fails, fallback to current working directory.
    APP_TMP_DIR = Path(".")

# Make Python's tempfile (and many libs) prefer the app temp dir over /tmp.
try:
    os.environ["TMPDIR"] = str(APP_TMP_DIR)
    os.environ["TEMP"] = str(APP_TMP_DIR)
    os.environ["TMP"] = str(APP_TMP_DIR)
    tempfile.tempdir = str(APP_TMP_DIR)
except Exception:
    pass
