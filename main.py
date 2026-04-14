import os
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
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, Response, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from openai import OpenAI
from dotenv import load_dotenv
from difflib import SequenceMatcher
import requests
import json
import re
import uvicorn
import asyncio
import subprocess
import wave
import base64
import tempfile
from pathlib import Path
import time

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
    parse_fluency_output
)

# Dictionary API service import
from backend.services.krdict_service import search_krdict

# DALL-E 서비스 임포트
from backend.services.dalle_service import (
    generate_image_dall_e,
    generate_image_gemini,
    enhance_prompt_for_korean_learning
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
        "g", "kk", "n", "d", "tt", "r", "m", "b", "pp",
        "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h"
    ]
    V_TABLE = [
        "a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o",
        "wa", "wae", "oe", "yo", "u", "wo", "we", "wi", "yu",
        "eu", "ui", "i"
    ]
    T_TABLE = [
        "", "k", "k", "ks", "n", "nj", "nh", "t", "l", "lg",
        "lm", "lb", "ls", "lt", "lp", "lh", "m", "p", "ps",
        "t", "t", "ng", "t", "ch", "k", "t", "p", "h"
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
            return "".join(_romanize_syllable(ch) if 0xAC00 <= ord(ch) <= 0xD7A3 else ch for ch in text)
        except Exception:
            return text

    ROMANIZER_AVAILABLE = False

# ==========================================
# 설정: 환경변수에서 OpenAI API 키 로드
# ==========================================
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# KRDIC API key (Korean Basic Dictionary)
KRDICT_API_KEY = os.getenv("KRDICT_API_KEY")

# Backend selection: set MODEL_BACKEND to 'ollama', 'openai', or 'gemini'
MODEL_BACKEND = os.getenv("MODEL_BACKEND", "ollama")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "exaone3.5:2.4b")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")

# Initialize Gemini client if available
gemini_client = None
if GEMINI_API_KEY and GENAI_AVAILABLE:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)

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
        logger.warning("[Google STT] Failed to initialize client: %s (requires GOOGLE_APPLICATION_CREDENTIALS)", e)
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
TTS_PREWARM_ON_STARTUP = os.getenv("TTS_PREWARM_ON_STARTUP", "").lower() in ("1", "true", "yes")
TTS_CACHE = {}
WORD_IMAGE_CACHE_PATH = Path(os.getenv("WORD_IMAGE_CACHE_PATH", "data/word_image_cache.json"))
WORD_IMAGE_CACHE_LOCK = threading.Lock()

# Session management
SESSION_EXPIRY_SECONDS = 24 * 60 * 60  # 24 hours
active_sessions = {}  # {token: {"user_id": int, "email": str, "created_at": float, "is_admin": bool}}

# Role definitions
ROLE_LEARNER = "learner"
ROLE_INSTRUCTOR = "instructor"
ROLE_SYSTEM_ADMIN = "system_admin"
ROLE_CHOICES = {ROLE_LEARNER, ROLE_INSTRUCTOR, ROLE_SYSTEM_ADMIN}


def _normalize_role(role: str, is_admin: bool = False) -> str:
    """Return a valid role, prioritizing system admin when is_admin is true."""
    if is_admin:
        return ROLE_SYSTEM_ADMIN
    if role in ROLE_CHOICES:
        return role
    return ROLE_LEARNER


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
    gain: float = None
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
        "_TEXT": text
    }

    # Log payload for debugging
    import sys
    print(f"[MzTTS] Sending payload: {payload}", file=sys.stderr)

    try:
        if output_type == "file":
            # Request WAV file directly
            response = requests.post(
                MZTTS_API_URL,
                json=payload,
                timeout=30,
                stream=True
            )
            response.raise_for_status()

            # Check if response is JSON (error) or binary (WAV file)
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                # This is an error response
                error_data = response.json()
                raise RuntimeError(f"MzTTS API error: {error_data}")

            # Return binary WAV data
            return {
                "audio_data": response.content,
                "content_type": "audio/wav"
            }
        else:
            # Request JSON response (path or pcm)
            response = requests.post(
                MZTTS_API_URL,
                json=payload,
                timeout=30
            )
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
                return {"audio_data": base64.b64decode(data), "content_type": mime or GEMINI_TTS_MIME}
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


def _load_word_image_cache() -> dict:
    if not WORD_IMAGE_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(WORD_IMAGE_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_word_image_cache(cache: dict) -> None:
    try:
        WORD_IMAGE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        WORD_IMAGE_CACHE_PATH.write_text(
            json.dumps(cache, ensure_ascii=True),
            encoding="utf-8",
        )
    except Exception:
        return


def _get_cached_word_image(key: str) -> Optional[Dict]:
    if not key:
        return None
    with WORD_IMAGE_CACHE_LOCK:
        cache = _load_word_image_cache()
        return cache.get(key)


def _set_cached_word_image(key: str, url: str) -> None:
    if not key or not url:
        return
    with WORD_IMAGE_CACHE_LOCK:
        cache = _load_word_image_cache()
        cache[key] = {"url": url, "updatedAt": int(time.time() * 1000)}
        _save_word_image_cache(cache)


def _amplify_pcm16(pcm_data: bytes, target_peak: float = 1.0, max_gain: float = None) -> bytes:
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

    amplified = [
        max(-32768, min(32767, int(s * gain)))
        for s in samples
    ]
    return struct.pack("<" + "h" * sample_count, *amplified)


def _pcm16_to_wav(pcm_data: bytes, sample_rate: int = 24000, channels: int = 1) -> bytes:
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

    audio_enum = texttospeech.AudioEncoding.MP3 if encoding == "MP3" else texttospeech.AudioEncoding.LINEAR16
    media_type = "audio/mpeg" if audio_enum == texttospeech.AudioEncoding.MP3 else "audio/wav"

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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                name TEXT,
                nickname TEXT,
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
        _ensure_ai_content_table(conn)
        _seed_admin_user(conn)
    finally:
        conn.close()


def _ensure_ai_content_table(conn):
    """Create AI content generation history table if missing."""
    cursor = conn.cursor()
    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS ai_content_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content_type TEXT NOT NULL, -- 'feedback', 'sentence', 'image', 'chatbot'
            model TEXT NOT NULL,
            prompt TEXT,
            response TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_ai_content_user_type
            ON ai_content_history(user_id, content_type, created_at);
        """
    )
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

def _ensure_rag_tables(conn):
    """Create RAG tables (documents, chunks, FTS index, settings) if missing."""
    cursor = conn.cursor()
    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS rag_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            enabled INTEGER NOT NULL DEFAULT 0,
            top_k INTEGER NOT NULL DEFAULT 5,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        INSERT OR IGNORE INTO rag_settings (id, enabled, top_k) VALUES (1, 0, 5);

        CREATE TABLE IF NOT EXISTS rag_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            source TEXT NOT NULL,
            mime_type TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS rag_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_rag_chunks_doc_idx
            ON rag_chunks(document_id, chunk_index);

        CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunks_fts
        USING fts5(content, chunk_id UNINDEXED, tokenize='unicode61');
        """
    )
    conn.commit()


def _rag_chunk_text(text: str, max_chars: int = 700) -> List[str]:
    cleaned = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return []
    parts = [p.strip() for p in re.split(r"\n{2,}", cleaned) if p.strip()]
    chunks: List[str] = []
    buf = ""
    for part in parts:
        if not buf:
            buf = part
            continue
        if len(buf) + 2 + len(part) <= max_chars:
            buf = f"{buf}\n\n{part}"
        else:
            chunks.append(buf)
            buf = part
    if buf:
        chunks.append(buf)
    # fallback for very long single blocks
    final_chunks: List[str] = []
    for c in chunks:
        if len(c) <= max_chars:
            final_chunks.append(c)
        else:
            for i in range(0, len(c), max_chars):
                final_chunks.append(c[i : i + max_chars].strip())
    return [c for c in final_chunks if c]


def _log_ai_content(user_id: int, content_type: str, model: str, prompt: str = None, response: str = None):
    """Log AI content generation to database."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            INSERT INTO ai_content_history (user_id, content_type, model, prompt, response)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, content_type, model, prompt, response)
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to log AI content: {str(e)}")
    finally:
        conn.close()


def _rag_get_settings(conn) -> dict:
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT enabled, top_k, updated_at FROM rag_settings WHERE id = 1")
    row = cursor.fetchone()
    if not row:
        return {"enabled": False, "top_k": 5, "updated_at": ""}
    return {
        "enabled": bool(row["enabled"]),
        "top_k": int(row["top_k"] or 5),
        "updated_at": row["updated_at"] or "",
    }


def _rag_search(conn, query: str, top_k: int = 5) -> List[Dict]:
    q = (query or "").strip()
    if not q:
        return []
    top_k = max(1, min(int(top_k or 5), 10))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT chunk_id, bm25(rag_chunks_fts) AS score
        FROM rag_chunks_fts
        WHERE rag_chunks_fts MATCH ?
        ORDER BY score
        LIMIT ?
        """,
        (q, top_k),
    )
    hits = cursor.fetchall()
    if not hits:
        return []
    chunk_ids = [int(r["chunk_id"]) for r in hits if r and r["chunk_id"]]
    if not chunk_ids:
        return []
    placeholders = ",".join(["?"] * len(chunk_ids))
    cursor.execute(
        f"""
        SELECT c.id, c.content, c.document_id, d.title, d.source
        FROM rag_chunks c
        JOIN rag_documents d ON d.id = c.document_id
        WHERE c.id IN ({placeholders})
        """,
        chunk_ids,
    )
    rows = cursor.fetchall()
    by_id = {int(r["id"]): dict(r) for r in rows}
    results: list[dict] = []
    for cid in chunk_ids:
        r = by_id.get(cid)
        if not r:
            continue
        results.append(
            {
                "chunk_id": cid,
                "title": r.get("title") or "",
                "source": r.get("source") or "",
                "content": r.get("content") or "",
            }
        )
    return results


def _compute_attendance_streak(conn, user_id: int) -> int:
    cursor = conn.cursor()
    cursor.execute("SELECT date FROM attendance WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    if not rows:
        return 0
    dates = {row[0] for row in rows if row and row[0]}
    streak = 0
    day = datetime.now().date()
    while day.isoformat() in dates:
        streak += 1
        day = day - timedelta(days=1)
    return streak


def _seed_admin_user(conn):
    """Seed a default admin account if none exists."""
    admin_email = os.getenv("ADMIN_EMAIL", "admin@mediazen.co.kr").lower().strip()
    admin_password = os.getenv("ADMIN_PASSWORD", "mz1234!@")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE is_admin = 1")
    row = cursor.fetchone()
    if row:
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
    name = (payload.get("name") or "").strip()
    # For backward compatibility internally, use name as nickname
    nickname = name or email.split("@")[0]
    password = payload.get("password") or ""

    if not email or not EMAIL_REGEX.match(email):
        raise HTTPException(status_code=400, detail="유효한 이메일을 입력하세요.")
    if not name:
        raise HTTPException(status_code=400, detail="이름을 입력하세요.")
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
                email, name, nickname, password_hash, native_lang, affiliation,
                time_pref, interests, goal, exam_level, reason, style, created_at, is_admin, role
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                email,
                name,
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
        user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")
    finally:
        conn.close()

    return {
        "id": user_id,
        "email": email,
        "name": name,
        "nickname": nickname,
        "is_admin": False,
        "role": ROLE_LEARNER,
    }


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
            SELECT id, email, name, nickname, password_hash, is_admin, role
            FROM users WHERE email = ?
            """,
            ((email or "").strip().lower(),)
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
            ((nickname or "").strip(),)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _create_session_token(user_id: int, email: str, is_admin: bool = False) -> str:
    """Create a simple JWT-like session token (in production, use proper JWT library)."""
    import secrets
    import time
    
    # Simple format: base64(id|email|timestamp|random|is_admin)
    timestamp = time.time()
    random_str = secrets.token_hex(16)
    data = f"{user_id}|{email}|{int(timestamp)}|{random_str}|{int(bool(is_admin))}"
    token = base64.b64encode(data.encode()).decode()
    
    # Store session with expiry info
    active_sessions[token] = {
        "user_id": user_id,
        "email": email,
        "created_at": timestamp,
        "is_admin": bool(is_admin)
    }
    
    return token


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
                logger.info(f"[SESSION_EXPIRED] user_id={session.get('user_id')} email={session.get('email')}")
                return None
            
            # Session is valid
            return {
                "user_id": session["user_id"],
                "email": session["email"],
                "is_admin": session.get("is_admin", False)
            }
        
        # Fallback: parse token (for backward compatibility)
        data = base64.b64decode(token.encode()).decode()
        parts = data.split("|")
        if len(parts) >= 3:
            user_id = int(parts[0])
            email = parts[1]
            timestamp = int(parts[2])
            
            # Check expiry
            if time.time() - timestamp > SESSION_EXPIRY_SECONDS:
                logger.info(f"[SESSION_EXPIRED] user_id={user_id} email={email}")
                return None
            
            payload = {"user_id": user_id, "email": email}
            if len(parts) >= 5:
                payload["is_admin"] = parts[4] == "1"
            else:
                payload["is_admin"] = False
            return payload
    except Exception as e:
        logger.debug(f"[SESSION_PARSE_ERROR] {e}")
    return None


def _extract_session_from_request(request: Request) -> dict:
    """Extract session data from Authorization header or cookie."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        token = request.cookies.get("session_token", "")
    if not token:
        return None
    return _parse_session_token(token)


def _get_user_by_id(user_id: int) -> dict:
    """Fetch full user profile by ID."""
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
            (user_id,)
        )
        row = cursor.fetchone()
        if row:
            data = dict(row)
            # Parse interests JSON
            if data.get("interests"):
                try:
                    data["interests"] = json.loads(data["interests"])
                except Exception:
                    data["interests"] = []
            data["role"] = _normalize_role(data.get("role"), data.get("is_admin"))
            return data
        return None
    finally:
        conn.close()


def _require_authenticated_user(request: Request) -> dict:
    """Return authenticated user or raise HTTP 401/404."""
    session = _extract_session_from_request(request)
    if not session:
        raise HTTPException(status_code=401, detail="토큰이 없습니다.")

    user = _get_user_by_id(session.get("user_id"))
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    return user


def _require_admin(request: Request) -> dict:
    """Return admin user or raise HTTP 403."""
    user = _require_authenticated_user(request)
    role = _normalize_role(user.get("role"), user.get("is_admin"))
    if role != ROLE_SYSTEM_ADMIN:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return user


def _require_role(request: Request, allowed_roles) -> dict:
    """Return user if role is allowed, otherwise raise HTTP 403."""
    user = _require_authenticated_user(request)
    role = _normalize_role(user.get("role"), user.get("is_admin"))
    if role not in allowed_roles:
        raise HTTPException(status_code=403, detail="권한이 없습니다.")
    return user


def _get_user_stats() -> dict:
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), SUM(is_admin) FROM users")
        total, admin_count = cursor.fetchone() or (0, 0)
        cursor.execute("SELECT email, nickname, created_at FROM users ORDER BY created_at DESC LIMIT 5")
        recent = [
            {"email": row[0], "nickname": row[1], "created_at": row[2]}
            for row in cursor.fetchall()
        ]
        return {
            "total_users": total or 0,
            "admin_users": admin_count or 0,
            "recent_signups": recent,
        }
    finally:
        conn.close()


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
    "logs/detailed.log",
    when="midnight",
    interval=1,
    backupCount=30,
    encoding="utf-8"
)
file_handler.suffix = "%Y-%m-%d"
def _log_namer(default_name: str) -> str:
    base = os.path.basename(default_name)
    prefix = "detailed.log."
    if base.startswith(prefix):
        date_part = base[len(prefix):]
        return os.path.join(os.path.dirname(default_name), f"{date_part}-detailed.log")
    return default_name
file_handler.namer = _log_namer
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        file_handler,
        logging.StreamHandler()
    ]
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
        
        # 세션 토큰에서 사용자 정보 추출
        user_info = "Guest"
        user_label = "Guest"
        user_email = ""
        user_role = ""
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
            logger.info(f"[QUERY] {query_params}")
        
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
                        logger.info(
                            f"[BODY] {json.dumps(body_json, ensure_ascii=False)[:500]}"
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


app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.state.templates = templates
learning_service = LearningProgressService()
app.state.learning_service = learning_service

from backend.routes.sentence_learning import router as sentence_learning_router
app.include_router(sentence_learning_router)

from backend.routes.learning_progress import router as learning_progress_router
app.include_router(learning_progress_router)

from backend.routes.tts import router as tts_router
app.include_router(tts_router)

from backend.routes.speechpro import router as speechpro_router
app.include_router(speechpro_router)

# App state hooks for routers (avoid importing from main.py)
app.state.require_authenticated_user = _require_authenticated_user
app.state.normalize_role = _normalize_role
app.state.role_instructor = ROLE_INSTRUCTOR
app.state.role_system_admin = ROLE_SYSTEM_ADMIN
app.state.db_path = DB_PATH
app.state.get_word_score_history = _get_word_score_history
app.state.get_sentence_score_history = _get_sentence_score_history
app.state.find_vocab_id_by_word = _find_vocab_id_by_word

# TTS hooks/config for routers
app.state.logger = logger
app.state.tts_backend = TTS_BACKEND
app.state.openai_client = client
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
app.state.load_speechpro_precomputed_sentences = (
    lambda: globals()["load_speechpro_precomputed_sentences"]()
)
app.state.find_precomputed_sentence = lambda text: globals()[
    "find_precomputed_sentence"
](text)
app.state.generate_pronunciation_feedback = lambda text, score_result: globals()[
    "_generate_pronunciation_feedback"
](text, score_result)
app.state.model_backend = MODEL_BACKEND
app.state.ollama_model = OLLAMA_MODEL
app.state.gemini_model = GEMINI_MODEL
app.state.openai_model = OPENAI_MODEL
app.state.stt_backend = STT_BACKEND

# 특정 호스트(moj.ngrok.app) 루트 접근 시 speechpro-practice로 리다이렉트
@app.middleware("http")
async def redirect_speechpro_practice(request: Request, call_next):
    host = request.headers.get("host", "")
    if host.startswith("moj.ngrok.app") and request.url.path in ("", "/"):
        return RedirectResponse(url="/speechpro-practice")
    return await call_next(request)

# CORS 설정
# 개발 환경: localhost 허용
# 프로덕션 환경: ngrok 도메인 허용
allowed_origins = [
    "http://localhost:9000",
    "http://127.0.0.1:9000",
    "https://brainlessly-unequestrian-ember.ngrok-free.dev",
    # 개발 중 다른 포트에서 테스트 시 필요하면 추가
    "http://localhost:5173",  # Vite dev server (if needed)
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
                token for token, session in active_sessions.items()
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
                logger.info(f"[SESSION_CLEANUP] Removed {len(expired_tokens)} expired sessions")
            else:
                logger.debug(f"[SESSION_CLEANUP] No expired sessions found. Active: {len(active_sessions)}")
                
        except Exception as e:
            logger.error(f"[SESSION_CLEANUP] Error: {e}", exc_info=True)

# ==========================================
# 학습 데이터 로드 헬퍼 함수
# ==========================================
def load_json_data(filename):
    """Load JSON data from data/ directory"""
    try:
        with open(f"data/{filename}", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return []


@lru_cache(maxsize=1)
def load_speechpro_precomputed_sentences():
    """Load precomputed SpeechPro sentences (with syllables/FST) from CSV"""
    path = "data/sp_ko_questions.csv"
    sentences = []

    if not os.path.exists(path):
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

                sentences.append({
                    "id": 1000 + base_id if base_id else order,
                    "order": order,
                    "sentenceKr": sentence_kr,
                    "sentenceEn": "",
                    "level": "초급",
                    "difficulty": "SpeechPro",
                    "category": "프리셋",
                    "tags": ["speechpro", "preset"],
                    "tips": "SpeechPro 서버의 프리셋 문장입니다.",
                    "syll_ltrs": row.get("syll_ltrs", ""),
                    "syll_phns": row.get("syll_phns", ""),
                    "fst": row.get("fst", ""),
                    "source": "precomputed"
                })
    except Exception as e:
        print(f"Error loading {path}: {e}")

    # Order by given order, then id
    sentences.sort(key=lambda s: (s.get("order", 0), s.get("id", 0)))
    return sentences


def find_precomputed_sentence(text: str):
    """Find precomputed sentence entry by normalized text"""
    normalized = normalize_spaces(text or "")
    for item in load_speechpro_precomputed_sentences():
        if normalize_spaces(item.get("sentenceKr", "")) == normalized:
            return item
    return None


async def _generate_pronunciation_feedback(text: str, score_result) -> str:
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
                    speechpro_info += f"\n- 정확 발음: {sent.get('accuracy_percentage', 0):.1f}%"
                if sent.get("completeness_percentage"):
                    speechpro_info += f"\n- 완성도: {sent.get('completeness_percentage', 0):.1f}%"
        
        # FluencyPro 분석 데이터 추출
        fluency_info = ""
        if details.get("fluency"):
            f = details["fluency"]
            try:
                correct = f.get('correct_syllables', f.get('correct syllable count', 0)) or 0
                total = f.get('total_syllables', f.get('syllable count', 0)) or 0
                rate = f.get('speech_rate', f.get('speech rate', 0)) or 0
                
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
                            word_scores.append({
                                "text": word["text"],
                                "score": round(word.get("score", 0))
                            })
        
        word_summary = ""
        if word_scores:
            low_words = [w for w in word_scores if w["score"] < 70]
            high_words = [w for w in word_scores if w["score"] >= 90]
            
            if low_words:
                word_summary += "\n잘 못한 발음: " + ", ".join([f"{w['text']}({w['score']}점)" for w in low_words[:3]])
            if high_words:
                word_summary += "\n잘한 발음: " + ", ".join([f"{w['text']}({w['score']}점)" for w in high_words[:3]])

        prompt = f"""당신은 한국어 발음 교육 전문가이자 친절한 코치입니다. 아래 발음 평가 결과를 바탕으로 학습자에게 피드백을 작성해주세요.

[평가 대상 문장]
{text}

[종합 평가 결과]
- 전체 점수: {overall_score}점{speechpro_info}
{fluency_info}
{word_summary}

[출력 형식 - 아래 마커를 정확히 그대로 사용할 것]
[SUMMARY]
(학습자의 현재 상태를 1~2문장으로 요약)

[STRENGTHS]
• (잘한 점 3개 이상, 각 항목을 • 로 시작)

[IMPROVEMENTS]
• (개선이 필요한 부분 3개 이상, 어려웠던 단어/음절 중심으로, 각 항목을 • 로 시작)

[TIPS]
• (바로 따라할 수 있는 연습 방법 3개 이상, 각 항목을 • 로 시작)

[SCORE]
전체: {overall_score}/100
(정확 발음/완성도/유창성 등 핵심 수치 2~3개 추가)

[작성 규칙]
- 모든 피드백 내용은 반드시 한국어(Korean)로만 작성하세요. (영어 단어, 문장, 설명 등을 절대 사용하지 말 것)
- 학습자를 따뜻하게 격려하되 과장하지 말 것
- 문장 안에서 중요 단어/표현 강조 등을 위한 **볼드** 및 마크다운 기호(*)를 절대 사용하지 말 것 (순수하게 텍스트만 사용할 것)
- 마커([SUMMARY] 등) 와 • 이외의 마크다운(#, ##, >, -, 1.) 금지
- 코드블록, JSON, 표 금지
- 각 섹션마다 내용을 충분히 상세하게 작성할 것"""

        if MODEL_BACKEND == "ollama":
            payload = {
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            }
            
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
                    {"role": "system", "content": "당신은 한국어 발음 교육 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2500
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
                    )
                )
                if response.candidates and len(response.candidates) > 0:
                    feedback = response.text.strip()
                else:
                    print("[AI Feedback] Gemini - No candidates returned (likely blocked)")
                    return None
            except Exception as ge:
                print(f"[AI Feedback] Gemini error: {ge}")
                return None
        
        else:
            return None
        
        # Remove obvious JSON artifacts if feedback is a string
        if isinstance(feedback, str):
            feedback = re.sub(r'\{.*?\}', '', feedback, flags=re.DOTALL)
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
@app.get("/")
def landing_page(request: Request):
    """기본 랜딩 페이지"""
    return templates.TemplateResponse("landing.html", {"request": request})

@app.get("/landing")
def landing_page_1(request: Request):
    """랜딩 페이지 1"""
    return templates.TemplateResponse("landing.html", {"request": request})

@app.get("/landing-2")
def landing_page_2(request: Request):
    """랜딩 페이지 2"""
    return templates.TemplateResponse("landing-2.html", {"request": request})

@app.get("/lobby")
def lobby_page(request: Request):
    """학습 로비 페이지"""
    return templates.TemplateResponse("lobby.html", {"request": request})

@app.get("/home")
def home_dashboard(request: Request):
    """기존 대시보드 홈페이지 (백업 경로)"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/learning")
def learning_page(request: Request):
    """기존 AI 학습 도구 (콘텐츠 생성, 발음 교정, 작문 테스트)"""
    return templates.TemplateResponse("learning.html", {"request": request})

@app.get("/content-generation")
def content_generation_page(request: Request):
    """맞춤형 교재 생성 페이지"""
    return templates.TemplateResponse("content-generation.html", {"request": request})

@app.get("/pronunciation-check")
def pronunciation_check_page(request: Request):
    """발음 교정 페이지"""
    return templates.TemplateResponse("pronunciation-check.html", {"request": request})

@app.get("/fluency-test")
def fluency_test_page(request: Request):
    """한국어 작문 테스트 페이지"""
    return templates.TemplateResponse("fluency-test.html", {"request": request})

@app.get("/pronunciation-correction")
def pronunciation_correction_page(request: Request):
    """발음 교정 페이지"""
    return templates.TemplateResponse("pronunciation-correction.html", {"request": request})

@app.get("/word-puzzle")
def word_puzzle_page(request: Request):
    """단어 순서 맞추기 게임"""
    return templates.TemplateResponse("word-puzzle.html", {"request": request})

@app.get("/initial-quiz")
def initial_quiz_page(request: Request):
    """초성 퀴즈 페이지"""
    return templates.TemplateResponse("initial-quiz.html", {"request": request})

@app.get("/card-matching-game")
def card_matching_game_page(request: Request):
    """카드 짝 맞추기 페이지"""
    return templates.TemplateResponse(
        "card-matching-game.html",
        {"request": request},
    )

@app.get("/word-matching-game")
def word_matching_game_page(request: Request):
    """단어맞추기 게임 페이지"""
    return templates.TemplateResponse("word-matching-game.html", {"request": request})

@app.get("/word-list")
def word_list_page(request: Request):
    """학습 단어 목록 페이지"""
    return templates.TemplateResponse("word-list.html", {"request": request})

@app.get("/krdict")
def krdict_page(request: Request):
    """사전 검색 페이지"""
    return templates.TemplateResponse("krdict-search.html", {"request": request})

@app.get("/synonym-antonym-game")
def synonym_antonym_game_page(request: Request):
    """동의어/반의어 찾기 게임 페이지"""
    return templates.TemplateResponse("synonym-antonym-game.html", {"request": request})

@app.get("/daily-expression")
def daily_expression_page(request: Request):
    """오늘의 한국어 표현 카드 슬라이더"""
    return templates.TemplateResponse("daily-expression.html", {"request": request})

@app.get("/vocab-garden")
def vocab_garden_page(request: Request):
    """어휘 정원 (Vocabulary Garden)"""
    return templates.TemplateResponse("vocab-garden.html", {"request": request})

@app.get("/typing-game")
def typing_game_page(request: Request):
    """타이핑 게임"""
    return templates.TemplateResponse("typing-game.html", {"request": request})

@app.get("/listening-dictation")
def listening_dictation_page(request: Request):
    """듣고 받아쓰기"""
    return templates.TemplateResponse("listening-dictation.html", {"request": request})

@app.get("/speed-quiz")
def speed_quiz_page(request: Request):
    """스피드 퀴즈"""
    return templates.TemplateResponse("speed-quiz.html", {"request": request})

@app.get("/folktales")
def folktales_page(request: Request):
    """전래동화 읽기"""
    return templates.TemplateResponse("folktales.html", {"request": request})

@app.get("/cultural-expressions")
def cultural_expressions_page(request: Request):
    """문화 표현 학습"""
    return templates.TemplateResponse("cultural-expressions.html", {"request": request})

@app.get("/pronunciation-practice")
def pronunciation_practice_page(request: Request):
    """발음 연습 (ELSA Speak 스타일 2-Step: Listen → Speak)"""
    return templates.TemplateResponse("pronunciation-practice.html", {"request": request})

@app.get("/pronunciation-stages")
def pronunciation_stages_page(request: Request):
    """단계별 발음 학습"""
    return templates.TemplateResponse("pronunciation-stages.html", {"request": request})

@app.get("/pronunciation-rules")
def pronunciation_rules_page(request: Request):
    """발음 규칙 학습"""
    return templates.TemplateResponse("pronunciation-rules.html", {"request": request})

@app.get("/curriculum")
def curriculum_page(request: Request):
    """학습 단계 선택하기 페이지"""
    return templates.TemplateResponse("curriculum.html", {"request": request})

@app.get("/curriculum/intro-basic")
def curriculum_intro_basic_page(request: Request):
    """입문-기본 학습 상세 페이지"""
    return templates.TemplateResponse("curriculum-intro-basic.html", {"request": request})

@app.get("/pronunciation-learning")
def pronunciation_learning_page(request: Request):
    """발음 학습 허브 페이지"""
    return templates.TemplateResponse("word-pronunciation.html", {"request": request})

@app.get("/word-pronunciation")
def word_pronunciation_page(request: Request):
    """단어 발음 학습"""
    return templates.TemplateResponse("word-pronunciation.html", {"request": request})

@app.get("/signup")
def signup_page(request: Request):
    """회원가입 페이지"""
    return templates.TemplateResponse("signup.html", {"request": request})

@app.get("/stt-api-test")
def stt_api_test_page(request: Request):
    """STT API 다중 테스트 페이지"""
    return templates.TemplateResponse("stt-multi-test.html", {"request": request})

@app.get("/api-test")
def api_test_page(request: Request):
    """관리자 API 테스트 도구 (클라이언트 측 인증 검사)"""
    # Note: Token validation happens on client-side (JavaScript)
    # Client will redirect to /admin/login if not authenticated
    return templates.TemplateResponse("api-test.html", {"request": request})

@app.get("/media-generation")
def media_generation_page(request: Request):
    """상황별 콘텐츠 생성"""
    return templates.TemplateResponse("media-generation.html", {"request": request})

@app.get("/sitemap")
def sitemap_page(request: Request):
    """사이트맵 페이지"""
    return templates.TemplateResponse("sitemap.html", {"request": request})

@app.get("/login")
def login_page(request: Request):
    """로그인 페이지"""
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/mypage")
def mypage(request: Request):
    """사용자 프로필 페이지"""
    return templates.TemplateResponse("mypage.html", {"request": request})

@app.get("/learning-progress")
def learning_progress(request: Request):
    """학습 진도 대시보드"""
    return templates.TemplateResponse("learning-progress.html", {"request": request})


@app.get("/dashboard")
def learning_dashboard(request: Request):
    """학습 대시보드 (alias)"""
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/change-password")
def change_password_page(request: Request):
    """비밀번호 변경 페이지"""
    return templates.TemplateResponse("change-password.html", {"request": request})


@app.get("/admin/login")
def admin_login_page(request: Request):
    """관리자 로그인 페이지"""
    return templates.TemplateResponse("admin-login.html", {"request": request})


@app.get("/admin/dashboard")
def admin_dashboard_page(request: Request):
    """관리자 대시보드 페이지 (클라이언트 측 인증 검사)"""
    # Note: Token validation happens on client-side (JavaScript)
    # API endpoints enforce _require_admin for actual operations
    return templates.TemplateResponse("admin-dashboard.html", {"request": request})


@app.get("/admin/users")
def admin_users_page(request: Request):
    """관리자 사용자 관리 페이지 (클라이언트 측 인증 검사)"""
    # Note: Token validation happens on client-side (JavaScript)
    # API endpoints enforce _require_admin for actual operations
    return templates.TemplateResponse("admin-users.html", {"request": request})


@app.get("/admin/words")
def admin_words_page(request: Request):
    """관리자 단어 관리 페이지"""
    return templates.TemplateResponse("admin-words.html", {"request": request})


@app.get("/admin/recordings")
def admin_recordings_page(request: Request):
    """관리자 녹음 관리 페이지"""
    return templates.TemplateResponse("admin-recordings.html", {"request": request})
    return templates.TemplateResponse("admin-dashboard.html", {"request": request})

@app.get("/admin/learner-status")
def admin_learner_status_page(request: Request):
    """학습자 학습 상태 페이지 (클라이언트 측 인증 검사)"""
    return templates.TemplateResponse(
        "admin-learner-status.html", {"request": request}
    )

@app.get("/admin")
def admin_shell_page(request: Request):
    """관리자 셸: 좌측 사이드 패널 + 우측 콘텐츠 프레임"""
    return templates.TemplateResponse("admin.html", {"request": request})
@app.get("/admin/analytics")
def admin_analytics_page(request: Request):
    """관리자 통계 분석 페이지"""
    return templates.TemplateResponse("admin-analytics.html", {"request": request})


@app.get("/admin/content")
def admin_content_page(request: Request):
    """관리자 AI 콘텐츠 관리 페이지"""
    return templates.TemplateResponse("admin-content.html", {"request": request})


@app.get("/admin/api")
def admin_api_page(request: Request):
    """관리자 API 설정 페이지"""
    return templates.TemplateResponse("admin-api.html", {"request": request})


@app.get("/admin/system")
def admin_system_page(request: Request):
    """관리자 시스템 설정 페이지"""
    return templates.TemplateResponse("admin-system.html", {"request": request})


@app.get("/admin/logs")
def admin_logs_page(request: Request):
    """관리자 로그 모니터링 페이지 (클라이언트 측 인증 검사)"""
    # Note: Token validation happens on client-side (JavaScript)
    # API endpoints enforce _require_admin for actual operations
    return templates.TemplateResponse("admin-logs.html", {"request": request})


@app.get("/admin/settings")
def admin_settings_page(request: Request):
    """관리자 설정 페이지 (클라이언트 측 인증 검사)"""
    # Note: Token validation happens on client-side (JavaScript)
    # API endpoints enforce _require_admin for actual operations
    return templates.TemplateResponse("admin-settings.html", {"request": request})


@app.get("/admin/rag")
def admin_rag_page(request: Request):
    """RAG 설정 페이지 (클라이언트 측 인증 검사)"""
    return templates.TemplateResponse("admin-rag.html", {"request": request})

# ------------------------------------------
# 회원가입 (실제 계정 생성)
# ------------------------------------------
@app.post("/api/signup")
async def signup(request: Request):
    payload = await request.json()
    user = _store_user_signup(payload)

    # Auto-login: Create session token
    token = _create_session_token(user["id"], user["email"], user["is_admin"])

    return {
        "success": True,
        "token": token,
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
    }


@app.post("/api/landing-intake")
async def landing_intake(request: Request):
    """Backward compatibility: reuse signup handler."""
    return await signup(request)


# ------------------------------------------
# 로그인 (계정 인증)
# ------------------------------------------
@app.post("/api/login")
async def login(request: Request):
    """사용자 로그인: 이메일과 비밀번호로 인증."""
    payload = await request.json()
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    if not email or not password:
        raise HTTPException(status_code=400, detail="이메일과 비밀번호를 입력하세요.")

    user = _get_user_by_email(email)
    if not user or not _verify_password(user["password_hash"], password):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")

    # Create session token
    token = _create_session_token(user["id"], user["email"], bool(user.get("is_admin")))
    
    # Log successful login
    client_host = request.client.host if request.client else "Unknown"
    logger.info(
        "[LOGIN] user=%s email=%s role=%s ip=%s",
        user["nickname"],
        user["email"],
        _normalize_role(user.get("role"), user.get("is_admin")),
        client_host,
    )
    
    role = _normalize_role(user.get("role"), user.get("is_admin"))

    return {
        "success": True,
        "token": token,
        "email": user["email"],
        "name": user["name"],
        "is_admin": role == ROLE_SYSTEM_ADMIN,
        "role": role,
    }


@app.post("/api/log/guest-login")
async def log_guest_login(request: Request):
    """게스트 로그인 로그 기록"""
    payload = await request.json()
    nickname = payload.get("nickname", "Unknown")
    timestamp = payload.get("timestamp", "")
    user_agent = payload.get("userAgent", "")
    language = payload.get("language", "")
    client_host = request.client.host if request.client else "Unknown"
    
    logger.info(
        "[GUEST_LOGIN] user=%s ip=%s time=%s",
        nickname,
        client_host,
        timestamp,
    )
    logger.info(
        "[GUEST_INFO] user=%s userAgent=%s language=%s",
        nickname,
        user_agent,
        language,
    )
    
    return {"success": True, "message": "Guest login logged"}


@app.post("/api/log/activity")
async def log_user_activity(request: Request):
    """사용자 활동 로그 기록"""
    payload = await request.json()
    nickname = payload.get("nickname", "Unknown")
    action = payload.get("action", "")
    page = payload.get("page", "")
    details = payload.get("details", {})
    client_host = request.client.host if request.client else "Unknown"
    
    logger.info(
        "[ACTIVITY] user=%s action=%s page=%s ip=%s",
        nickname,
        action,
        page,
        client_host,
    )
    if details:
        logger.info("[ACTIVITY_DETAILS] %s", json.dumps(details, ensure_ascii=False))
    
    return {"success": True, "message": "Activity logged"}


@app.post("/api/attendance/check-in")
async def attendance_check_in(request: Request):
    """오늘 출석 체크."""
    user = _require_authenticated_user(request)
    today = datetime.now().date().isoformat()
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO attendance (user_id, date) VALUES (?, ?)",
            (user["id"], today),
        )
        conn.commit()
        checked_in = cursor.rowcount > 0
        streak = _compute_attendance_streak(conn, user["id"])
        logger.info(
            "[ATTENDANCE] user=%s email=%s date=%s status=%s ip=%s",
            user.get("nickname"),
            user.get("email"),
            today,
            "checked_in" if checked_in else "already_checked",
            request.client.host if request.client else "Unknown",
        )
        return {
            "success": True,
            "date": today,
            "checked_in": checked_in,
            "streak": streak,
        }
    finally:
        conn.close()


@app.get("/api/attendance/month")
async def attendance_month(request: Request, year: int, month: int):
    """월별 출석 정보 조회."""
    user = _require_authenticated_user(request)
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="유효한 월을 입력하세요.")
    start_date = datetime(year, month, 1).date()
    if month == 12:
        end_date = datetime(year + 1, 1, 1).date()
    else:
        end_date = datetime(year, month + 1, 1).date()

    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT date FROM attendance
            WHERE user_id = ? AND date >= ? AND date < ?
            """,
            (user["id"], start_date.isoformat(), end_date.isoformat()),
        )
        rows = cursor.fetchall()
        days = []
        for (date_str,) in rows:
            try:
                day = int(date_str.split("-")[2])
                days.append(day)
            except Exception:
                continue
        days.sort()
        streak = _compute_attendance_streak(conn, user["id"])
        return {
            "success": True,
            "year": year,
            "month": month,
            "days": days,
            "streak": streak,
        }
    finally:
        conn.close()


@app.post("/api/logout")
async def logout(request: Request):
    """사용자 로그아웃."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        token = request.cookies.get("session_token", "")
    
    if token:
        session = _parse_session_token(token)
        if session:
            logger.info(f"[LOGOUT] user_id={session['user_id']} email={session['email']}")
        
        # Remove from active_sessions
        if token in active_sessions:
            del active_sessions[token]
    
    return {"success": True, "message": "로그아웃되었습니다."}


# ------------------------------------------
# 사용자 프로필 (mypage)
# ------------------------------------------
@app.get("/api/user/profile")
async def get_user_profile(request: Request):
    """로그인한 사용자의 프로필 조회."""
    user = _require_authenticated_user(request)

    # Remove sensitive fields
    user.pop("password_hash", None)
    return {"success": True, "user": user}


@app.post("/api/user/profile/update")
async def update_user_profile(request: Request):
    """사용자 프로필 업데이트 (비밀번호 제외)."""
    user = _require_authenticated_user(request)
    payload = await request.json()
    user_id = user["id"]
    
    # Update allowed fields
    nickname = (payload.get("nickname") or "").strip()
    native_lang = (payload.get("native_lang") or "").strip()
    affiliation = (payload.get("affiliation") or "").strip()
    time_pref = (payload.get("time_pref") or "").strip()
    interests = _normalize_interests(payload.get("interests"))
    goal = (payload.get("goal") or "").strip()
    exam_level = (payload.get("exam_level") or "").strip()
    reason = (payload.get("reason") or "").strip()
    style = (payload.get("style") or "").strip()
    
    if nickname and len(nickname) > 50:
        raise HTTPException(status_code=400, detail="닉네임은 50자 이하여야 합니다.")
    
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        updates = []
        values = []
        
        if nickname:
            updates.append("nickname = ?")
            values.append(nickname)
        if native_lang:
            updates.append("native_lang = ?")
            values.append(native_lang)
        if affiliation:
            updates.append("affiliation = ?")
            values.append(affiliation)
        if time_pref:
            updates.append("time_pref = ?")
            values.append(time_pref)
        updates.append("interests = ?")
        values.append(json.dumps(interests, ensure_ascii=False))
        if goal:
            updates.append("goal = ?")
            values.append(goal)
        if exam_level:
            updates.append("exam_level = ?")
            values.append(exam_level)
        if reason:
            updates.append("reason = ?")
            values.append(reason)
        if style:
            updates.append("style = ?")
            values.append(style)
        
        values.append(user_id)
        
        cursor.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
            values
        )
        conn.commit()
    finally:
        conn.close()
    
    # Return updated user
    updated = _get_user_by_id(user_id)
    updated.pop("password_hash", None)
    return {"success": True, "user": updated}


# ------------------------------------------
# 관리자 API (스켈레톤)
# ------------------------------------------
@app.get("/api/admin/summary")
async def admin_summary(request: Request):
    """관리자 대시보드를 위한 간단한 요약 정보."""
    admin = _require_role(request, {ROLE_INSTRUCTOR, ROLE_SYSTEM_ADMIN})
    stats = _get_user_stats()
    logger.info(f"[ADMIN_SUMMARY] {admin['email']} accessed summary")
    return {
        "success": True,
        "admin": {
            "email": admin["email"],
            "nickname": admin["nickname"],
        },
        "stats": stats,
    }

def _read_last_log_lines(path: Path, limit: int = 50000) -> List[str]:
    if limit <= 0:
        return []
    if not path.exists():
        return []
    from collections import deque

    lines = deque(maxlen=limit)
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line:
                lines.append(line.rstrip("\n"))
    return list(lines)


_LOG_TS_FORMAT = "%Y-%m-%d %H:%M:%S,%f"
_LOGIN_RE = re.compile(r"\[LOGIN\]\s+user=(?P<user>\S+)\s+email=(?P<email>\S+)\s+role=(?P<role>\S+)\s+ip=(?P<ip>\S+)")
_PAGE_VIEW_RE = re.compile(r"\[PAGE_VIEW\]\s+user=(?P<user>\S+)\s+email=(?P<email>\S*)\s+role=(?P<role>\S*)\s+page=(?P<page>\S+)\s+ip=(?P<ip>\S+)")


def _extract_log_timestamp(line: str) -> str:
    if not line:
        return ""
    # logging.basicConfig format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    # e.g., "2025-12-30 17:01:02,123 - __main__ - INFO - [LOGIN] ..."
    try:
        ts_str = line.split(" - ", 1)[0].strip()
        dt = datetime.strptime(ts_str, _LOG_TS_FORMAT)
        return dt.isoformat(sep=" ", timespec="seconds")
    except Exception:
        return ""


def _last_activity_from_logs(nicknames: List[str], limit: int = 50000) -> Dict[str, Dict]:
    log_file = Path("logs/detailed.log")
    recent_lines = _read_last_log_lines(log_file, limit=limit)
    wanted = {n for n in (nicknames or []) if n}
    if not wanted or not recent_lines:
        return {}

    remaining_login = set(wanted)
    remaining_page = set(wanted)
    result: Dict[str, Dict] = {n: {} for n in wanted}

    for line in reversed(recent_lines):
        if remaining_login and "[LOGIN]" in line:
            m = _LOGIN_RE.search(line)
            if m:
                user = m.group("user")
                if user in remaining_login:
                    result[user]["last_login_at"] = _extract_log_timestamp(line)
                    remaining_login.remove(user)

        if remaining_page and "[PAGE_VIEW]" in line:
            m = _PAGE_VIEW_RE.search(line)
            if m:
                user = m.group("user")
                if user in remaining_page:
                    result[user]["last_page_view_at"] = _extract_log_timestamp(line)
                    result[user]["last_page"] = m.group("page")
                    remaining_page.remove(user)

        if not remaining_login and not remaining_page:
            break

    return result


@app.get("/api/admin/learner-status")
async def admin_learner_status(request: Request, q: str = "", limit: int = 200):
    """교수/시스템관리자: 학습자 상태 요약."""
    _require_role(request, {ROLE_INSTRUCTOR, ROLE_SYSTEM_ADMIN})

    limit = max(1, min(int(limit or 200), 500))
    q = (q or "").strip()
    today = datetime.now().date().isoformat()
    since_7d_dt = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    since_7d_date = (datetime.now().date() - timedelta(days=6)).isoformat()

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        where = "WHERE role = ?"
        params: list = [ROLE_LEARNER]
        if q:
            where += " AND (LOWER(nickname) LIKE ? OR LOWER(email) LIKE ?)"
            like = f"%{q.lower()}%"
            params.extend([like, like])

        cursor.execute(
            f"""
            SELECT id, email, nickname, created_at
            FROM users
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (*params, limit),
        )
        users = [dict(row) for row in cursor.fetchall()]
        if not users:
            return {
                "success": True,
                "stats": {"learners": 0, "today_attendance": 0, "word_7d": 0, "sentence_7d": 0},
                "users": [],
            }

        user_ids = [u["id"] for u in users]
        nicknames = [u.get("nickname") or "" for u in users]

        # Attendance aggregates
        placeholders = ",".join(["?"] * len(user_ids))
        cursor.execute(
            f"""
            SELECT
              user_id,
              MAX(date) AS last_date,
              SUM(CASE WHEN date = ? THEN 1 ELSE 0 END) AS today_cnt,
              SUM(CASE WHEN date >= ? THEN 1 ELSE 0 END) AS days_7d
            FROM attendance
            WHERE user_id IN ({placeholders})
            GROUP BY user_id
            """,
            (today, since_7d_date, *user_ids),
        )
        attendance_rows = {row["user_id"]: dict(row) for row in cursor.fetchall()}

        # Word score aggregates
        cursor.execute(
            f"""
            SELECT
              user_id,
              COUNT(*) AS total,
              MAX(created_at) AS last_at,
              SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS cnt_7d
            FROM word_score_history
            WHERE user_id IN ({placeholders})
            GROUP BY user_id
            """,
            (since_7d_dt, *user_ids),
        )
        word_rows = {row["user_id"]: dict(row) for row in cursor.fetchall()}

        # Sentence score aggregates
        cursor.execute(
            f"""
            SELECT
              user_id,
              COUNT(*) AS total,
              MAX(created_at) AS last_at,
              SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS cnt_7d
            FROM sentence_score_history
            WHERE user_id IN ({placeholders})
            GROUP BY user_id
            """,
            (since_7d_dt, *user_ids),
        )
        sentence_rows = {row["user_id"]: dict(row) for row in cursor.fetchall()}

        # Streak per user (small N; compute in python using helper)
        streaks = {uid: _compute_attendance_streak(conn, uid) for uid in user_ids}

    finally:
        conn.close()

    last_activity = _last_activity_from_logs(nicknames, limit=50000)

    merged_users = []
    today_attendance = 0
    total_word_7d = 0
    total_sentence_7d = 0

    for u in users:
        uid = u["id"]
        a = attendance_rows.get(uid) or {}
        w = word_rows.get(uid) or {}
        s = sentence_rows.get(uid) or {}
        la = last_activity.get(u.get("nickname") or "", {})

        today_cnt = int(a.get("today_cnt") or 0)
        today_attendance += 1 if today_cnt > 0 else 0
        total_word_7d += int(w.get("cnt_7d") or 0)
        total_sentence_7d += int(s.get("cnt_7d") or 0)

        merged_users.append(
            {
                "id": uid,
                "email": u.get("email") or "",
                "nickname": u.get("nickname") or "",
                "created_at": u.get("created_at") or "",
                "attendance_streak": int(streaks.get(uid) or 0),
                "last_attendance_date": a.get("last_date") or "",
                "word_total": int(w.get("total") or 0),
                "word_last_at": w.get("last_at") or "",
                "sentence_total": int(s.get("total") or 0),
                "sentence_last_at": s.get("last_at") or "",
                "last_login_at": la.get("last_login_at") or "",
                "last_page_view_at": la.get("last_page_view_at") or "",
                "last_page": la.get("last_page") or "",
            }
        )

    return {
        "success": True,
        "stats": {
            "learners": len(merged_users),
            "today_attendance": today_attendance,
            "word_7d": total_word_7d,
            "sentence_7d": total_sentence_7d,
        },
        "users": merged_users,
    }


@app.get("/api/admin/logs-tail")
async def admin_logs_tail(request: Request, lines: int = 100, level: str = "", search: str = ""):
    """관리자용 최근 로그 조회 (필터링 포함)."""
    admin = _require_role(request, {ROLE_SYSTEM_ADMIN})
    
    log_file = Path("logs/detailed.log")
    if not log_file.exists():
        return {"success": True, "logs": [], "count": 0, "total_available": 0}
    
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        
        # Filter logs
        filtered = []
        for line in all_lines:
            # Level filter
            if level and f"[{level.upper()}]" not in line and f" {level.upper()} " not in line:
                continue
            # Search filter
            if search and search.lower() not in line.lower():
                continue
            filtered.append(line)
        
        # Get last N filtered lines
        recent = filtered[-min(lines, len(filtered)):]
        logger.info(f"[ADMIN_LOGS] {admin['email']} retrieved {len(recent)} log lines (level={level}, search={search})")
        
        return {
            "success": True,
            "logs": recent,
            "count": len(recent),
            "total_available": len(all_lines),
            "total_filtered": len(filtered),
        }
    except Exception as e:
        logger.error(f"Failed to read logs: {e}")
        return {"success": False, "detail": str(e)}


@app.get("/api/admin/analytics")
async def admin_analytics(request: Request):
    """관리자 통계 분석 데이터."""
    _require_role(request, {ROLE_INSTRUCTOR, ROLE_SYSTEM_ADMIN})

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        # Ensure learning progress tables exist
        try:
            learning_service._init_db()
        except Exception:
            pass

        cursor.execute("SELECT COUNT(*) AS n FROM users")
        total_users = int(cursor.fetchone()["n"])

        since_date = (datetime.now().date() - timedelta(days=6)).isoformat()
        cursor.execute(
            """
            SELECT COUNT(DISTINCT user_id) AS n
            FROM user_learning_progress
            WHERE date >= ?
            """,
            (since_date,),
        )
        active_users = int(cursor.fetchone()["n"] or 0)

        cursor.execute(
            """
            SELECT
              AVG(total_learning_time) AS avg_minutes,
              AVG(NULLIF(pronunciation_avg_score, 0)) AS avg_score
            FROM user_learning_progress
            WHERE date >= ?
            """,
            (since_date,),
        )
        row = cursor.fetchone() or {}
        avg_minutes = float(row["avg_minutes"] or 0)
        avg_score = float(row["avg_score"] or 0)
        avg_hours = avg_minutes / 60.0 if avg_minutes else 0.0

        # Daily activity counts for last 7 days
        cursor.execute(
            """
            SELECT date,
                   SUM(pronunciation_practice_count + words_learned + sentences_learned) AS cnt
            FROM user_learning_progress
            WHERE date >= ?
            GROUP BY date
            """,
            (since_date,),
        )
        activity_map = {row["date"]: int(row["cnt"] or 0) for row in cursor.fetchall()}
        activity = []
        for i in range(7):
            d = (datetime.now().date() - timedelta(days=6 - i)).isoformat()
            activity.append({"date": d, "count": activity_map.get(d, 0)})

        # Difficulty distribution from vocabulary.json
        vocab = load_json_data("vocabulary.json") or []
        if not isinstance(vocab, list):
            vocab = []
        dist: dict[str, int] = {}
        for item in vocab:
            if not isinstance(item, dict):
                continue
            key = (
                item.get("level")
                or item.get("topikLevel")
                or item.get("kiipLevel")
                or "기타"
            )
            key = str(key)
            dist[key] = dist.get(key, 0) + 1
        difficulty = [
            {"label": k, "count": v} for k, v in sorted(dist.items(), key=lambda x: x[0])
        ]

        # Per-user learning table
        cursor.execute(
            """
            SELECT user_id,
                   SUM(pronunciation_practice_count + words_learned + sentences_learned) AS learning_count,
                   AVG(NULLIF(pronunciation_avg_score, 0)) AS avg_score,
                   MAX(date) AS last_learning
            FROM user_learning_progress
            GROUP BY user_id
            """
        )
        progress_rows = {str(row["user_id"]): dict(row) for row in cursor.fetchall()}

        cursor.execute(
            "SELECT id, nickname, email FROM users WHERE role = ?",
            (ROLE_LEARNER,),
        )
        users = cursor.fetchall()
        table = []
        for user in users:
            uid = str(user["id"])
            nick = user["nickname"] or uid
            email = user["email"] or ""
            progress = progress_rows.get(uid) or progress_rows.get(nick) or {}
            table.append(
                {
                    "user": f"{nick} ({email})" if email else nick,
                    "learning_count": int(progress.get("learning_count") or 0),
                    "avg_score": round(float(progress.get("avg_score") or 0), 1),
                    "last_learning": progress.get("last_learning") or "-",
                }
            )

        return {
            "success": True,
            "stats": {
                "total_users": total_users,
                "active_users": active_users,
                "avg_study_hours": round(avg_hours, 2),
                "avg_score": round(avg_score, 2),
            },
            "activity": activity,
            "difficulty": difficulty,
            "table": table,
        }
    finally:
        conn.close()


@app.get("/api/admin/users")
async def admin_users_list(request: Request, skip: int = 0, limit: int = 50):
    """관리자용 사용자 목록 조회."""
    admin = _require_role(request, {ROLE_INSTRUCTOR, ROLE_SYSTEM_ADMIN})
    
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get total count
        cursor.execute("SELECT COUNT(*) FROM users")
        total = cursor.fetchone()[0]
        
        # Get paginated users
        cursor.execute(
            """
            SELECT id, email, name, nickname, is_admin, role, created_at
            FROM users
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, skip)
        )
        users = [dict(row) for row in cursor.fetchall()]
        for user in users:
            user["role"] = _normalize_role(user.get("role"), user.get("is_admin"))
        
        logger.info(f"[ADMIN_USERS] {admin['email']} retrieved {len(users)} users")
        
        return {
            "success": True,
            "users": users,
            "total": total,
            "skip": skip,
            "limit": limit,
        }
    finally:
        conn.close()


@app.get("/api/admin/words")
async def admin_words_list(request: Request, q: str = "", skip: int = 0, limit: int = 200):
    """관리자용 단어 목록 (vocabulary.json 기반)."""
    _require_role(request, {ROLE_INSTRUCTOR, ROLE_SYSTEM_ADMIN})
    skip = max(0, int(skip or 0))
    limit = max(1, min(int(limit or 200), 500))
    q = (q or "").strip().lower()

    vocab = load_json_data("vocabulary.json") or []
    if not isinstance(vocab, list):
        vocab = []

    def matches(item: dict) -> bool:
        if not q:
            return True
        fields = [
            str(item.get("word", "")),
            str(item.get("meaningKo", "")),
            str(item.get("meaning", "")),
            str(item.get("meaningEn", "")),
            str(item.get("roman", "")),
            str(item.get("category", "")),
            str(item.get("topic", "")),
            str(item.get("topikLevel", "")),
        ]
        hay = " ".join(fields).lower()
        return q in hay

    filtered = [item for item in vocab if isinstance(item, dict) and matches(item)]
    total = len(filtered)

    categories = {str(item.get("category") or "") for item in filtered if item.get("category")}
    levels = {str(item.get("level") or "") for item in filtered if item.get("level")}
    if not levels:
        levels = {str(item.get("topikLevel") or "") for item in filtered if item.get("topikLevel")}

    sliced = filtered[skip : skip + limit]
    words = []
    for item in sliced:
        words.append(
            {
                "id": item.get("id") or "",
                "word": item.get("word") or "",
                "meaning": item.get("meaningKo")
                or item.get("meaning")
                or item.get("meaningEn")
                or "",
                "category": item.get("category") or item.get("topic") or "",
                "level": item.get("level") or item.get("topikLevel") or "",
            }
        )

    return {
        "success": True,
        "stats": {
            "total": total,
            "categories": len([c for c in categories if c]),
            "levels": len([l for l in levels if l]),
        },
        "words": words,
        "skip": skip,
        "limit": limit,
    }


@app.get("/api/admin/recordings")
async def admin_recordings_list(request: Request, limit: int = 50):
    """관리자용 최근 녹음 목록 조회."""
    _require_role(request, {ROLE_INSTRUCTOR, ROLE_SYSTEM_ADMIN})
    
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Stats
        cursor.execute("SELECT COUNT(*) FROM sentence_score_history")
        total_recordings = cursor.fetchone()[0]
        
        today = datetime.now().date().isoformat()
        cursor.execute(
            "SELECT COUNT(*) FROM sentence_score_history WHERE date(created_at) = ?",
            (today,)
        )
        today_recordings = cursor.fetchone()[0]
        
        # Recent recordings
        cursor.execute(
            """
            SELECT s.id, u.name, u.email, s.score, s.created_at, s.sentence_id
            FROM sentence_score_history s
            JOIN users u ON s.user_id = u.id
            ORDER BY s.created_at DESC
            LIMIT ?
            """,
            (limit,)
        )
        rows = cursor.fetchall()
        
        # Load sentences for context
        sentences_data = load_json_data("sentences.json") or []
        sentence_map = {str(s.get("id")): s.get("text") for s in sentences_data if s.get("id")}
        
        recordings = []
        for r in rows:
            recordings.append({
                "id": r["id"],
                "user": f"{r['name'] or 'Unknown'} ({r['email']})",
                "sentence": sentence_map.get(str(r["sentence_id"]), f"Sentence #{r['sentence_id']}"),
                "score": r["score"],
                "created_at": r["created_at"]
            })
            
        return {
            "success": True,
            "stats": {
                "total": total_recordings,
                "today": today_recordings,
                "avg_length": "2.4", # Mocked for now
                "total_size": "124" # Mocked for now
            },
            "recordings": recordings
        }
    finally:
        conn.close()


@app.get("/api/admin/content")
async def admin_content_list(request: Request, limit: int = 50):
    """관리자용 AI 콘텐츠 생성 내역 조회."""
    _require_role(request, {ROLE_INSTRUCTOR, ROLE_SYSTEM_ADMIN})
    
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Total
        cursor.execute("SELECT COUNT(*) FROM ai_content_history")
        total_content = cursor.fetchone()[0]
        
        # By type
        cursor.execute("SELECT content_type, COUNT(*) as count FROM ai_content_history GROUP BY content_type")
        type_counts = {row["content_type"]: row["count"] for row in cursor.fetchall()}
        
        # Recent
        cursor.execute(
            """
            SELECT a.id, u.name, u.email, a.content_type, a.model, a.created_at
            FROM ai_content_history a
            JOIN users u ON a.user_id = u.id
            ORDER BY a.created_at DESC
            LIMIT ?
            """,
            (limit,)
        )
        rows = cursor.fetchall()
        
        content_list = []
        for r in rows:
            content_list.append({
                "id": r["id"],
                "type": r["content_type"],
                "model": r["model"],
                "user": f"{r['name'] or 'Unknown'} ({r['email']})",
                "created_at": r["created_at"]
            })
            
        return {
            "success": True,
            "stats": {
                "total": total_content,
                "feedback": type_counts.get("feedback", 0),
                "sentence": type_counts.get("sentence", 0),
                "image": type_counts.get("image", 0),
                "chatbot": type_counts.get("chatbot", 0),
            },
            "content": content_list
        }
    finally:
        conn.close()


@app.post("/api/admin/users/{user_id}/toggle-admin")
async def admin_toggle_user_admin(request: Request, user_id: int):
    """사용자 관리자 권한 토글."""
    admin = _require_role(request, {ROLE_SYSTEM_ADMIN})
    payload = await request.json()
    
    if admin["id"] == user_id:
        raise HTTPException(status_code=400, detail="자신의 관리자 권한은 수정할 수 없습니다.")
    
    is_admin = payload.get("is_admin", False)
    new_role = ROLE_SYSTEM_ADMIN if is_admin else ROLE_LEARNER
    
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET is_admin = ?, role = ? WHERE id = ?",
            (int(bool(is_admin)), new_role, user_id)
        )
        conn.commit()
        
        user = _get_user_by_id(user_id)
        logger.info(f"[ADMIN_TOGGLE] {admin['email']} set is_admin={is_admin} for user {user['email']}")
        
        return {
            "success": True,
            "user": {"id": user_id, "is_admin": bool(is_admin), "role": new_role},
        }
    finally:
        conn.close()


@app.post("/api/admin/users/{user_id}/role")
async def admin_update_user_role(request: Request, user_id: int):
    """사용자 역할 변경."""
    admin = _require_role(request, {ROLE_INSTRUCTOR, ROLE_SYSTEM_ADMIN})
    payload = await request.json()

    if admin["id"] == user_id:
        raise HTTPException(status_code=400, detail="자신의 역할은 변경할 수 없습니다.")

    role = (payload.get("role") or "").strip().lower()
    if role not in ROLE_CHOICES:
        raise HTTPException(status_code=400, detail="유효하지 않은 역할입니다.")

    is_admin = role == ROLE_SYSTEM_ADMIN

    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET role = ?, is_admin = ? WHERE id = ?",
            (role, int(is_admin), user_id),
        )
        conn.commit()

        user = _get_user_by_id(user_id)
        logger.info(
            f"[ADMIN_ROLE] {admin['email']} set role={role} for user {user['email']}"
        )

        return {
            "success": True,
            "user": {
                "id": user_id,
                "role": role,
                "is_admin": bool(is_admin),
            },
        }
    finally:
        conn.close()


@app.post("/api/admin/users/{user_id}/reset-password")
async def admin_reset_user_password(request: Request, user_id: int):
    """사용자 비밀번호 초기화."""
    admin = _require_role(request, {ROLE_INSTRUCTOR, ROLE_SYSTEM_ADMIN})
    payload = await request.json()
    
    if admin["id"] == user_id:
        raise HTTPException(status_code=400, detail="자신의 비밀번호는 이 방법으로 초기화할 수 없습니다.")
    
    new_password = payload.get("new_password", "")
    if not new_password or len(new_password) < 8:
        raise HTTPException(status_code=400, detail="새 비밀번호는 8자 이상이어야 합니다.")
    
    new_hash = _hash_password(new_password)
    
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_hash, user_id)
        )
        conn.commit()
        
        user = _get_user_by_id(user_id)
        logger.info(f"[ADMIN_RESET_PWD] {admin['email']} reset password for user {user['email']}")
        
        return {"success": True, "message": f"{user['email']}의 비밀번호가 초기화되었습니다."}
    finally:
        conn.close()


@app.post("/api/admin/users")
async def admin_create_user(request: Request):
    """관리자용 새 사용자 계정 생성."""
    _require_role(request, {ROLE_INSTRUCTOR, ROLE_SYSTEM_ADMIN})
    payload = await request.json()
    
    email = (payload.get("email") or "").strip().lower()
    name = (payload.get("name") or "").strip()
    password = payload.get("password") or "mz1234!@" # 기본 비밀번호
    role = (payload.get("role") or ROLE_LEARNER).strip().lower()
    
    if not email or not EMAIL_REGEX.match(email):
        raise HTTPException(status_code=400, detail="유효한 이메일을 입력하세요.")
    if not name:
        raise HTTPException(status_code=400, detail="이름을 입력하세요.")
    if role not in ROLE_CHOICES:
        raise HTTPException(status_code=400, detail="유효하지 않은 역할입니다.")

    password_hash = _hash_password(password)
    created_at = datetime.utcnow().isoformat()
    is_admin = 1 if role == ROLE_SYSTEM_ADMIN else 0
    nickname = name

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            INSERT INTO users (email, name, nickname, password_hash, created_at, is_admin, role)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (email, name, nickname, password_hash, created_at, is_admin, role),
        )
        conn.commit()
        return {"success": True, "message": "사용자 계정이 생성되었습니다."}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="이미 존재하는 이메일입니다.")
    finally:
        conn.close()


@app.patch("/api/admin/users/{user_id}")
async def admin_update_user(request: Request, user_id: int):
    """관리자용 사용자 정보 수정 (이름, 이메일)."""
    _require_role(request, {ROLE_INSTRUCTOR, ROLE_SYSTEM_ADMIN})
    payload = await request.json()
    
    name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    
    if not name and not email:
        raise HTTPException(status_code=400, detail="수정할 정보를 입력하세요.")

    updates = []
    values = []
    if name:
        updates.append("name = ?")
        updates.append("nickname = ?")
        values.extend([name, name])
    if email:
        if not EMAIL_REGEX.match(email):
            raise HTTPException(status_code=400, detail="유효한 이메일을 입력하세요.")
        updates.append("email = ?")
        values.append(email)
    
    values.append(user_id)
    
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
            tuple(values)
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
        return {"success": True, "message": "사용자 정보가 수정되었습니다."}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="이미 존재하는 이메일입니다.")
    finally:
        conn.close()


@app.delete("/api/admin/users/{user_id}")
async def admin_delete_user(request: Request, user_id: int):
    """관리자용 사용자 계정 삭제."""
    admin = _require_role(request, {ROLE_INSTRUCTOR, ROLE_SYSTEM_ADMIN})
    
    if admin["id"] == user_id:
        raise HTTPException(status_code=400, detail="자신의 계정은 삭제할 수 없습니다.")
        
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
        return {"success": True, "message": "사용자 계정이 삭제되었습니다."}
    finally:
        conn.close()


@app.get("/api/admin/users/{user_id}")
async def admin_get_user_detail(request: Request, user_id: int):
    """사용자 상세 조회."""
    admin = _require_role(request, {ROLE_INSTRUCTOR, ROLE_SYSTEM_ADMIN})
    
    user = _get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    
    user.pop("password_hash", None)
    logger.info(f"[ADMIN_VIEW_USER] {admin['email']} viewed user {user['email']}")
    
    return {"success": True, "user": user}


@app.get("/api/admin/settings")
async def admin_get_settings(request: Request):
    """관리자 설정 조회."""
    admin = _require_role(request, {ROLE_SYSTEM_ADMIN})
    
    settings = {
        "model_backend": MODEL_BACKEND,
        "ollama_url": OLLAMA_URL,
        "ollama_model": OLLAMA_MODEL,
        "mztts_url": MZTTS_API_URL,
        "romanize_mode": ROMANIZE_MODE,
        "romanizer_available": ROMANIZER_AVAILABLE,
    }
    
    logger.info(f"[ADMIN_SETTINGS] {admin['email']} retrieved settings")
    return {"success": True, "settings": settings}


@app.get("/api/admin/rag/settings")
async def admin_rag_get_settings(request: Request):
    admin = _require_role(request, {ROLE_SYSTEM_ADMIN})
    conn = sqlite3.connect(DB_PATH)
    try:
        _ensure_rag_tables(conn)
        settings = _rag_get_settings(conn)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS n FROM rag_documents")
        docs = int(cursor.fetchone()["n"])
        cursor.execute("SELECT COUNT(*) AS n FROM rag_chunks")
        chunks = int(cursor.fetchone()["n"])
        logger.info("[ADMIN_RAG] %s viewed settings", admin.get("email"))
        return {"success": True, "settings": settings, "stats": {"documents": docs, "chunks": chunks}}
    finally:
        conn.close()


@app.post("/api/admin/rag/settings")
async def admin_rag_update_settings(request: Request):
    admin = _require_role(request, {ROLE_SYSTEM_ADMIN})
    payload = await request.json()
    enabled = 1 if bool(payload.get("enabled")) else 0
    top_k = int(payload.get("top_k") or 5)
    top_k = max(1, min(top_k, 10))
    conn = sqlite3.connect(DB_PATH)
    try:
        _ensure_rag_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE rag_settings SET enabled = ?, top_k = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
            (enabled, top_k),
        )
        conn.commit()
        logger.info("[ADMIN_RAG] %s updated settings enabled=%s top_k=%s", admin.get("email"), enabled, top_k)
        return {"success": True}
    finally:
        conn.close()


@app.get("/api/admin/rag/documents")
async def admin_rag_list_documents(request: Request):
    _require_role(request, {ROLE_SYSTEM_ADMIN})
    conn = sqlite3.connect(DB_PATH)
    try:
        _ensure_rag_tables(conn)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, title, source, mime_type, created_at
            FROM rag_documents
            ORDER BY created_at DESC
            LIMIT 200
            """
        )
        docs = [dict(r) for r in cursor.fetchall()]
        return {"success": True, "documents": docs}
    finally:
        conn.close()


@app.delete("/api/admin/rag/documents/{doc_id}")
async def admin_rag_delete_document(request: Request, doc_id: int):
    admin = _require_role(request, {ROLE_SYSTEM_ADMIN})
    conn = sqlite3.connect(DB_PATH)
    try:
        _ensure_rag_tables(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM rag_documents WHERE id = ?", (doc_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
        cursor.execute("SELECT id FROM rag_chunks WHERE document_id = ?", (doc_id,))
        chunk_ids = [row[0] for row in cursor.fetchall()]
        if chunk_ids:
            placeholders = ",".join(["?"] * len(chunk_ids))
            cursor.execute(
                f"DELETE FROM rag_chunks_fts WHERE chunk_id IN ({placeholders})", chunk_ids
            )
        cursor.execute("DELETE FROM rag_chunks WHERE document_id = ?", (doc_id,))
        cursor.execute("DELETE FROM rag_documents WHERE id = ?", (doc_id,))
        conn.commit()
        logger.info("[ADMIN_RAG] %s deleted document id=%s", admin.get("email"), doc_id)
        return {"success": True}
    finally:
        conn.close()


@app.post("/api/admin/rag/documents")
async def admin_rag_upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(""),
    source: str = Form(""),
):
    admin = _require_role(request, {ROLE_SYSTEM_ADMIN})
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    mime_type = file.content_type or "text/plain"
    try:
        text = raw.decode("utf-8", errors="ignore")
    except Exception:
        text = str(raw)

    title = (title or "").strip() or (file.filename or "문서")
    source = (source or "").strip() or (file.filename or "upload")
    chunks = _rag_chunk_text(text, max_chars=700)
    if not chunks:
        raise HTTPException(status_code=400, detail="텍스트를 추출할 수 없습니다.")

    conn = sqlite3.connect(DB_PATH)
    try:
        _ensure_rag_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO rag_documents (title, source, mime_type) VALUES (?, ?, ?)",
            (title, source, mime_type),
        )
        doc_id = cursor.lastrowid
        for idx, chunk in enumerate(chunks):
            cursor.execute(
                "INSERT INTO rag_chunks (document_id, chunk_index, content) VALUES (?, ?, ?)",
                (doc_id, idx, chunk),
            )
            chunk_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO rag_chunks_fts (content, chunk_id) VALUES (?, ?)",
                (chunk, chunk_id),
            )
        conn.commit()
        logger.info(
            "[ADMIN_RAG] %s uploaded document id=%s chunks=%s",
            admin.get("email"),
            doc_id,
            len(chunks),
        )
        return {"success": True, "document_id": doc_id, "chunks": len(chunks)}
    finally:
        conn.close()


@app.post("/api/user/password/change")
async def change_password(request: Request):
    """사용자 비밀번호 변경."""
    payload = await request.json()
    # Get token
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(status_code=401, detail="토큰이 없습니다.")
    
    parsed = _parse_session_token(token)
    if not parsed:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    
    user_id = parsed["user_id"]
    user = _get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    
    # Validate inputs
    current_password = payload.get("current_password") or ""
    new_password = payload.get("new_password") or ""
    confirm_password = payload.get("confirm_password") or ""
    
    if not current_password:
        raise HTTPException(status_code=400, detail="현재 비밀번호를 입력하세요.")
    if not new_password:
        raise HTTPException(status_code=400, detail="새 비밀번호를 입력하세요.")
    if new_password != confirm_password:
        raise HTTPException(status_code=400, detail="새 비밀번호가 일치하지 않습니다.")
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="새 비밀번호는 8자 이상이어야 합니다.")
    
    # Verify current password
    user_with_hash = _get_user_by_email(user["email"])
    if not user_with_hash or not _verify_password(user_with_hash["password_hash"], current_password):
        raise HTTPException(status_code=401, detail="현재 비밀번호가 올바르지 않습니다.")
    
    # Update password
    new_hash = _hash_password(new_password)
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_hash, user_id)
        )
        conn.commit()
    finally:
        conn.close()
    
    return {"success": True, "message": "비밀번호가 변경되었습니다."}

@app.post("/api/generate-content")
async def generate_content(
    topic: str = Form(...), 
    level: str = Form(...), 
    model: str = Form(None),
    backend: str = Form(None)
):
    # Add level-specific guidance to the prompt so the model tailors output
    lvl = (level or "").strip()
    if lvl == "초급":
        level_guidance = (
            "초급 학습자용으로 답변해주세요. "
            "문장은 짧고 간단하게(주로 기본 표현), 쉬운 어휘를 사용하고, 각 문장에 대한 짧은 설명은 생략하세요. "
            "한글을 처음 배우는 학습자도 이해하기 쉬운 수준으로 구성해 주세요."
        )
    elif lvl == "중급":
        level_guidance = (
            "중급 학습자용으로 답변해주세요. "
            "문장은 자연스럽고 약간 복잡한 문장 구조를 포함할 수 있으며, 한두 개의 문법 포인트나 표현 설명(짧게)을 포함하세요. "
            "어휘는 적당히 도전적인 단어를 사용해 주세요."
        )
    elif lvl == "고급":
        level_guidance = (
            "고급 학습자용으로 답변해주세요. "
            "보다 풍부한 표현, 관용구, 뉘앙스 설명과 문화적 메모를 포함해 주세요. "
            "문장은 자연스럽고 복잡할 수 있으며 학습자가 심화 학습할 수 있도록 예시와 설명을 추가하세요."
        )
    else:
        level_guidance = "요구된 레벨에 맞게 적절한 난이도로 작성해 주세요."

    prompt = f"""
    한국어 선생님입니다.
    주제: '{topic}'
    레벨: '{level}'

    {level_guidance}

    위 조건에 맞는 짧은 한국어 대화문(3~4마디)과 주요 단어 3개를 JSON 형식으로 만들어주세요.
    각 대사 항목에는 한국어 원문(text)과, 발음 표기를 반드시 포함해 주세요.
    발음 표기는 한국어 발음을 이해하기 쉬운 영문 로마자(라틴 알파벳)로 표기해 주세요. 예: "안녕" -> "annyeong".
    (참고: IPA 대신 보편적으로 이해하기 쉬운 로마자 표기를 사용하십시오.)
    형식 예시:
    {{
        "dialogue": [
            {{"speaker": "A", "text": "한국어 문장", "pronunciation": "romanized pronunciation"}},
            {{"speaker": "B", "text": "한국어 문장", "pronunciation": "romanized pronunciation"}}
        ],
        "vocabulary": ["단어1", "단어2", "단어3"]
    }}
    
    중요: 응답은 반드시 마지막에 하나의 JSON 객체만 포함된 코드 블럭(```json ... ``` )으로 정확하게 반환하세요. 추가 설명이나 여분의 텍스트는 포함하지 마시고, 코드 블럭 외의 다른 출력은 하지 마세요.
    """
    
    # Determine which backend to use
    selected_backend = backend or MODEL_BACKEND
    
    # Use Gemini backend if configured
    if selected_backend == "gemini":
        try:
            if not GEMINI_API_KEY:
                return JSONResponse(status_code=400, content={"error": "GEMINI_API_KEY not configured"})
            
            # Use REST API for Python 3.8 compatibility
            gemini_model = model or GEMINI_MODEL
            url = f"https://generativelanguage.googleapis.com/v1/models/{gemini_model}:generateContent?key={GEMINI_API_KEY}"
            payload = {
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }]
            }
            
            resp = requests.post(url, json=payload, timeout=60)
            resp.raise_for_status()
            result = resp.json()
            
            if "candidates" in result and len(result["candidates"]) > 0:
                out = result["candidates"][0]["content"]["parts"][0]["text"]
            else:
                return JSONResponse(status_code=500, content={"error": "No response from Gemini", "details": result})
            
            parsed = _parse_model_output(out)
            if parsed is None:
                try:
                    m = re.search(r"(\{[\s\S]*\"dialogue\"[\s\S]*\})", out)
                    if m:
                        parsed = json.loads(m.group(1))
                except Exception:
                    parsed = None
            
            if parsed is not None:
                # Post-process pronunciation
                try:
                    dlg = parsed.get("dialogue")
                    if isinstance(dlg, list):
                        for item in dlg:
                            if not isinstance(item, dict):
                                continue
                            item_text = item.get("text", "") or ""
                            pron = item.get("pronunciation")
                            try:
                                mode = ROMANIZE_MODE
                                if mode == "force":
                                    pron = romanize_korean(item_text)
                                else:
                                    if pron and isinstance(pron, str):
                                        if re.search(r"[\uac00-\ud7a3]", pron) or not re.search(r"[A-Za-z]", pron):
                                            pron = romanize_korean(item_text)
                                    else:
                                        pron = romanize_korean(item_text)
                            except Exception:
                                pron = pron or romanize_korean(item_text)

                            try:
                                if isinstance(pron, str):
                                    pron = re.sub(r"\s+", " ", pron.replace("\n", " ").replace("\t", " ")).strip()
                                else:
                                    pron = str(pron)
                            except Exception:
                                pron = pron if pron is not None else ""

                            item["pronunciation"] = pron
                except Exception:
                    pass
                return JSONResponse(content=parsed)
            return JSONResponse(content={"text": out})
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": "generate-content (gemini) failed", "details": str(e)})
    
    # Use Ollama local backend if configured
    elif selected_backend == "ollama":
        try:
            use_model = model or OLLAMA_MODEL
            payload = {"model": use_model, "prompt": prompt}
            resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, stream=True, timeout=30)
            if resp.status_code != 200:
                return JSONResponse(status_code=500, content={"error": "ollama generate failed", "status": resp.status_code, "body": resp.text})

            out = ""
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        out += obj.get("response", "") or obj.get("text", "")
                    else:
                        out += str(obj)
                except Exception:
                    out += line

            parsed = _parse_model_output(out)
            # If parser failed to extract JSON, try a fallback extraction of a
            # JSON substring containing a "dialogue" key. If that still fails,
            # re-prompt the model once with a very strict instruction asking for
            # exactly one JSON code block only. This helps when the model
            # prepends commentary or streams non-JSON content before the JSON.
            if parsed is None:
                try:
                    m = re.search(r"(\{[\s\S]*\"dialogue\"[\s\S]*\})", out)
                    if m:
                        candidate = m.group(1)
                        parsed = json.loads(candidate)
                except Exception:
                    parsed = None

            # If still not parsed, perform one retry with a short, strict
            # re-instruction to the model to only return the single JSON
            # object in a code block. Avoid infinite retries.
            if parsed is None:
                try:
                    retry_prompt = (
                        prompt
                        + "\n\nSECOND REQUEST (STRICT): RETURN ONLY ONE JSON OBJECT INSIDE A SINGLE ```json CODE BLOCK. DO NOT ADD ANY TEXT OUTSIDE THE CODE BLOCK."
                    )
                    payload2 = {"model": use_model, "prompt": retry_prompt}
                    resp2 = requests.post(f"{OLLAMA_URL}/api/generate", json=payload2, stream=True, timeout=30)
                    if resp2.status_code == 200:
                        out2 = ""
                        for line in resp2.iter_lines(decode_unicode=True):
                            if not line:
                                continue
                            try:
                                obj = json.loads(line)
                                if isinstance(obj, dict):
                                    out2 += obj.get("response", "") or obj.get("text", "")
                                else:
                                    out2 += str(obj)
                            except Exception:
                                out2 += line

                        parsed = _parse_model_output(out2)
                        if parsed is None:
                            try:
                                m2 = re.search(r"(\{[\s\S]*\"dialogue\"[\s\S]*\})", out2)
                                if m2:
                                    parsed = json.loads(m2.group(1))
                            except Exception:
                                parsed = None
                except Exception:
                    # swallow retry errors and continue; we'll return raw text if
                    # parsing still fails.
                    parsed = None

            if parsed is not None:
                # Post-process: ensure each dialogue entry has an English
                # (romanized) pronunciation and normalize whitespace.
                # If the model returned Hangul or omitted pronunciation,
                # produce a romanized fallback from the `text` field.
                try:
                    dlg = parsed.get("dialogue")
                    if isinstance(dlg, list):
                        for item in dlg:
                            if not isinstance(item, dict):
                                continue
                            item_text = item.get("text", "") or ""
                            # Prefer the model-provided pronunciation if it
                            # appears to be Latin. If it's missing or contains
                            # Hangul, derive from `text`.
                            pron = item.get("pronunciation")
                            try:
                                # ROMANIZE_MODE controls behavior:
                                # - 'force': always overwrite with the romanizer output
                                # - 'prefer': keep model-provided Latin pronunciation when valid
                                mode = ROMANIZE_MODE
                                if mode == "force":
                                    pron = romanize_korean(item_text)
                                else:
                                    # prefer mode: keep model-provided pronunciation
                                    # if it looks like Latin (has ASCII letters and
                                    # does not include Hangul), otherwise romanize.
                                    if pron and isinstance(pron, str):
                                        if re.search(r"[\uac00-\ud7a3]", pron) or not re.search(r"[A-Za-z]", pron):
                                            pron = romanize_korean(item_text)
                                        # else: keep model-provided Latin pronunciation
                                    else:
                                        pron = romanize_korean(item_text)
                            except Exception:
                                pron = pron or romanize_korean(item_text)

                            # Normalize whitespace & newlines: collapse runs
                            # of whitespace into a single space and trim.
                            try:
                                if isinstance(pron, str):
                                    # replace newlines/tabs with spaces then collapse
                                    pron = re.sub(r"\s+", " ", pron.replace("\n", " ").replace("\t", " ")).strip()
                                else:
                                    pron = str(pron)
                            except Exception:
                                pron = pron if pron is not None else ""

                            item["pronunciation"] = pron
                except Exception:
                    # keep parsed as-is on any failure
                    pass
                return JSONResponse(content=parsed)
            return JSONResponse(content={"text": out})
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": "generate-content (ollama) failed", "details": str(e)})

    # Use OpenAI backend if configured
    elif selected_backend == "openai":
        if not OPENAI_API_KEY or not client:
            return JSONResponse(status_code=500, content={"error": "OpenAI API key not configured"})
        
        try:
            use_model = model or OPENAI_MODEL
            response = client.chat.completions.create(
                model=use_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=2000
            )
            
            out = response.choices[0].message.content.strip()
            parsed = _parse_model_output(out)
            
            if parsed is None:
                try:
                    m = re.search(r"(\{[\s\S]*\"dialogue\"[\s\S]*\})", out)
                    if m:
                        candidate = m.group(1)
                        parsed = json.loads(candidate)
                except Exception:
                    parsed = None
            
            if parsed is not None:
                try:
                    dlg = parsed.get("dialogue")
                    if isinstance(dlg, list):
                        for item in dlg:
                            if not isinstance(item, dict):
                                continue
                            item_text = item.get("text", "") or ""
                            pron = item.get("pronunciation")
                            try:
                                mode = ROMANIZE_MODE
                                if mode == "force":
                                    pron = romanize_korean(item_text)
                                else:
                                    if pron and isinstance(pron, str):
                                        if re.search(r"[\uac00-\ud7a3]", pron) or not re.search(r"[A-Za-z]", pron):
                                            pron = romanize_korean(item_text)
                                    else:
                                        pron = romanize_korean(item_text)
                            except Exception:
                                pron = pron or romanize_korean(item_text)
                            
                            try:
                                if isinstance(pron, str):
                                    pron = re.sub(r"\s+", " ", pron.replace("\n", " ").replace("\t", " ")).strip()
                                else:
                                    pron = str(pron)
                            except Exception:
                                pron = pron if pron is not None else ""
                            
                            item["pronunciation"] = pron
                except Exception:
                    pass
                return JSONResponse(content=parsed)
            return JSONResponse(content={"text": out})
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": "generate-content (openai) failed", "details": str(e)})
    
    # Fallback / default
    return JSONResponse(status_code=501, content={"error": "Unknown backend selected"})


# ==========================================
# 이미지 생성 (Gemini 시범용) API
# ==========================================
@app.post("/api/gemini/image")
async def gemini_image(prompt: str = Form(...), save_locally: bool = Form(True)):
    if MODEL_BACKEND not in ("gemini", "openai", "ollama", "gemini-image", "mixed"):
        # 여유 있게 허용 (프롬프트가 올 때 백엔드 무관하게 시도)
        pass

    result = await generate_image_gemini(prompt, save_locally=save_locally)
    if not result.get("success"):
        fallback = await generate_image_dall_e(
            prompt=enhance_prompt_for_korean_learning(prompt, "illustration"),
            size=os.getenv("DALLE_IMAGE_SIZE", "1024x1024"),
            quality=os.getenv("DALLE_QUALITY", "standard"),
            style=os.getenv("DALLE_STYLE", "vivid"),
            save_locally=save_locally,
        )
        if fallback.get("success"):
            fallback["fallback_from"] = "gemini"
            return JSONResponse(content=fallback)
        return JSONResponse(status_code=500, content=result)
    return JSONResponse(content=result)


@app.get("/api/word-images/cache")
async def get_word_image_cache(key: str = None):
    if not key:
        return JSONResponse(status_code=400, content={"error": "key is required"})
    cached = _get_cached_word_image(key)
    return JSONResponse(content={"cached": bool(cached), "entry": cached or {}})


@app.post("/api/word-images/cache")
async def set_word_image_cache(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid json"})
    key = (data.get("key") or "").strip()
    url = (data.get("url") or "").strip()
    if not key or not url:
        return JSONResponse(status_code=400, content={"error": "key and url are required"})
    _set_cached_word_image(key, url)
    return JSONResponse(content={"success": True})


@app.get("/api/ollama/models")
def get_ollama_models():
    """Proxy endpoint to list Ollama models available on the local server."""
    try:
        models = _list_ollama_models()
        return JSONResponse(content={"models": models})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "failed to list ollama models", "details": str(e)})


@app.post("/api/ollama/test")
async def ollama_test(prompt: str = Form(...), model: str = Form(None)):
    """Send a quick test prompt to the selected Ollama model and return the raw text."""
    if MODEL_BACKEND != "ollama":
        return JSONResponse(status_code=400, content={"error": "MODEL_BACKEND is not set to 'ollama'"})

    use_model = model or OLLAMA_MODEL
    try:
        payload = {"model": use_model, "prompt": prompt}
        resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, stream=True, timeout=30)
        if resp.status_code != 200:
            return JSONResponse(status_code=500, content={"error": "ollama generate failed", "status": resp.status_code, "body": resp.text})

        out = ""
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    out += obj.get("response", "") or obj.get("text", "")
                else:
                    out += str(obj)
            except Exception:
                out += line

        parsed = _parse_model_output(out)
        if parsed is None:
            try:
                m = re.search(r"(\{[\s\S]*\"dialogue\"[\s\S]*\})", out)
                if m:
                    parsed = json.loads(m.group(1))
            except Exception:
                parsed = None

        if parsed is not None:
            return JSONResponse(content={"model": use_model, "parsed": parsed})
        return JSONResponse(content={"model": use_model, "text": out})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "ollama test failed", "details": str(e)})

@app.post("/api/chat/test")
async def chat_test(prompt: str = Form(...), model: str = Form(None), backend: str = Form(None)):
    """Send a quick test prompt to the selected model (Gemini or Ollama) and return the raw text."""
    selected_backend = backend or MODEL_BACKEND
    
    # Use Gemini backend
    if selected_backend == "gemini":
        try:
            if not GEMINI_API_KEY:
                return JSONResponse(status_code=400, content={"error": "GEMINI_API_KEY not configured"})
            
            gemini_model = model or GEMINI_MODEL
            url = f"https://generativelanguage.googleapis.com/v1/models/{gemini_model}:generateContent?key={GEMINI_API_KEY}"
            payload = {
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }]
            }
            
            resp = requests.post(url, json=payload, timeout=60)
            resp.raise_for_status()
            result = resp.json()
            
            if "candidates" in result and len(result["candidates"]) > 0:
                out = result["candidates"][0]["content"]["parts"][0]["text"]
                return JSONResponse(content={"model": gemini_model, "text": out})
            else:
                return JSONResponse(status_code=500, content={"error": "No response from Gemini", "details": result})
                
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": "gemini test failed", "details": str(e)})
    
    # Use OpenAI backend
    elif selected_backend == "openai":
        try:
            if not OPENAI_API_KEY:
                return JSONResponse(status_code=400, content={"error": "OPENAI_API_KEY not configured"})
            if not client:
                return JSONResponse(status_code=500, content={"error": "OpenAI client not initialized"})

            use_model = model or OPENAI_MODEL
            completion = client.chat.completions.create(
                model=use_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )

            out = completion.choices[0].message.content if completion and completion.choices else ""
            return JSONResponse(content={"model": use_model, "text": out})
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": "openai test failed", "details": str(e)})

    # Use Ollama backend
    elif selected_backend == "ollama":
        use_model = model or OLLAMA_MODEL
        try:
            payload = {"model": use_model, "prompt": prompt}
            resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, stream=True, timeout=30)
            if resp.status_code != 200:
                return JSONResponse(status_code=500, content={"error": "ollama generate failed", "status": resp.status_code, "body": resp.text})

            out = ""
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        out += obj.get("response", "") or obj.get("text", "")
                    else:
                        out += str(obj)
                except Exception:
                    out += line

            return JSONResponse(content={"model": use_model, "text": out})
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": "ollama test failed", "details": str(e)})
    
    else:
        return JSONResponse(status_code=400, content={"error": f"Unknown backend: {selected_backend}"})

# ==========================================
# 3. 유창성 테스트 (작문 교정) API
# ==========================================
@app.post("/api/fluency-check")
async def fluency_check(user_text: str = Form(...)):
    prompt = f"""
    사용자가 쓴 한국어 문장입니다: "{user_text}"
    
    이 문장의 자연스러움을 100점 만점으로 평가하고, 
    교정된 문장과 피드백을 한국어로 짧게 주세요.
    JSON 형식: {{"score": 85, "corrected": "...", "feedback": "..."}}
    """
    
    # Use Ollama backend if configured
    if MODEL_BACKEND == "ollama":
        try:
            payload = {"model": OLLAMA_MODEL, "prompt": prompt}
            resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, stream=True, timeout=30)
            if resp.status_code != 200:
                return JSONResponse(status_code=500, content={"error": "ollama generate failed", "status": resp.status_code, "body": resp.text})

            out = ""
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        out += obj.get("response", "") or obj.get("text", "")
                    else:
                        out += str(obj)
                except Exception:
                    out += line

            parsed = _parse_model_output(out)
            if parsed is not None:
                return JSONResponse(content=parsed)
            return JSONResponse(content={"text": out})
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": "fluency-check (ollama) failed", "details": str(e)})
    
    # Use Gemini backend if configured
    elif MODEL_BACKEND == "gemini":
        try:
            if not GEMINI_API_KEY:
                return JSONResponse(status_code=400, content={"error": "GEMINI_API_KEY not configured"})
            
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel(GEMINI_MODEL)
            
            response = model.generate_content(prompt)
            out = response.text
            
            parsed = _parse_model_output(out)
            if parsed is not None:
                return JSONResponse(content=parsed)
            return JSONResponse(content={"text": out})
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": "fluency-check (gemini) failed", "details": str(e)})
    
    # Use OpenAI backend if configured
    elif MODEL_BACKEND == "openai":
        try:
            if not OPENAI_API_KEY or not client:
                return JSONResponse(status_code=500, content={"error": "OpenAI API key not configured"})
            
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500
            )
            
            out = response.choices[0].message.content.strip()
            parsed = _parse_model_output(out)
            if parsed is not None:
                return JSONResponse(content=parsed)
            return JSONResponse(content={"text": out})
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": "fluency-check (openai) failed", "details": str(e)})

    # Fallback / default
    return JSONResponse(status_code=501, content={"error": "Unknown backend selected"})

# ==========================================
# 3-2. 상황별 컨텐츠 생성 API
# ==========================================
@app.post("/api/situational-content")
async def situational_content(situation: str = Form(...), level: str = Form(...), model: str = Form(None), backend: str = Form(None)):
    """
    상황(예: 카페, 식당, 병원)과 난이도를 입력받아 
    상황에 맞는 표현, 대화, 어휘를 생성합니다.
    """
    situation_prompts = {
        "카페": "카페에서 커피를 주문하는 상황",
        "식당": "식당에서 음식을 예약하고 주문하는 상황",
        "병원": "병원 진료를 받는 상황",
        "은행": "은행에서 업무를 보는 상황",
        "여행": "여행을 계획하고 호텔을 예약하는 상황",
        "면접": "면접을 보는 상황",
    }
    
    situation_desc = situation_prompts.get(situation, situation)
    
    prompt = f"""한국어 학습자를 위한 상황별 학습 컨텐츠를 생성해주세요.

상황: {situation_desc}
난이도: {level}

다음 정보를 JSON 형식으로 제공해주세요:
{{
    "situation_description": "상황에 대한 설명",
    "key_expressions": [
        {{"korean": "네, 잠깐만요.", "romanization": "Ne, jamkkanman yo.", "meaning": "Yes, wait a moment"}},
        {{"korean": "감사합니다.", "romanization": "Gamsahamnida.", "meaning": "Thank you"}}
    ],
    "example_dialogue": [
        {{"role": "A", "text": "안녕하세요! 무엇을 도와드릴까요?"}},
        {{"role": "B", "text": "아이스 아메리카노 한 잔 주세요."}}
    ],
    "vocabulary": ["단어1", "단어2", "단어3"]
}}

중요: 응답은 반드시 하나의 JSON 객체만 포함된 코드 블럭(```json ... ```)으로 정확하게 반환하세요. 추가 설명이나 여분의 텍스트는 포함하지 마세요."""
    
    # Determine which backend to use (respect frontend selection)
    selected_backend = backend or MODEL_BACKEND
    
    try:
        if selected_backend == "gemini":
            if not GEMINI_API_KEY:
                return JSONResponse(status_code=400, content={"error": "GEMINI_API_KEY not configured"})
            
            gemini_model_name = model or GEMINI_MODEL
            url = f"https://generativelanguage.googleapis.com/v1/models/{gemini_model_name}:generateContent?key={GEMINI_API_KEY}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}]
            }
            
            resp = requests.post(url, json=payload, timeout=60)
            resp.raise_for_status()
            result = resp.json()
            
            out = ""
            if "candidates" in result and len(result["candidates"]) > 0:
                parts = result["candidates"][0].get("content", {}).get("parts", [])
                for part in parts:
                    out += part.get("text", "")
            
            parsed = _parse_model_output(out)
            if parsed is not None:
                return JSONResponse(content=parsed)
            # Fallback: return raw text so frontend can display something
            return JSONResponse(content={"text": out})
        
        elif selected_backend == "ollama":
            payload = {"model": model or OLLAMA_MODEL, "prompt": prompt}
            resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, stream=True, timeout=60)
            if resp.status_code != 200:
                return JSONResponse(status_code=500, content={"error": "ollama generate failed"})
            
            out = ""
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        out += obj.get("response", "") or obj.get("text", "")
                except Exception:
                    out += line
            
            parsed = _parse_model_output(out)
            if parsed is not None:
                return JSONResponse(content=parsed)
            # Fallback: return raw text so frontend can display something
            return JSONResponse(content={"text": out})
        
        else:
            return JSONResponse(status_code=501, content={"error": f"Backend '{selected_backend}' not configured"})
    
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "situational-content failed", "details": str(e)})

# ==========================================
# 4. 발음 교정 API (음성 업로드 -> STT -> 비교)
# ==========================================
@app.post("/api/pronunciation-check")
async def pronunciation_check(target_text: str = Form(...), file: UploadFile = File(...)):
    # 파일 업로드 검증 및 저장 (MVP 수준)
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
    ALLOWED_TYPES = {
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/webm",
        "audio/ogg",
        "audio/mp4",
        "audio/x-m4a",
    }

    if file.content_type not in ALLOWED_TYPES:
        return JSONResponse(status_code=415, content={"error": "Unsupported media type"})

    file_location = f"temp_{file.filename}"

    # STT backend pre-checks
    if STT_BACKEND == "openai":
        if client is None:
            return JSONResponse(status_code=501, content={"error": "OpenAI STT is not configured"})
    elif STT_BACKEND == "google":
        # Google STT will be attempted after writing the file
        pass
    else:
        # Try local STT if configured
        local_stt = os.getenv("LOCAL_STT", "").lower()
        if local_stt == "vosk":
            vosk_model_path = os.getenv("VOSK_MODEL_PATH")
            if not vosk_model_path:
                return JSONResponse(status_code=501, content={"error": "VOSK model path not configured (VOSK_MODEL_PATH)"})

            # convert uploaded file to 16k mono wav for VOSK
            converted = file_location + ".vsk.wav"
            try:
                _ensure_wav_16k_mono(file_location, converted)
                transcript_text = _transcribe_with_vosk(converted, vosk_model_path)
                try:
                    os.remove(converted)
                except Exception:
                    pass

                user_said = transcript_text
            except Exception as e:
                try:
                    if os.path.exists(file_location):
                        os.remove(file_location)
                except Exception:
                    pass
                return JSONResponse(status_code=500, content={"error": "local STT failed", "details": str(e)})
        else:
            return JSONResponse(status_code=501, content={"error": "STT backend not configured"})
    size = 0
    try:
        # stream-write to disk with size limit
        with open(file_location, "wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    await file.close()
                    buffer.close()
                    try:
                        os.remove(file_location)
                    except Exception:
                        pass
                    return JSONResponse(status_code=413, content={"error": "File too large"})
                buffer.write(chunk)

        # 2. STT (OpenAI Whisper or Google Cloud)
        if STT_BACKEND == "openai":
            audio_file = open(file_location, "rb")
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ko"
            )
            user_said = getattr(transcript, "text", None) or transcript.get("text") if isinstance(transcript, dict) else None
            if user_said is None:
                user_said = ""
        elif STT_BACKEND == "google":
            google_client = _get_google_speech_client()
            if not GOOGLE_SPEECH_AVAILABLE or google_client is None:
                return JSONResponse(status_code=501, content={"error": "Google Cloud STT not configured or credentials missing"})
            try:
                google_tmp = file_location + ".g.wav"
                _ensure_wav_16k_mono(file_location, google_tmp)
                with open(google_tmp, "rb") as gfile:
                    g_audio = gfile.read()
                audio = speech.RecognitionAudio(content=g_audio)
                config = speech.RecognitionConfig(
                    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                    sample_rate_hertz=16000,
                    language_code="ko-KR",
                    max_alternatives=1,
                )
                response = google_client.recognize(config=config, audio=audio)
                if response.results:
                    for result in response.results:
                        if result.alternatives:
                            user_said = result.alternatives[0].transcript
                            break
                if user_said is None:
                    user_said = ""
            finally:
                try:
                    if os.path.exists(google_tmp):
                        os.remove(google_tmp)
                except Exception:
                    pass

        # 3. 유사도 검사 (간단한 MVP용 알고리즘)
        matcher = SequenceMatcher(None, target_text.replace(" ", ""), user_said.replace(" ", ""))
        similarity = matcher.ratio() * 100  # 0~100점

        return {
            "user_said": user_said,
            "target_text": target_text,
            "score": round(similarity, 1),
            "feedback": "완벽해요!" if similarity > 90 else "조금 더 또박또박 말해보세요."
        }

    except Exception as e:
        try:
            if os.path.exists(file_location):
                os.remove(file_location)
        except Exception:
            pass
        return JSONResponse(status_code=500, content={"error": "pronunciation processing failed", "details": str(e)})
    finally:
        try:
            await file.close()
        except Exception:
            pass
        try:
            audio_file.close()
        except Exception:
            pass
        try:
            if os.path.exists(file_location):
                os.remove(file_location)
        except Exception:
            pass

# ==========================================
# 학습 게임 API 엔드포인트
# ==========================================

# Word Puzzle APIs
@app.get("/api/puzzle/sentences")
async def get_puzzle_sentences(level: str = None):
    """Get word puzzle sentences, optionally filtered by CEFR level"""
    try:
        sentences = load_json_data("sentences.json")
        if level:
            sentences = [s for s in sentences if s.get("level") == level.upper()]
        return JSONResponse(content={"sentences": sentences})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to load sentences", "details": str(e)})

@app.get("/api/puzzle/sentences/{sentence_id}")
async def get_puzzle_sentence(sentence_id: int):
    """Get a specific sentence by ID"""
    try:
        sentences = load_json_data("sentences.json")
        sentence = next((s for s in sentences if s.get("id") == sentence_id), None)
        if sentence:
            return JSONResponse(content=sentence)
        return JSONResponse(status_code=404, content={"error": "Sentence not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to load sentence", "details": str(e)})

# Daily Expression APIs
@app.get("/api/expressions")
async def get_expressions(level: str = None):
    """Get all expressions, optionally filtered by CEFR level"""
    try:
        expressions = load_json_data("expressions.json")
        if level:
            expressions = [e for e in expressions if e.get("level") == level.upper()]
        return JSONResponse(content={"expressions": expressions})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to load expressions", "details": str(e)})

@app.get("/api/expressions/today")
async def get_today_expression():
    """Get today's expression (cycles through available expressions)"""
    try:
        import datetime
        expressions = load_json_data("expressions.json")
        if not expressions:
            return JSONResponse(status_code=404, content={"error": "No expressions available"})

        # Use day of year to cycle through expressions
        day_of_year = datetime.datetime.now().timetuple().tm_yday
        index = day_of_year % len(expressions)
        return JSONResponse(content=expressions[index])
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to get today's expression", "details": str(e)})

# Vocabulary Garden APIs
@app.get("/api/vocabulary")
async def get_vocabulary(level: str = None):
    """Get all vocabulary words, optionally filtered by CEFR level"""
    try:
        vocabulary = load_json_data("vocabulary.json")
        if level:
            vocabulary = [v for v in vocabulary if v.get("level") == level.upper()]
        return JSONResponse(content={"vocabulary": vocabulary})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to load vocabulary", "details": str(e)})

@app.get("/api/vocabulary/{word_id}")
async def get_vocabulary_word(word_id: str):
    """Get a specific vocabulary word by ID"""
    try:
        vocabulary = load_json_data("vocabulary.json")
        word = next((v for v in vocabulary if v.get("id") == word_id), None)
        if word:
            return JSONResponse(content=word)
        return JSONResponse(status_code=404, content={"error": "Word not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to load vocabulary word", "details": str(e)})

# KRDIC Dictionary Search API
@app.get("/api/krdict/search")
async def krdict_search(
    q: str,
    start: int = 1,
    num: int = 10,
    sort: str = None,
    part: str = None,
    translated: str = None,
    trans_lang: str = None,
    advanced: str = None,
    target: int = None,
    lang: int = None,
    method: str = None,
    type1: str = None,
    type2: str = None,
    level: str = None,
    pos: str = None,
    multimedia: str = None,
    letter_s: int = None,
    letter_e: int = None,
    sense_cat: str = None,
    subject_cat: str = None,
):
    """Search the Korean Basic Dictionary (krdict)."""
    request_params = {
        "q": q,
        "start": start,
        "num": num,
        "sort": sort,
        "part": part,
        "translated": translated,
        "trans_lang": trans_lang,
        "advanced": advanced,
        "target": target,
        "lang": lang,
        "method": method,
        "type1": type1,
        "type2": type2,
        "level": level,
        "pos": pos,
        "multimedia": multimedia,
        "letter_s": letter_s,
        "letter_e": letter_e,
        "sense_cat": sense_cat,
        "subject_cat": subject_cat,
    }
    start_time = time.monotonic()
    try:
        result = search_krdict(
            api_key=KRDICT_API_KEY,
            q=q,
            start=start,
            num=num,
            sort=sort,
            part=part,
            translated=translated,
            trans_lang=trans_lang,
            advanced=advanced,
            target=target,
            lang=lang,
            method=method,
            type1=type1,
            type2=type2,
            level=level,
            pos=pos,
            multimedia=multimedia,
            letter_s=letter_s,
            letter_e=letter_e,
            sense_cat=sense_cat,
            subject_cat=subject_cat,
        )
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        if result.get("error"):
            logger.warning(
                "[KRDICT] error=%s message=%s q=%s params=%s elapsed_ms=%s",
                result["error"].get("code"),
                result["error"].get("message"),
                q,
                {k: v for k, v in request_params.items() if v is not None and k != "q"},
                elapsed_ms,
            )
            return JSONResponse(status_code=502, content=result)
        logger.info(
            "[KRDICT] success q=%s total=%s items=%s elapsed_ms=%s params=%s",
            q,
            (result.get("channel") or {}).get("total"),
            len(result.get("items") or []),
            elapsed_ms,
            {k: v for k, v in request_params.items() if v is not None and k != "q"},
        )
        return JSONResponse(content=result)
    except ValueError as e:
        logger.warning(
            "[KRDICT] bad_request q=%s error=%s params=%s",
            q,
            str(e),
            {k: v for k, v in request_params.items() if v is not None and k != "q"},
        )
        return JSONResponse(status_code=400, content={"error": str(e)})
    except RuntimeError as e:
        logger.error(
            "[KRDICT] runtime_error q=%s error=%s params=%s",
            q,
            str(e),
            {k: v for k, v in request_params.items() if v is not None and k != "q"},
        )
        return JSONResponse(status_code=500, content={"error": str(e)})
    except requests.RequestException as e:
        logger.error(
            "[KRDICT] upstream_error q=%s error=%s params=%s",
            q,
            str(e),
            {k: v for k, v in request_params.items() if v is not None and k != "q"},
            exc_info=True,
        )
        return JSONResponse(
            status_code=502,
            content={"error": "KRDICT request failed", "details": str(e)},
        )
    except Exception as e:
        logger.error(
            "[KRDICT] unexpected_error q=%s error=%s params=%s",
            q,
            str(e),
            {k: v for k, v in request_params.items() if v is not None and k != "q"},
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"error": "KRDICT search failed", "details": str(e)},
        )

# Folktales APIs
@app.get("/api/folktales")
async def get_folktales(level: str = None):
    """Get all folktales, optionally filtered by CEFR level"""
    try:
        folktales = load_json_data("folktales.json")
        if level:
            folktales = [f for f in folktales if f.get("level") == level.upper()]
        return JSONResponse(content={"folktales": folktales})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to load folktales", "details": str(e)})

@app.get("/api/folktales/{folktale_id}")
async def get_folktale(folktale_id: int):
    """Get a specific folktale by ID"""
    try:
        folktales = load_json_data("folktales.json")
        folktale = next((f for f in folktales if f.get("id") == folktale_id), None)
        if folktale:
            return JSONResponse(content=folktale)
        return JSONResponse(status_code=404, content={"error": "Folktale not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to load folktale", "details": str(e)})

# Cultural Expressions APIs
@app.get("/api/cultural-expressions")
async def get_cultural_expressions(level: str = None, category: str = None):
    """Get cultural expressions, optionally filtered by level or category"""
    try:
        expressions = load_json_data("cultural-expressions.json")
        if level:
            expressions = [e for e in expressions if e.get("level") == level.upper()]
        if category:
            expressions = [e for e in expressions if e.get("category") == category]
        return JSONResponse(content={"expressions": expressions})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to load cultural expressions", "details": str(e)})

@app.get("/api/cultural-expressions/{expression_id}")
async def get_cultural_expression(expression_id: int):
    """Get a specific cultural expression by ID"""
    try:
        expressions = load_json_data("cultural-expressions.json")
        expression = next((e for e in expressions if e.get("id") == expression_id), None)
        if expression:
            return JSONResponse(content=expression)
        return JSONResponse(status_code=404, content={"error": "Expression not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to load cultural expression", "details": str(e)})

# Pronunciation Practice APIs
@app.get("/api/pronunciation-words")
async def get_pronunciation_words(level: str = None):
    """Get pronunciation practice words, optionally filtered by CEFR level"""
    try:
        words = load_json_data("pronunciation-words.json")
        if level:
            words = [w for w in words if w.get("level") == level.upper()]
        return JSONResponse(content={"words": words})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to load pronunciation words", "details": str(e)})

@app.get("/api/pronunciation-words/{word_id}")
async def get_pronunciation_word(word_id: str):
    """Get a specific pronunciation word by ID"""
    try:
        words = load_json_data("pronunciation-words.json")
        word = next((w for w in words if w.get("id") == word_id), None)
        if word:
            return JSONResponse(content=word)
        return JSONResponse(status_code=404, content={"error": "Word not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to load pronunciation word", "details": str(e)})


# ==========================================
# TTS API Endpoints (moved to backend/routes/tts.py)
# ==========================================

from pydantic import BaseModel


class STTProxyRequest(BaseModel):
    base_url: str
    endpoint: str
    payload: dict

# (moved) /api/speechpro/evaluate -> backend/routes/speechpro.py
async def _speechpro_evaluate_deprecated(
    text: str = Form(...),
    audio: UploadFile = File(...),
    syll_ltrs: str = Form(None),
    syll_phns: str = Form(None),
    fst: str = Form(None),
    include_ai: str = Form("true"),
):
    """
    통합 발음 평가 API
    텍스트와 음성을 전송하여 전체 워크플로우를 실행합니다.
    
    Form Data:
        - text: 평가 대상 텍스트
        - audio: WAV 오디오 파일
    
    Response: {
        "gtp": {...},
        "model": {...},
        "score": {...},
        "overall_score": 85.5
    }
    """
    import time
    start_time = time.time()

    def _parse_bool(value: str, default: bool = True) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "y", "on")

    include_ai_feedback = _parse_bool(include_ai, True)
    
    try:
        # 오디오 파일 읽기
        audio_content_raw = await audio.read()
        
        text = text.strip()
        
        if not text:
            return JSONResponse(
                status_code=400,
                content={"error": "text is required"}
            )
        
        if not audio_content_raw:
            return JSONResponse(
                status_code=400,
                content={"error": "audio file is required"}
            )

        try:
            audio_content = _convert_audio_bytes_to_wav16(audio_content_raw)
        except Exception as conv_err:
            return JSONResponse(
                status_code=400,
                content={"error": f"audio convert failed: {conv_err}"}
            )

        recognized_text = None
        if STT_BACKEND == "openai" and client:
            logger.info("[STT] backend=openai whisper-1 start")
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False, dir=str(APP_TMP_DIR)) as tmp:
                    tmp.write(audio_content_raw)
                    tmp_path = tmp.name
                with open(tmp_path, "rb") as f:
                    transcript = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=f,
                        language="ko"
                    )
                recognized_text = (
                    getattr(transcript, "text", None)
                    or transcript.get("text")
                    if isinstance(transcript, dict)
                    else None
                )
                logger.info("[STT] backend=openai success=%s", bool(recognized_text))
            except Exception as stt_err:
                logger.warning("[STT] backend=openai failed: %s", stt_err)
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
        else:
            logger.info("[STT] skipped backend=%s client=%s", STT_BACKEND, bool(client))
        
        # 1) 요청에 사전 계산 정보가 함께 왔다면 그대로 사용
        pre_syll_ltrs = syll_ltrs.strip() if syll_ltrs else None
        pre_syll_phns = syll_phns.strip() if syll_phns else None
        pre_fst = fst.strip() if fst else None

        print(f"[Evaluate] Text: {text}")
        print(f"[Evaluate] Received FST from client: {bool(pre_fst)}")
        print(f"[Evaluate] FST length: {len(pre_fst) if pre_fst else 0}")

        preset = None
        if pre_syll_ltrs and pre_syll_phns and pre_fst:
            print(f"[Evaluate] Using client-provided precomputed data")
            preset = {
                "sentenceKr": text,
                "syll_ltrs": pre_syll_ltrs,
                "syll_phns": pre_syll_phns,
                "fst": pre_fst,
                "source": "client-precomputed"
            }
        else:
            print(f"[Evaluate] Searching for precomputed sentence match")
            preset = find_precomputed_sentence(text)
            if preset:
                print(f"[Evaluate] Found preset: {preset.get('sentence', '')}")

        if preset and preset.get("fst"):
            print(f"[Evaluate] Using preset for scoring")
            # SpeechPro의 scorejson은 `id`를 키로 내부 상태를 캐시/공유하는 구현이 있을 수 있어,
            # 고정된 id(preset_score 등)를 반복 사용하면 간헐적으로 5xx가 발생할 수 있다.
            import uuid
            preset_id = str(preset.get("id") or "preset").strip() or "preset"
            request_id = f"preset_{preset_id}_{uuid.uuid4().hex[:8]}"

            gtp_dict = {
                "id": f"gtp_{request_id}",
                "text": text,
                "syll_ltrs": preset.get("syll_ltrs", ""),
                "syll_phns": preset.get("syll_phns", ""),
                "error_code": 0,
            }
            model_dict = {
                "id": f"model_{request_id}",
                "text": text,
                "syll_ltrs": preset.get("syll_ltrs", ""),
                "syll_phns": preset.get("syll_phns", ""),
                "fst": preset.get("fst", ""),
                "error_code": 0,
            }

            print(f"[Evaluate] Calling score API...")
            speechpro_start = time.time()
            score_result = call_speechpro_score(
                text=text,
                syll_ltrs=preset.get("syll_ltrs", ""),
                syll_phns=preset.get("syll_phns", ""),
                fst=preset.get("fst", ""),
                audio_data=audio_content,
                request_id=request_id,
            )
            speechpro_time = time.time() - speechpro_start

            print(f"[Evaluate] Score result: score={score_result.score}, error_code={score_result.error_code}")

            if score_result.error_code != 0:
                print(f"[Evaluate] Score error detected: {score_result.error_code}")
                raise RuntimeError(f"Score 오류: error_code={score_result.error_code}")

            # AI 피드백 생성
            ai_feedback = None
            ai_feedback_start = time.time()
            if include_ai_feedback and MODEL_BACKEND in ("ollama", "openai", "gemini"):
                try:
                    ai_feedback = await _generate_pronunciation_feedback(text, score_result)
                    print(f"[Evaluate] AI feedback generated: {ai_feedback[:100] if ai_feedback else 'None'}")
                except Exception as fb_err:
                    print(f"[Evaluate] AI feedback failed: {fb_err}")
            ai_feedback_time = time.time() - ai_feedback_start

            print(f"[Evaluate] Success - returning response")
            elapsed_time = time.time() - start_time
            
            response_data = {
                "gtp": gtp_dict,
                "model": model_dict,
                "score": score_result.to_dict(),
                "overall_score": score_result.score,
                "success": True,
                "source": preset.get("source", "precomputed"),
                "evaluation_time": round(elapsed_time, 2),
                "speechpro_time": round(speechpro_time, 2),
                "ai_model": f"{MODEL_BACKEND}/{OLLAMA_MODEL if MODEL_BACKEND == 'ollama' else GEMINI_MODEL if MODEL_BACKEND == 'gemini' else OPENAI_MODEL}",
                "ai_feedback_time": round(ai_feedback_time, 2) if ai_feedback else None
            }
            if recognized_text:
                response_data["recognized_text"] = recognized_text
            if ai_feedback:
                response_data["ai_feedback"] = ai_feedback
            
            return JSONResponse(content=response_data)

        # 2) 프리셋이 없으면 기존 전체 워크플로우 수행
        print(f"[Evaluate] No preset found, using full workflow")
        result = speechpro_full_workflow(text, audio_content)
        if recognized_text:
            result["recognized_text"] = recognized_text
        if include_ai_feedback and result.get("success"):
            try:
                score_dict = result.get("score") or {}
                score_result = ScoreResult(
                    score=float(score_dict.get("score", 0) or 0),
                    details=score_dict.get("details", {}),
                    error_code=int(score_dict.get("error_code", 0) or 0),
                )
                ai_feedback = await _generate_pronunciation_feedback(text, score_result)
                if ai_feedback:
                    result["ai_feedback"] = ai_feedback
            except Exception as fb_err:
                print(f"[Evaluate] AI feedback failed (full workflow): {fb_err}")
        return JSONResponse(content=result)
    
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"error": str(e), "success": False}
        )
    except RuntimeError as e:
        return JSONResponse(
            status_code=503,
            content={"error": str(e), "success": False}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Evaluation failed: {str(e)}", "success": False}
        )


@app.post("/api/stt/proxy")
async def stt_proxy(request: STTProxyRequest):
    """Proxy STT JSON requests to avoid browser CORS."""
    base_url = (request.base_url or "").strip().rstrip("/")
    endpoint = (request.endpoint or "").strip()
    if not base_url or not endpoint:
        return JSONResponse(status_code=400, content={"error": "base_url and endpoint are required"})

    url = f"{base_url}{endpoint}"
    try:
        resp = requests.post(url, json=request.payload, timeout=30)
        if resp.status_code >= 400:
            return JSONResponse(
                status_code=resp.status_code,
                content={
                    "error": "Upstream error",
                    "status": resp.status_code,
                    "body": resp.text,
                },
            )
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text}
        return JSONResponse(status_code=resp.status_code, content=data)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Proxy failed: {str(e)}"})


@app.post("/api/stt/scorefile")
async def stt_scorefile(
    base_url: str = Form(...),
    endpoint: str = Form(...),
    config: str = Form(...),
    wav_usr: UploadFile = File(...),
):
    """Proxy STT scorefile multipart request to avoid browser CORS."""
    url = f"{base_url.strip().rstrip('/')}{endpoint.strip()}"
    try:
        audio_content = await wav_usr.read()
        files = {
            "wav_usr": (wav_usr.filename or "audio.wav", audio_content, wav_usr.content_type or "audio/wav")
        }
        data = {"config": config}
        resp = requests.post(url, files=files, data=data, timeout=60)
        if resp.status_code >= 400:
            return JSONResponse(
                status_code=resp.status_code,
                content={
                    "error": "Upstream error",
                    "status": resp.status_code,
                    "body": resp.text,
                },
            )
        try:
            resp_json = resp.json()
        except Exception:
            resp_json = {"raw": resp.text}
        return JSONResponse(status_code=resp.status_code, content=resp_json)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Proxy failed: {str(e)}"})



@app.get("/pricing")
def pricing_page(request: Request):
    """가격 정책 페이지"""
    return templates.TemplateResponse("pricing.html", {"request": request})


@app.get("/sentence-evaluation")
def sentence_evaluation_page(request: Request):
    """문장 학습 페이지"""
    return templates.TemplateResponse("sentence-evaluation.html", {"request": request})

@app.post("/api/chatbot")
async def chatbot_api(request: Request):
    """AI 챗봇 API - 사용자가 선택한 모델로 응답"""
    try:
        data = await request.json()
        user_message = data.get("message", "").strip()
        selected_model = data.get("model", "ollama").strip().lower()
        
        if not user_message:
            return JSONResponse(
                status_code=400,
                content={"error": "메시지를 입력해주세요."}
            )
        
        system_prompt = """당신은 한국어 교육 AI 튜터입니다. 간결하고 명확하게 답변해주세요.
중요: 당신의 모델명이나 기술적 세부사항(EXAONE, Ollama 등)을 언급하지 마세요. 단지 "한국어 학습을 돕는 AI 튜터"라고만 소개하세요."""

        rag_context = ""
        try:
            conn = sqlite3.connect(DB_PATH)
            try:
                _ensure_rag_tables(conn)
                settings = _rag_get_settings(conn)
                if settings.get("enabled"):
                    hits = _rag_search(conn, user_message, top_k=settings.get("top_k", 5))
                    if hits:
                        blocks = []
                        for i, h in enumerate(hits, start=1):
                            title = h.get("title") or ""
                            source = h.get("source") or ""
                            content = (h.get("content") or "").strip()
                            blocks.append(
                                f"[자료 {i}] {title} ({source})\n{content}"
                            )
                        rag_context = "\n\n".join(blocks)
            finally:
                conn.close()
        except Exception:
            rag_context = ""

        prompt = f"{system_prompt}\n\n질문: {user_message}"
        if rag_context:
            prompt += f"\n\n[참고 자료]\n{rag_context}\n\n위 참고 자료를 근거로 답변하되, 모르면 모른다고 말하세요."
        
        # Use Ollama backend
        if selected_model == "ollama":
            try:
                payload = {
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.7
                }
                
                print(f"[Chatbot] Sending request to Ollama API: {OLLAMA_URL}/api/generate")
                print(f"[Chatbot] User message: {user_message}")
                
                response = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=60)
                
                print(f"[Chatbot] Response status: {response.status_code}")
                
                if response.status_code != 200:
                    print(f"[Chatbot] Error response: {response.text[:200]}")
                    return JSONResponse(
                        status_code=500,
                        content={"error": "Ollama 서버 연결 오류"}
                    )
                
                result = response.json()
                
                if "response" in result:
                    ai_response = result["response"].strip()
                    print(f"[Chatbot] Ollama response: {ai_response[:100]}...")

                    # Log AI content
                    session = _extract_session_from_request(request)
                    if session:
                        _log_ai_content(session["user_id"], "chatbot", "ollama", user_message, ai_response)

                    return JSONResponse(content={
                        "response": ai_response,
                        "success": True
                    })
                print(f"[Chatbot] Failed to extract text from response: {result}")
                return JSONResponse(
                    status_code=500,
                    content={"error": "AI 응답을 처리할 수 없습니다."}
                )
            except requests.exceptions.Timeout:
                print("[Chatbot] Timeout error")
                return JSONResponse(
                    status_code=504,
                    content={"error": "Ollama 서버 응답 시간이 초과되었습니다."}
                )
            except requests.exceptions.RequestException as e:
                print(f"[Chatbot] Request error: {str(e)}")
                return JSONResponse(
                    status_code=500,
                    content={"error": f"Ollama 연결 오류: {str(e)}"}
                )
        
        # Use OpenAI backend
        elif selected_model == "openai":
            try:
                if not OPENAI_API_KEY or not client:
                    return JSONResponse(
                        status_code=500,
                        content={"error": "OpenAI API 키가 설정되지 않았습니다."}
                    )
                
                messages = [{"role": "system", "content": system_prompt}]
                if rag_context:
                    messages.append(
                        {
                            "role": "system",
                            "content": f"[참고 자료]\n{rag_context}\n\n위 참고 자료를 근거로 답변하되, 모르면 모른다고 말하세요.",
                        }
                    )
                messages.append({"role": "user", "content": user_message})
                response = client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=1000
                )
                
                ai_response = response.choices[0].message.content.strip()
                print(f"[Chatbot] OpenAI response: {ai_response[:100]}...")
                
                # Log AI content
                session = _extract_session_from_request(request)
                if session:
                    _log_ai_content(session["user_id"], "chatbot", "openai", user_message, ai_response)
                    
                return JSONResponse(content={
                    "response": ai_response,
                    "success": True
                })
            except Exception as e:
                print(f"[Chatbot] OpenAI error: {str(e)}")
                return JSONResponse(
                    status_code=500,
                    content={"error": f"OpenAI 오류: {str(e)}"}
                )
        
        # Use Gemini backend
        elif selected_model == "gemini":
            try:
                if not GEMINI_API_KEY or not gemini_client:
                    return JSONResponse(
                        status_code=500,
                        content={"error": "Gemini API 키가 설정되지 않았거나 google-genai 패키지가 설치되지 않았습니다."}
                    )
                
                response = gemini_client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt
                )
                ai_response = response.text.strip()
                print(f"[Chatbot] Gemini response: {ai_response[:100]}...")
                
                # Log AI content
                session = _extract_session_from_request(request)
                if session:
                    _log_ai_content(session["user_id"], "chatbot", "gemini", user_message, ai_response)
                    
                return JSONResponse(content={
                    "response": ai_response,
                    "success": True
                })
            except Exception as e:
                print(f"[Chatbot] Gemini error: {str(e)}")
                import traceback
                traceback.print_exc()
                return JSONResponse(
                    status_code=500,
                    content={"error": f"Gemini 오류: {str(e)}"}
                )
        
        else:
            return JSONResponse(
                status_code=400,
                content={"error": f"지원하지 않는 모델: {selected_model}"}
            )
        
    except Exception as e:
        print(f"[Chatbot] Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": f"오류가 발생했습니다: {str(e)}"}
        )


@app.post("/api/stt/whisper")
async def stt_whisper(
    file: UploadFile = File(...),
    language: str = Form("ko"),
):
    """OpenAI Whisper STT (direct)."""
    if not OPENAI_API_KEY or client is None:
        return JSONResponse(status_code=501, content={"error": "OpenAI STT is not configured"})

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
        return JSONResponse(status_code=415, content={"error": "Unsupported media type"})

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
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False, dir=str(APP_TMP_DIR)) as tmp:
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
            getattr(transcript, "text", None)
            or transcript.get("text")
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
        return JSONResponse(status_code=500, content={"error": "whisper stt failed", "details": str(err)})
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
            content={"error": "Google Cloud Speech-to-Text is not configured or credentials not found"}
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
        return JSONResponse(status_code=415, content={"error": "Unsupported media type"})

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
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False, dir=str(APP_TMP_DIR)) as tmp:
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
            content={"error": "Google Speech-to-Text failed", "details": str(err)}
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
        return JSONResponse(status_code=501, content={"error": "LOCAL_STT=vosk is required"})

    vosk_model_path = os.getenv("VOSK_MODEL_PATH")
    if not vosk_model_path:
        return JSONResponse(status_code=501, content={"error": "VOSK_MODEL_PATH not configured"})

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
        return JSONResponse(status_code=415, content={"error": "Unsupported media type"})

    tmp_input = None
    tmp_wav = None
    original_name = file.filename or ""
    _, ext = os.path.splitext(original_name)
    ext = ext.lower() or ".wav"

    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False, dir=str(APP_TMP_DIR)) as tmp:
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
        return JSONResponse(status_code=500, content={"error": "vosk stt failed", "details": str(err)})
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

        if not text or not audio_file:
            return JSONResponse(
                status_code=400,
                content={"error": "text and audio are required"}
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
                    "error": fluency_result.get("error", "유창성 분석에 실패했습니다.")
                }
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
            "timestamp": datetime.now().isoformat()
        }

        logger.info(f"FluencyPro analysis completed: accuracy={response_data['accuracy_rate']}%")
        return JSONResponse(content=response_data)

    except Exception as e:
        logger.error(f"FluencyPro analyze error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"서버 오류: {str(e)}"
            }
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
- 유창성 점수: {fluency_data.get('fluency_score', 0)}/100
- 발화 속도: {fluency_data.get('speech_rate', 0):.2f} 음절/초
- 조음 속도: {fluency_data.get('articulation_rate', 0):.2f} 음절/초
- 정확한 음절 비율: {fluency_data.get('correct_syllables_rate', 0):.1f}%
- 쉼표 개수: {fluency_data.get('pause_count', 0)}개

[SpeechPro 정확도 분석]
- 발음 정확도 점수: {speechpro_data.get('score', 0)}/100
- 발음 상세 피드백: {speechpro_data.get('feedback', 'N/A')}

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
                return JSONResponse(status_code=400, content={"error": "GEMINI_API_KEY not configured"})
            
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel(GEMINI_MODEL)
            
            response = model.generate_content(prompt)
            response_text = response.text
        
        elif MODEL_BACKEND == "ollama":
            payload = {"model": OLLAMA_MODEL, "prompt": prompt}
            resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, stream=True, timeout=60)
            
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
            return JSONResponse(status_code=501, content={"error": "Backend not configured"})
        
        # 응답에서 JSON 추출
        parsed_feedback = _parse_model_output(response_text)
        
        if parsed_feedback:
            return JSONResponse(content=parsed_feedback)
        else:
            # 파싱 실패시 기본 구조로 반환
            return JSONResponse(content={
                "overall_comment": "좋은 연습이었습니다!",
                "strengths": ["발음을 명확하게 했습니다"],
                "improvements": ["더 자연스러운 속도로 연습해보세요"],
                "tips": ["매일 꾸준히 연습하세요"],
                "encouragement": "계속 화이팅!"
            })
    
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "combined-feedback failed", "details": str(e)}
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
        cursor.execute(
            "SELECT id, nickname FROM users WHERE nickname = ?",
            (user_id,)
        )
        user_row = cursor.fetchone()
        
        if not user_row:
            return JSONResponse(
                status_code=404,
                content={"error": f"User {user_id} not found"}
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
            (actual_user_id,)
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
            "practice_frequency": "매일" if total >= 7 else "주 3-4회" if total >= 3 else "불규칙",
            "improvement_trend": "상승" if total >= 3 else "데이터 부족",
            "speech_rate_average": round(4.5 + (avg_score / 100), 2),
            "articulation_rate_average": round(4.2 + (avg_score / 120), 2),
            "accuracy_score": round(avg_score, 1),
            "last_practice": datetime.now().isoformat()
        }
        
        return JSONResponse(content=fluency_metrics)

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


# ====================
# Media Generation APIs
# ====================

@app.post("/api/generate-image")
async def generate_image(request: Request):
    """AI 이미지 생성 API (OpenAI DALL-E 3)"""
    try:
        data = await request.json()
        situation = data.get("situation", "").strip()
        style = data.get("style", "illustration")
        quality = data.get("quality", "standard")

        if not situation:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": "상황 설명을 입력해주세요."
                }
            )

        logger.info(f"Image generation request - situation: {situation}, style: {style}, quality: {quality}")

        # 한국어 프롬프트를 영어로 최적화
        enhanced_prompt = enhance_prompt_for_korean_learning(situation, style)

        # DALL-E API 호출 (로컬 저장 포함)
        result = await generate_image_dall_e(
            prompt=enhanced_prompt,
            size=os.getenv("DALLE_IMAGE_SIZE", "1024x1024"),
            quality=quality,
            style=os.getenv("DALLE_STYLE", "vivid"),
            save_locally=True
        )

        if result["success"]:
            logger.info(f"Image generated successfully: {result.get('local_path', result.get('image_url'))}")
            return JSONResponse({
                "success": True,
                "image_url": result.get("image_url"),
                "local_path": result.get("local_path"),
                "revised_prompt": result.get("revised_prompt", enhanced_prompt),
                "prompt": enhanced_prompt
            })
        else:
            logger.error(f"Image generation failed: {result.get('error')}")
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "message": f"이미지 생성 실패: {result.get('error', 'Unknown error')}"
                }
            )

    except Exception as e:
        logger.error(f"Error generating image: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"이미지 생성 중 오류 발생: {str(e)}"
            }
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
        
        return JSONResponse({
            "success": True,
            "music_url": "/static/placeholder-music.mp3",
            "description": f"{mood} 분위기의 {duration}초 배경음악",
            "message": "음악 생성 기능은 개발 중입니다. AI 음악 생성 API 연동이 필요합니다."
        })
        
    except Exception as e:
        print(f"Error generating music: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"음악 생성 중 오류 발생: {str(e)}"
            }
        )

@app.get("/ai-video-learning")
def ai_video_learning(request: Request):
    return templates.TemplateResponse("ai-video-learning.html", {"request": request})


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
                    "mp4": None, "has_mp4": False,
                    "pdf": None, "has_pdf": False,
                    "html": None, "has_html": False,
                }
            ext = f.suffix.lower()
            if ext == ".mp4":
                lessons[key]["mp4"]     = f"/static/videos/{f.name}"
                lessons[key]["has_mp4"] = True
            elif ext == ".pdf":
                lessons[key]["pdf"]     = f"/static/videos/{f.name}"
                lessons[key]["has_pdf"] = True
            elif ext == ".html":
                lessons[key]["html"]     = f"/static/videos/{f.name}"
                lessons[key]["has_html"] = True

    # Group by level
    result: dict = {}
    for item in sorted(lessons.values(), key=lambda x: (x["level"], x["week"], x["session"])):
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
async def get_video_progress(user_id: str):
    """사용자의 전체 동영상 시청 진도를 반환합니다."""
    try:
        conn = sqlite3.connect("data/users.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT video_id, watched_seconds, duration_seconds, completed, last_position, updated_at "
            "FROM user_video_progress WHERE user_id = ?",
            (user_id,)
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
    user_id: str
    video_id: str
    watched_seconds: int = 0
    duration_seconds: int = 0
    last_position: int = 0
    completed: bool = False


@app.post("/api/video-progress")
async def save_video_progress(body: _VideoProgressBody):
    """동영상 시청 진도를 저장합니다."""
    try:
        conn = sqlite3.connect("data/users.db")
        conn.execute("""
            INSERT INTO user_video_progress
                (user_id, video_id, watched_seconds, duration_seconds, completed, last_position, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, video_id) DO UPDATE SET
                watched_seconds = MAX(excluded.watched_seconds, watched_seconds),
                duration_seconds = excluded.duration_seconds,
                completed = MAX(excluded.completed, completed),
                last_position = excluded.last_position,
                updated_at = CURRENT_TIMESTAMP
        """, (body.user_id, body.video_id, body.watched_seconds,
              body.duration_seconds, int(body.completed), body.last_position))
        conn.commit()

        # 완료 시 학습 진도 서비스 연동
        if body.completed:
            try:
                lps = LearningProgressService()
                lps.update_sentence_learned(body.user_id, 1)
            except Exception:
                pass

        conn.close()
        return JSONResponse(content={"saved": True})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    logger.info("Uvicorn 서버 시작: 0.0.0.0:9000")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=9000,
        reload=True,
        log_level="info",
        access_log=True
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
