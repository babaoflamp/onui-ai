import os
import shutil
import csv
import sqlite3
import hashlib
import hmac
from functools import lru_cache
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, Response
# from openai import OpenAI
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

# SpeechPro 서비스 임포트
from backend.services.speechpro_service import (
    call_speechpro_gtp,
    call_speechpro_model,
    call_speechpro_score,
    speechpro_full_workflow,
    get_speechpro_url,
    set_speechpro_url,
    normalize_spaces,
)

# 학습 진도 서비스 임포트
from backend.services.learning_progress_service import LearningProgressService

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
# OpenAI integration disabled/commented out by user request.
# If you want to re-enable OpenAI, uncomment the import at the top and
# restore `client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None`.
client = None

# Backend selection: set MODEL_BACKEND to 'ollama', 'openai', or 'gemini'
MODEL_BACKEND = os.getenv("MODEL_BACKEND", "ollama")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "exaone")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
# Romanization mode: 'force' = always replace pronunciation with romanizer output;
# 'prefer' = keep model-provided Latin pronunciation if it looks valid (contains ASCII letters).
ROMANIZE_MODE = os.getenv("ROMANIZE_MODE", "force").lower()

# MzTTS Configuration
MZTTS_API_URL = os.getenv("MZTTS_API_URL", "http://112.220.79.218:56014")


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

    with tempfile.TemporaryDirectory() as tmpdir:
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
    """Ensure the users table exists."""
    conn = sqlite3.connect(DB_PATH)
    try:
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
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


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
                time_pref, interests, goal, exam_level, reason, style, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            "SELECT id, email, nickname, password_hash FROM users WHERE email = ?",
            ((email or "").strip().lower(),)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _create_session_token(user_id: int, email: str) -> str:
    """Create a simple JWT-like session token (in production, use proper JWT library)."""
    import secrets
    import time
    
    # Simple format: base64(id|email|timestamp|random)
    timestamp = str(int(time.time()))
    random_str = secrets.token_hex(16)
    data = f"{user_id}|{email}|{timestamp}|{random_str}"
    return base64.b64encode(data.encode()).decode()


def _parse_session_token(token: str) -> dict:
    """Parse session token, return dict with user_id/email or None."""
    try:
        data = base64.b64decode(token.encode()).decode()
        parts = data.split("|")
        if len(parts) >= 2:
            return {"user_id": int(parts[0]), "email": parts[1]}
    except Exception:
        pass
    return None


def _get_user_by_id(user_id: int) -> dict:
    """Fetch full user profile by ID."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, email, nickname, native_lang, affiliation, time_pref,
                   interests, goal, exam_level, reason, style, created_at
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
            return data
        return None
    finally:
        conn.close()



app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
def startup_event():
    # If using Ollama, try to auto-select a suitable model when app starts
    if MODEL_BACKEND == "ollama":
        try:
            _auto_select_ollama_model()
        except Exception as e:
            print(f"Ollama auto-select failed: {e}")
    try:
        _init_user_db()
    except Exception as e:
        print(f"User DB init failed: {e}")

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
                    "level": "PRESET",
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
    if MODEL_BACKEND not in ("ollama", "gemini"):
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
            fluency_info = f"""
FluencyPro 분석:
- 발화 속도: {f.get('speech_rate', f.get('speech rate', 0)):.1f} 음절/초
- 정확 음절: {f.get('correct_syllables', f.get('correct syllable count', 0))}/{f.get('total_syllables', f.get('syllable count', 0))} 
- 음절 정확도: {(f.get('correct_syllables', f.get('correct syllable count', 0))/max(f.get('total_syllables', f.get('syllable count', 1)), 1)*100):.1f}%"""

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

        prompt = f"""당신은 한국어 발음 교육 전문가입니다. 다음 발음 평가 결과를 종합적으로 분석하고 학습자에게 정확하고 도움이 되는 피드백을 제공해주세요.

**평가 대상 문장:** {text}

**종합 평가 결과:**
- 전체 점수: {overall_score}점{speechpro_info}
{fluency_info}
{word_summary}

**피드백 작성 가이드:**
1. 점수 평가 (현재 수준 인정, 구체적 칭찬 포함) - 1-2문장
2. SpeechPro 데이터 기반 정확도 분석 - 2-3문장  
3. FluencyPro 데이터 기반 유창성 분석 - 1-2문장
4. 구체적인 발음 개선 포인트 (어려운 단어 중심) - 2-3가지
5. 효과적인 연습 방법 제안 - 1-2가지

**작성 규칙:**
- 친절하고 격려적인 톤 유지
- 300-500자 이내로 작성
- JSON이나 특수 포맷 없이 일반 텍스트만 사용
- 마크다운 형식 금지"""

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
            
        elif MODEL_BACKEND == "gemini":
            if not GEMINI_API_KEY:
                return None
            
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel(GEMINI_MODEL)
            
            response = model.generate_content(prompt)
            feedback = response.text.strip()
        
        else:
            return None
        
        # Remove any markdown/json artifacts
        feedback = re.sub(r'```.*?```', '', feedback, flags=re.DOTALL)
        feedback = re.sub(r'\{.*?\}', '', feedback, flags=re.DOTALL)
        feedback = feedback.strip()
        
        return feedback if feedback else None
        
    except Exception as e:
        print(f"[AI Feedback] Error: {e}")
        return None

# ==========================================
# 페이지 라우트 (Routes)
# ==========================================
@app.get("/")
def home_dashboard(request: Request):
    """대시보드 홈페이지"""
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

@app.get("/custom-materials")
def custom_materials_page(request: Request):
    """맞춤형 교재 생성 페이지"""
    return templates.TemplateResponse("custom-materials.html", {"request": request})

@app.get("/essay-test")
def essay_test_page(request: Request):
    """한국어 작문 테스트 페이지"""
    return templates.TemplateResponse("essay-test.html", {"request": request})

@app.get("/pronunciation-correction")
def pronunciation_correction_page(request: Request):
    """발음 교정 페이지"""
    return templates.TemplateResponse("pronunciation-correction.html", {"request": request})

@app.get("/word-puzzle")
def word_puzzle_page(request: Request):
    """단어 순서 맞추기 게임"""
    return templates.TemplateResponse("word-puzzle.html", {"request": request})

@app.get("/daily-expression")
def daily_expression_page(request: Request):
    """오늘의 한국어 표현 카드 슬라이더"""
    return templates.TemplateResponse("daily-expression.html", {"request": request})

@app.get("/vocab-garden")
def vocab_garden_page(request: Request):
    """단어 꽃밭 (Vocabulary Garden)"""
    return templates.TemplateResponse("vocab-garden.html", {"request": request})

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

@app.get("/speechpro-practice")
def speechpro_practice_page(request: Request):
    """SpeechPro 발음 정확도 평가"""
    return templates.TemplateResponse("speechpro-practice.html", {"request": request})

@app.get("/fluency-practice")
def fluency_practice_page(request: Request):
    """FluencyPro 유창성 평가"""
    return templates.TemplateResponse("fluency-practice.html", {"request": request})

@app.get("/api-test")
def api_test_page(request: Request):
    """API 테스트 도구"""
    return templates.TemplateResponse("api-test.html", {"request": request})

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

@app.get("/change-password")
def change_password_page(request: Request):
    """비밀번호 변경 페이지"""
    return templates.TemplateResponse("change-password.html", {"request": request})

# ------------------------------------------
# 회원가입 (실제 계정 생성)
# ------------------------------------------
@app.post("/api/signup")
async def signup(payload: dict):
    user = _store_user_signup(payload)
    return {"success": True, "email": user["email"], "nickname": user["nickname"]}


@app.post("/api/landing-intake")
async def landing_intake(payload: dict):
    """Backward compatibility: reuse signup handler."""
    return await signup(payload)


# ------------------------------------------
# 로그인 (계정 인증)
# ------------------------------------------
@app.post("/api/login")
async def login(payload: dict):
    """사용자 로그인: 이메일과 비밀번호로 인증."""
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    if not email or not password:
        raise HTTPException(status_code=400, detail="이메일과 비밀번호를 입력하세요.")

    user = _get_user_by_email(email)
    if not user or not _verify_password(user["password_hash"], password):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다.")

    # Create session token
    token = _create_session_token(user["id"], user["email"])
    
    return {
        "success": True,
        "token": token,
        "email": user["email"],
        "nickname": user["nickname"],
    }


@app.post("/api/logout")
async def logout(request: Request):
    """로그아웃 (클라이언트에서 토큰 삭제)."""
    # In a real system, invalidate token in backend
    # For now, just return success
    return {"success": True}


# ------------------------------------------
# 사용자 프로필 (mypage)
# ------------------------------------------
@app.get("/api/user/profile")
async def get_user_profile(request: Request):
    """로그인한 사용자의 프로필 조회."""
    # Get token from header or query (header preferred for security)
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(status_code=401, detail="토큰이 없습니다.")
    
    parsed = _parse_session_token(token)
    if not parsed:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    
    user = _get_user_by_id(parsed["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    
    # Remove sensitive fields
    user.pop("password_hash", None)
    return {"success": True, "user": user}


@app.post("/api/user/profile/update")
async def update_user_profile(request: Request, payload: dict):
    """사용자 프로필 업데이트 (비밀번호 제외)."""
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


@app.post("/api/user/password/change")
async def change_password(request: Request, payload: dict):
    """사용자 비밀번호 변경."""
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

    # Fallback / default: OpenAI (disabled)
    return JSONResponse(status_code=501, content={"error": "OpenAI integration is disabled in this deployment"})


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

    # Fallback / default: OpenAI (disabled)
    return JSONResponse(status_code=501, content={"error": "OpenAI integration is disabled in this deployment"})

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

    # OpenAI-based Whisper STT is disabled when OpenAI integration is commented out.
    if client is None:
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
            return JSONResponse(status_code=501, content={"error": "OpenAI Whisper STT is disabled in this deployment"})

    file_location = f"temp_{file.filename}"
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

        # 2. OpenAI Whisper로 음성 -> 텍스트 변환 (STT)
        audio_file = open(file_location, "rb")
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="ko"
        )
        user_said = getattr(transcript, "text", None) or transcript.get("text") if isinstance(transcript, dict) else None
        if user_said is None:
            user_said = ""

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
# SpeechPro Evaluation Sentences
# ==========================================

@app.get("/api/speechpro/sentences")
async def get_speechpro_sentences():
    """Get all SpeechPro evaluation sentences"""
    try:
        precomputed = load_speechpro_precomputed_sentences()
        return JSONResponse(content=precomputed)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to load speechpro sentences", "details": str(e)})


@app.get("/api/speechpro/sentences/{sentence_id}")
async def get_speechpro_sentence(sentence_id: int):
    """Get a specific SpeechPro evaluation sentence by ID"""
    try:
        sentences = load_speechpro_precomputed_sentences()
        sentence = next((s for s in sentences if s.get("id") == sentence_id), None)
        if sentence:
            return JSONResponse(content=sentence)
        return JSONResponse(status_code=404, content={"error": "Sentence not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to load speechpro sentence", "details": str(e)})


@app.get("/api/speechpro/sentences/level/{level}")
async def get_speechpro_sentences_by_level(level: str):
    """Get SpeechPro evaluation sentences by level (A1, A2, B1, etc.)"""
    try:
        sentences = load_speechpro_precomputed_sentences()
        filtered = [s for s in sentences if s.get("level") == level.upper()]
        return JSONResponse(content=filtered)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to load speechpro sentences", "details": str(e)})


# ==========================================
# MzTTS API Endpoints
# ==========================================

@app.get("/api/tts/info")
async def get_tts_info():
    """Get MzTTS server information"""
    try:
        info = get_mztts_server_info()
        return JSONResponse(content=info)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to get TTS server info", "details": str(e)}
        )


from pydantic import BaseModel

class TTSRequest(BaseModel):
    text: str
    speaker: int = 0
    tempo: float = 1.0
    pitch: float = 1.0
    gain: float = 1.0

@app.post("/api/tts/generate")
async def generate_tts(request: TTSRequest):
    """
    Generate Korean speech using MzTTS API.

    Parameters:
    - text: Korean text to synthesize
    - speaker: Speaker ID (0: Hanna - female voice, default)
    - tempo: Speed (0.1-2.0, default 1.0)
    - pitch: Pitch (0.1-2.0, default 1.0)
    - gain: Volume (0.1-2.0, default 1.0)

    Returns WAV audio file
    """
    try:
        from fastapi.responses import Response

        # Call MzTTS API
        result = _call_mztts_api(
            text=request.text,
            output_type="file",
            speaker=request.speaker,
            tempo=request.tempo,
            pitch=request.pitch,
            gain=request.gain
        )

        # Return WAV file
        import hashlib
        filename_hash = hashlib.md5(request.text.encode('utf-8')).hexdigest()[:8]
        return Response(
            content=result["audio_data"],
            media_type=result["content_type"],
            headers={
                "Content-Disposition": f'attachment; filename="tts_{filename_hash}.wav"'
            }
        )

    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid parameters", "details": str(e)}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "TTS generation failed", "details": str(e)}
        )


# ==========================================
# SpeechPro API 엔드포인트
# ==========================================

@app.post("/api/speechpro/gtp")
async def speechpro_gtp(data: dict = None):
    """
    GTP (Grapheme-to-Phoneme) API
    한국어 텍스트를 음소로 변환합니다.
    
    Request: {"text": "안녕하세요"}
    Response: {"id": "...", "text": "...", "syll_ltrs": "...", "syll_phns": "..."}
    """
    try:
        if data is None:
            data = {}
        
        text = data.get("text", "").strip()
        if not text:
            return JSONResponse(
                status_code=400,
                content={"error": "text is required"}
            )
        
        result = call_speechpro_gtp(text)
        return JSONResponse(content=result.to_dict())
    
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"error": str(e)}
        )
    except RuntimeError as e:
        return JSONResponse(
            status_code=503,
            content={"error": str(e)}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"GTP processing failed: {str(e)}"}
        )


@app.post("/api/speechpro/model")
async def speechpro_model(data: dict = None):
    """
    Model API - FST 발음 모델 생성
    GTP 결과를 바탕으로 발음 평가 모델을 생성합니다.
    
    Request: {
        "text": "안녕하세요",
        "syll_ltrs": "안_녕_하_세_요",
        "syll_phns": "..."
    }
    Response: {"id": "...", "text": "...", "fst": "..."}
    """
    try:
        if data is None:
            data = {}
        
        text = data.get("text", "").strip()
        syll_ltrs = data.get("syll_ltrs", "").strip()
        syll_phns = data.get("syll_phns", "").strip()
        
        if not all([text, syll_ltrs, syll_phns]):
            return JSONResponse(
                status_code=400,
                content={"error": "text, syll_ltrs, syll_phns are required"}
            )
        
        result = call_speechpro_model(text, syll_ltrs, syll_phns)
        return JSONResponse(content=result.to_dict())
    
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"error": str(e)}
        )
    except RuntimeError as e:
        return JSONResponse(
            status_code=503,
            content={"error": str(e)}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Model processing failed: {str(e)}"}
        )


@app.post("/api/speechpro/score")
async def speechpro_score(
    text: str = Form(...),
    syll_ltrs: str = Form(...),
    syll_phns: str = Form(...),
    fst: str = Form(...),
    audio: UploadFile = File(...)
):
    """
    Score JSON API - 발음 평가
    사용자의 음성 데이터를 전송하여 발음 정확도를 평가합니다.
    
    Form Data:
        - text: 평가 대상 텍스트
        - syll_ltrs: 음절 글자
        - syll_phns: 음절 음소
        - fst: FST 모델 데이터
        - audio: WAV 오디오 파일
    
    Response: {"score": 85.5, "details": {...}}
    """
    try:
        # 오디오 파일 읽기
        audio_content_raw = await audio.read()
        
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
        
        # 필수 파라미터 검증
        text = text.strip()
        if not all([text, syll_ltrs, syll_phns, fst]):
            return JSONResponse(
                status_code=400,
                content={"error": "text, syll_ltrs, syll_phns, fst are required"}
            )
        
        result = call_speechpro_score(text, syll_ltrs, syll_phns, fst, audio_content)
        return JSONResponse(content=result.to_dict())
    
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"error": str(e)}
        )
    except RuntimeError as e:
        return JSONResponse(
            status_code=503,
            content={"error": str(e)}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Score processing failed: {str(e)}"}
        )


@app.post("/api/speechpro/evaluate")
async def speechpro_evaluate(
    text: str = Form(...),
    audio: UploadFile = File(...),
    syll_ltrs: str = Form(None),
    syll_phns: str = Form(None),
    fst: str = Form(None)
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
            request_id = f"preset_{preset.get('id', 'score')}"

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
            score_result = call_speechpro_score(
                text=text,
                syll_ltrs=preset.get("syll_ltrs", ""),
                syll_phns=preset.get("syll_phns", ""),
                fst=preset.get("fst", ""),
                audio_data=audio_content,
                request_id=request_id,
            )

            print(f"[Evaluate] Score result: score={score_result.score}, error_code={score_result.error_code}")

            if score_result.error_code != 0:
                print(f"[Evaluate] Score error detected: {score_result.error_code}")
                raise RuntimeError(f"Score 오류: error_code={score_result.error_code}")

            # AI 피드백 생성
            ai_feedback = None
            if MODEL_BACKEND == "ollama":
                try:
                    ai_feedback = await _generate_pronunciation_feedback(text, score_result)
                    print(f"[Evaluate] AI feedback generated: {ai_feedback[:100] if ai_feedback else 'None'}")
                except Exception as fb_err:
                    print(f"[Evaluate] AI feedback failed: {fb_err}")

            print(f"[Evaluate] Success - returning response")
            response_data = {
                "gtp": gtp_dict,
                "model": model_dict,
                "score": score_result.to_dict(),
                "overall_score": score_result.score,
                "success": True,
                "source": preset.get("source", "precomputed")
            }
            if ai_feedback:
                response_data["ai_feedback"] = ai_feedback
            
            return JSONResponse(content=response_data)

        # 2) 프리셋이 없으면 기존 전체 워크플로우 수행
        print(f"[Evaluate] No preset found, using full workflow")
        result = speechpro_full_workflow(text, audio_content)
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


@app.get("/chatbot")
def chatbot_page(request: Request):
    """AI 챗봇 페이지"""
    return templates.TemplateResponse("chatbot.html", {"request": request})


@app.post("/api/chatbot")
async def chatbot_api(request: Request):
    """EXAONE 기반 챗봇 API"""
    try:
        data = await request.json()
        user_message = data.get("message", "").strip()
        
        if not user_message:
            return JSONResponse(
                status_code=400,
                content={"error": "메시지를 입력해주세요."}
            )
        
        # Call Ollama API (EXAONE)
        system_prompt = """당신은 한국어 교육 AI 튜터입니다. 간결하고 명확하게 답변해주세요."""
        
        prompt = f"{system_prompt}\n\n질문: {user_message}"
        
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
                content={"error": "AI 서버 연결 오류"}
            )
        
        result = response.json()
        
        # Extract text from Ollama response
        if "response" in result:
            ai_response = result["response"].strip()
            print(f"[Chatbot] AI response: {ai_response[:100]}...")
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
            content={"error": "AI 서버 응답 시간이 초과되었습니다."}
        )
    except requests.exceptions.RequestException as e:
        print(f"[Chatbot] Request error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"AI 서버 연결 오류: {str(e)}"}
        )
    except Exception as e:
        print(f"[Chatbot] Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": f"오류가 발생했습니다: {str(e)}"}
        )


@app.get("/api/speechpro/config")
async def speechpro_config():
    """SpeechPro API 설정 조회"""
    return JSONResponse(content={
        "url": get_speechpro_url(),
        "status": "configured"
    })


@app.post("/api/speechpro/config")
async def set_speechpro_config(data: dict = None):
    """SpeechPro API URL 설정"""
    try:
        if data is None:
            data = {}
        
        url = data.get("url", "").strip()
        if not url:
            return JSONResponse(
                status_code=400,
                content={"error": "url is required"}
            )
        
        set_speechpro_url(url)
        return JSONResponse(content={
            "url": get_speechpro_url(),
            "status": "updated"
        })
    
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


# ============================================================================
# FluencyPro API (유창성 평가)
# ============================================================================

@app.post("/api/fluencypro/analyze")
async def fluency_analyze(request: Request):
    """음성 유창성 분석 - FluencyPro API"""
    try:
        form_data = await request.form()
        text = form_data.get("text", "").strip()
        audio_file = form_data.get("audio")

        if not text or not audio_file:
            return JSONResponse(
                status_code=400,
                content={"error": "text and audio are required"}
            )

        # 실제 FluencyPro API 호출 (테스트용 더미 응답)
        # TODO: 실제 FluencyPro 서비스 연동
        audio_data = await audio_file.read()
        
        fluency_result = {
            "text": text,
            "audio_length_ms": len(audio_data) // 16,  # 대략적인 오디오 길이 (16KB ≈ 1초)
            "speech_rate": round(len(text.split()) / (len(audio_data) / 16000), 2),  # 음절/초
            "correct_syllables_rate": round((len(text.replace(" ", "")) / len(text.split())) * 100, 1),  # 정확한 음절 비율
            "articulation_rate": round(len(text.split()) / (len(audio_data) / 16000) * 0.95, 2),  # 조음 속도
            "pause_count": len(text.split()) - 1,
            "pause_duration_ms": round(len(audio_data) / 32),  # 쉼표 총 시간
            "fluency_score": round(65 + (len(audio_data) / 16000) * 5, 1),  # 유창성 점수
            "confidence": 0.85,
            "recommendations": [
                "음절을 더 명확하게 발음해주세요.",
                "자연스러운 속도로 말씀해주세요.",
                "적절한 쉼표를 사용하세요."
            ],
            "timestamp": datetime.now().isoformat()
        }

        return JSONResponse(content=fluency_result)

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@app.get("/api/fluencypro/metrics/{user_id}")
async def get_fluency_metrics(user_id: str):
    """사용자 유창성 지표 조회"""
    try:
        # 데이터베이스에서 사용자의 유창성 데이터 조회
        # TODO: 실제 데이터베이스 연동
        
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


# ============================================================================
# 학습 진도 및 캐릭터 Pop-Up API
# ============================================================================

learning_service = LearningProgressService()

@app.post("/api/learning/pronunciation-completed")
async def record_pronunciation_completed(request: Request):
    """발음 연습 완료 기록"""
    try:
        data = await request.json()
        user_id = data.get("user_id", "anonymous")
        score = int(data.get("score", 0))
        
        result = learning_service.update_pronunciation_practice(user_id, score)
        
        # Pop-Up 트리거 확인
        popup_trigger = learning_service.check_popup_trigger(user_id)
        
        return JSONResponse({
            "success": True,
            "updated": result,
            "popup": popup_trigger
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@app.post("/api/learning/popup-shown")
async def record_popup_shown(request: Request):
    """Pop-Up 표시 기록"""
    try:
        data = await request.json()
        user_id = data.get("user_id", "anonymous")
        popup_type = data.get("popup_type")
        character = data.get("character")
        message = data.get("message")
        trigger_reason = data.get("trigger_reason", "user_activity")
        
        learning_service.record_popup_shown(
            user_id, popup_type, character, message, trigger_reason
        )
        
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@app.get("/api/learning/user-stats/{user_id}")
async def get_user_learning_stats(user_id: str):
    """사용자 학습 통계 조회"""
    try:
        stats = learning_service.get_user_stats(user_id)
        return JSONResponse(stats)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@app.get("/api/learning/today-progress/{user_id}")
async def get_today_progress(user_id: str):
    """오늘의 학습 진도 조회"""
    try:
        progress = learning_service.get_or_create_today_progress(user_id)
        return JSONResponse(progress)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@app.post("/api/learning/check-popup/{user_id}")
async def check_popup_trigger(user_id: str):
    """Pop-Up 트리거 확인"""
    try:
        popup = learning_service.check_popup_trigger(user_id)
        if popup:
            return JSONResponse({
                "should_show_popup": True,
                "character": popup.get("character", "오빠"),
                "popup_message": popup.get("message", ""),
                "popup_type": popup.get("type", "info"),
                "trigger": popup.get("trigger", "")
            })
        else:
            return JSONResponse({
                "should_show_popup": False,
                "character": None,
                "popup_message": None,
                "popup_type": None,
                "trigger": None
            })
    except Exception as e:
        print(f"Error checking popup: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=9000, reload=True)