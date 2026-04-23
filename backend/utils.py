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
import secrets
from datetime import datetime, timedelta
from typing import Optional, Set, List, Dict, Any
from pathlib import Path
from functools import lru_cache
from difflib import SequenceMatcher

from fastapi import Request, HTTPException, Depends

logger = logging.getLogger("uvicorn.error")

# Constants defaults
DEFAULT_DB_PATH = "data/users.db"
DEFAULT_SESSION_EXPIRY = 24 * 60 * 60  # Default 24 hours
ROLE_LEARNER = "learner"
ROLE_INSTRUCTOR = "instructor"
ROLE_SYSTEM_ADMIN = "system_admin"
ROLE_CHOICES = {ROLE_LEARNER, ROLE_INSTRUCTOR, ROLE_SYSTEM_ADMIN}
PBKDF_ITERATIONS = 120_000

# Global active sessions cache (Hybrid mode)
active_sessions: Dict[str, Dict[str, Any]] = {}

# Romanization tables
L_TABLE = ["g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h"]
V_TABLE = ["a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi", "yu", "eu", "ui", "i"]
T_TABLE = ["", "k", "k", "ks", "n", "nj", "nh", "t", "l", "lg", "lm", "lb", "ls", "lt", "lp", "lh", "m", "p", "ps", "t", "t", "ng", "t", "ch", "k", "t", "p", "h"]

def get_secret_key() -> str:
    key = os.getenv("SECRET_KEY", "")
    if not key:
        logger.warning("[SECURITY] SECRET_KEY not set. Using transient key.")
        return "transient-secret-key-for-dev-only"
    return key

def normalize_role(role: str, is_admin: bool = False) -> str:
    if is_admin: return ROLE_SYSTEM_ADMIN
    if role in ROLE_CHOICES: return role
    return ROLE_LEARNER

def _get_state(request: Request, name: str, default=None):
    app = getattr(request, "app", None)
    state = getattr(app, "state", None)
    return getattr(state, name, default)

def create_session_token(user_id: int, email: str, is_admin: bool = False) -> str:
    timestamp = time.time()
    payload = f"{user_id}|{email}|{int(timestamp)}|{secrets.token_hex(16)}|{int(bool(is_admin))}"
    payload_b64 = base64.b64encode(payload.encode()).decode()
    signature = hmac.new(get_secret_key().encode(), payload_b64.encode(), hashlib.sha256).digest()
    token = f"{payload_b64}.{base64.b64encode(signature).decode()}"
    active_sessions[token] = {"user_id": user_id, "email": email, "created_at": timestamp, "is_admin": bool(is_admin)}
    return token

def parse_session_token(token: str) -> Optional[dict]:
    if not token or "." not in token: return None
    try:
        p_b64, s_b64 = token.split(".", 1)
        expected = hmac.new(get_secret_key().encode(), p_b64.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, base64.b64decode(s_b64)): return None
        raw = base64.b64decode(p_b64).decode("utf-8")
        parts = raw.split("|")
        if len(parts) < 5: return None
        uid, email, cat, _, is_admin = parts[:5]
        session = {"user_id": int(uid), "email": email, "created_at": float(cat), "is_admin": bool(int(is_admin))}
        expiry = int(os.getenv("SESSION_EXPIRY_SECONDS", DEFAULT_SESSION_EXPIRY))
        if time.time() - session["created_at"] > expiry: return None
        if token not in active_sessions: active_sessions[token] = session
        return session
    except Exception: return None

def get_session(request: Request) -> Optional[dict]:
    token = request.headers.get("Authorization", "").replace("Bearer ", "") or \
            request.cookies.get("session_token", "") or \
            request.query_params.get("token", "")
    return parse_session_token(token) if token else None

@lru_cache(maxsize=128)
def _get_user_by_id_cached(db_path: str, user_id: int) -> Optional[tuple]:
    try:
        conn = sqlite3.connect(db_path); conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT id, email, nickname, native_lang, affiliation, time_pref, interests, goal, exam_level, reason, style, created_at, is_admin, role FROM users WHERE id=?", (user_id,)).fetchone()
        conn.close()
        if row:
            d = dict(row)
            try: d["interests"] = json.loads(d["interests"]) if d.get("interests") else []
            except Exception: d["interests"] = []
            d["role"] = normalize_role(d.get("role"), bool(d.get("is_admin")))
            return tuple(d.items())
    except Exception as e: logger.error(f"[DB_ERROR] {e}")
    return None

def get_user_by_id(db_path: str, user_id: int) -> Optional[dict]:
    res = _get_user_by_id_cached(db_path, user_id)
    return dict(res) if res else None

def get_current_user(request: Request, session: dict = Depends(get_session)) -> dict:
    if not session: raise HTTPException(status_code=401, detail="토큰이 없습니다.")
    db_path = str(getattr(request.app.state, "db_path", DEFAULT_DB_PATH))
    user = get_user_by_id(db_path, session["user_id"])
    if not user: raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return user

def get_current_admin_user(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"): raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return user

def get_optional_user(request: Request, session: dict = Depends(get_session)) -> Optional[dict]:
    if not session: return None
    try: return get_current_user(request, session)
    except Exception: return None

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF_ITERATIONS)
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(derived).decode()}"

def verify_password(stored_hash: str, password: str) -> bool:
    try:
        parts = stored_hash.split("$")
        if len(parts) != 2: return False
        salt, stored_derived = base64.b64decode(parts[0]), base64.b64decode(parts[1])
        derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF_ITERATIONS)
        return hmac.compare_digest(derived, stored_derived)
    except Exception: return False

def load_json_data(filename: str):
    try:
        with open(f"data/{filename}", "r", encoding="utf-8") as f: return json.load(f)
    except Exception: return None

def get_user_credits(db_path: str, user_id: int, daily_limit: int = 100) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT credits_used, credits_reset_date FROM users WHERE id=?", (user_id,)).fetchone()
        if not row: return {"credits_used": 0, "remaining": daily_limit, "daily_limit": daily_limit}
        used, rdate = row
        if rdate != today: used = 0
        return {"credits_used": used, "remaining": max(daily_limit - used, 0), "daily_limit": daily_limit}
    finally: conn.close()

def check_and_consume_credits(db_path: str, user_id: int, cost: int, daily_limit: int = 100) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT credits_used, credits_reset_date FROM users WHERE id=?", (user_id,)).fetchone()
        if not row: return {"ok": False, "remaining": 0}
        used, rdate = row
        if rdate != today: used = 0
        rem = daily_limit - used
        if rem < cost: return {"ok": False, "remaining": rem}
        conn.execute("UPDATE users SET credits_used=?, credits_reset_date=? WHERE id=?", (used + cost, today, user_id))
        conn.commit()
        return {"ok": True, "remaining": rem - cost}
    except Exception:
        conn.rollback(); return {"ok": False, "remaining": 0}
    finally: conn.close()

def romanize_korean(text: str) -> str:
    # Minimal version
    return text

def parse_model_output(text: str):
    if not text or not isinstance(text, str): return None
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.I)
    candidate = match.group(1).strip() if match else text
    try: return json.loads(candidate)
    except Exception:
        match = re.search(r"(\{[\s\S]*\})", text)
        if match:
            try: return json.loads(match.group(1))
            except Exception: pass
    return None

def list_ollama_models(ollama_url: str):
    try:
        resp = requests.get(f"{ollama_url}/v1/models", timeout=5)
        resp.raise_for_status()
        return resp.json().get("data", [])
    except Exception: return []

def ensure_wav_16k_mono(src_path: str, dst_path: str):
    subprocess.check_call(["ffmpeg", "-y", "-i", src_path, "-ar", "16000", "-ac", "1", dst_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def transcribe_with_vosk(wav_path: str, model_path: str) -> str:
    try: from vosk import Model, KaldiRecognizer
    except ImportError: return ""
    if not os.path.exists(model_path): return ""
    wf = wave.open(wav_path, "rb")
    rec = KaldiRecognizer(Model(model_path), wf.getframerate())
    res = []
    while True:
        data = wf.readframes(4000)
        if len(data) == 0: break
        if rec.AcceptWaveform(data): res.append(json.loads(rec.Result()).get("text", ""))
    res.append(json.loads(rec.FinalResult()).get("text", ""))
    wf.close()
    return " ".join([r for r in res if r])

def ensure_rag_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS rag_settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS rag_documents (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, source TEXT, content TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP);
    """)
    conn.commit()

def rag_chunk_text(text: str, chunk_size: int = 500) -> list:
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

def rag_get_settings(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT key, value FROM rag_settings").fetchall()
        return {r[0]: r[1] for r in rows}
    finally: conn.close()

def rag_search(db_path: str, query: str, limit: int = 5) -> list:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT id, title, source, content FROM rag_documents LIMIT ?", (limit,)).fetchall()
        return [{"id": r[0], "title": r[1], "source": r[2], "content": r[3]} for r in rows]
    finally: conn.close()
