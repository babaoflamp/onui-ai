"""
공통 유틸리티 및 인증 의존성
"""
import os
import json
import time
import sqlite3
import logging
import hashlib
import hmac
import base64
import re
import requests
import subprocess
import wave
import tempfile
from datetime import datetime, timedelta
from typing import Optional, Set, List, Dict
from pathlib import Path
from functools import lru_cache
from difflib import SequenceMatcher

from fastapi import Request, HTTPException, Depends

logger = logging.getLogger("uvicorn.error")

# Constants defaults
DEFAULT_DB_PATH = "data/users.db"
DEFAULT_SESSION_EXPIRY = 24 * 60 * 60
ROLE_LEARNER = "learner"
ROLE_SYSTEM_ADMIN = "system_admin"
PBKDF_ITERATIONS = 120_000

# Romanization tables for fallback
L_TABLE = ["g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h"]
V_TABLE = ["a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi", "yu", "eu", "ui", "i"]
T_TABLE = ["", "k", "k", "ks", "n", "nj", "nh", "t", "l", "lg", "lm", "lb", "ls", "lt", "lp", "lh", "m", "p", "ps", "t", "t", "ng", "t", "ch", "k", "t", "p", "h"]

def _normalize_role(role: str, is_admin: bool = False, role_choices: Set[str] = None) -> str:
    """Return a valid role, prioritizing system admin when is_admin is true."""
    if is_admin:
        return ROLE_SYSTEM_ADMIN
    if role_choices and role in role_choices:
        return role
    return ROLE_LEARNER

def _get_state(request: Request, name: str, default=None):
    """Read a value from app.state without raising when missing."""
    app = getattr(request, "app", None)
    state = getattr(app, "state", None)
    return getattr(state, name, default)

@lru_cache(maxsize=128)
def _get_user_by_id_cached(db_path: str, user_id: int, role_choices_tuple: tuple) -> Optional[tuple]:
    """Fetch user row and return as immutable tuple of items for cache safety."""
    try:
        conn = sqlite3.connect(db_path)
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
        conn.close()
        if row:
            data = dict(row)
            if data.get("interests"):
                try:
                    data["interests"] = json.loads(data["interests"])
                except Exception:
                    data["interests"] = []
            
            role_choices = set(role_choices_tuple) if role_choices_tuple else {ROLE_LEARNER, ROLE_SYSTEM_ADMIN}
            data["role"] = _normalize_role(data.get("role"), bool(data.get("is_admin")), role_choices)
            return tuple(data.items())
    except Exception as e:
        logger.error(f"[DB_ERROR] _get_user_by_id_cached: {e}")
    return None

def get_user_by_id(db_path: str, user_id: int, role_choices: Set[str] = None) -> Optional[dict]:
    """Fetch full user profile by ID. Always returns a fresh copy to prevent cache mutation."""
    role_choices_tuple = tuple(sorted(list(role_choices))) if role_choices else (ROLE_LEARNER, ROLE_SYSTEM_ADMIN)
    result = _get_user_by_id_cached(db_path, user_id, role_choices_tuple)
    if result is None:
        return None
    return dict(result)


def _decode_session_token(token: str) -> Optional[dict]:
    """Decode the stateless session token payload so sessions survive process restarts."""
    try:
        raw = base64.b64decode(token).decode("utf-8")
        user_id, email, created_at, _random_str, is_admin = raw.split("|", 4)
        return {
            "user_id": int(user_id),
            "email": email,
            "created_at": float(created_at),
            "is_admin": bool(int(is_admin)),
        }
    except Exception:
        return None

def get_session(request: Request) -> Optional[dict]:
    """Extract and parse session from request, validating against app.state.active_sessions."""
    active_sessions = getattr(request.app.state, "active_sessions", {})
    expiry = getattr(request.app.state, "session_expiry_seconds", DEFAULT_SESSION_EXPIRY)
    
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        token = request.cookies.get("session_token", "")
    if not token:
        token = request.query_params.get("token", "")

    if not token:
        return None

    session = active_sessions.get(token)
    if not session:
        session = _decode_session_token(token)
        if not session:
            return None
        if isinstance(active_sessions, dict):
            active_sessions[token] = session

    if time.time() - session.get("created_at", 0) > expiry:
        if isinstance(active_sessions, dict):
            active_sessions.pop(token, None)
        return None

    return session

def get_current_user(request: Request, session: dict = Depends(get_session)) -> dict:
    """FastAPI Dependency: returns the authenticated user or raises 401/404."""
    if not session:
        raise HTTPException(status_code=401, detail="토큰이 없습니다.")
    
    db_path = str(getattr(request.app.state, "db_path", DEFAULT_DB_PATH))
    role_choices = getattr(request.app.state, "role_choices", {ROLE_LEARNER, ROLE_SYSTEM_ADMIN})
    
    user = get_user_by_id(db_path, session.get("user_id"), role_choices)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
        
    return user

def get_current_admin_user(user: dict = Depends(get_current_user)) -> dict:
    """FastAPI Dependency: returns the authenticated admin user or raises 403."""
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return user

def get_optional_user(request: Request, session: dict = Depends(get_session)) -> Optional[dict]:
    """FastAPI Dependency: returns the user if authenticated, else None."""
    if not session:
        return None
    try:
        return get_current_user(request, session)
    except HTTPException:
        return None

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF_ITERATIONS
    )
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(derived).decode()}"

def verify_password(stored_hash: str, password: str) -> bool:
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

def load_json_data(filename: str):
    path = Path("data") / filename
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load JSON data from {filename}: {e}")
        return None

def get_user_credits(db_path: str, user_id: int, daily_credits: int = 50) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT credits_used, credits_reset_date FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return {"total": daily_credits, "used": 0, "remaining": daily_credits}
        
        used = row["credits_used"] or 0
        reset_date = row["credits_reset_date"]
        today = datetime.now().strftime("%Y-%m-%d")
        
        if reset_date != today:
            return {"total": daily_credits, "used": 0, "remaining": daily_credits}
        
        return {"total": daily_credits, "used": used, "remaining": max(0, daily_credits - used)}
    finally:
        conn.close()

def check_and_consume_credits(db_path: str, user_id: int, cost: int, daily_credits: int = 50) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(db_path)
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
        remaining = daily_credits - credits_used
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

def _romanize_syllable(ch: str) -> str:
    code = ord(ch)
    if code < 0xAC00 or code > 0xD7A3:
        return ch
    SIndex = code - 0xAC00
    TCount = 28
    VCount = 21
    NCount = VCount * TCount
    LIndex = SIndex // NCount
    VIndex = (SIndex % NCount) // TCount
    TIndex = SIndex % TCount
    return L_TABLE[LIndex] + V_TABLE[VIndex] + T_TABLE[TIndex]

def romanize_korean(text: str) -> str:
    try:
        # Try to use Romanizer if available (would need import)
        # For now, use the built-in logic moved from main.py
        return "".join(
            _romanize_syllable(ch) if 0xAC00 <= ord(ch) <= 0xD7A3 else ch
            for ch in text
        )
    except Exception:
        return text

def parse_model_output(text: str):
    if not text or not isinstance(text, str):
        return None
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except Exception:
            pass
    brace_match = re.search(r"(\{[\s\S]*\})", text)
    if brace_match:
        try:
            return json.loads(brace_match.group(1))
        except Exception:
            pass
    return None

def ensure_rag_tables(conn):
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rag_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            source TEXT,
            mime_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rag_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER,
            chunk_index INTEGER,
            content TEXT,
            embedding BLOB,
            FOREIGN KEY(document_id) REFERENCES rag_documents(id)
        )
    """)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rag_chunks_fts'")
    if not cursor.fetchone():
        cursor.execute("CREATE VIRTUAL TABLE rag_chunks_fts USING fts5(content, chunk_id UNINDEXED)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rag_settings (
            id INTEGER PRIMARY KEY,
            enabled INTEGER DEFAULT 0,
            top_k INTEGER DEFAULT 5,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("SELECT id FROM rag_settings WHERE id = 1")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO rag_settings (id, enabled, top_k) VALUES (1, 0, 5)")
    conn.commit()

def rag_chunk_text(text: str, max_chars: int = 700) -> List[str]:
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
    final_chunks: List[str] = []
    for c in chunks:
        if len(c) <= max_chars:
            final_chunks.append(c)
        else:
            for i in range(0, len(c), max_chars):
                final_chunks.append(c[i : i + max_chars].strip())
    return [c for c in final_chunks if c]

def rag_get_settings(conn) -> dict:
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

def rag_search(conn, query: str, top_k: int = 5) -> List[Dict]:
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

def list_ollama_models(ollama_url: str):
    """Return list of models from local Ollama server or raise."""
    try:
        resp = requests.get(f"{ollama_url}/v1/models", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
    except Exception as e:
        raise RuntimeError(f"Failed to list Ollama models: {e}")

def ensure_wav_16k_mono(src_path: str, dst_path: str):
    """Use ffmpeg (must be installed) to convert audio to 16k mono WAV."""
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

def transcribe_with_vosk(wav_path: str, model_path: str) -> str:
    try:
        from vosk import Model, KaldiRecognizer
    except Exception as e:
        raise RuntimeError("VOSK package not available: " + str(e))
    if not os.path.exists(model_path):
        raise RuntimeError(f"VOSK model path not found: {model_path}")
    wf = wave.open(wav_path, "rb")
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
    j = json.loads(rec.FinalResult())
    results.append(j.get("text", ""))
    wf.close()
    return " ".join([r for r in results if r])
