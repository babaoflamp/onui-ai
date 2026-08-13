from __future__ import annotations

import sqlite3
from pathlib import Path
import base64
import hashlib
import os


DEFAULT_DB_PATH = "data/users.db"


def connect(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def initialize_database(db_path: str = DEFAULT_DB_PATH) -> None:
    conn = connect(db_path)
    try:
        ensure_core_tables(conn)
        ensure_roleplay_tables(conn)
        ensure_learning_aux_tables(conn)
        ensure_content_tables(conn)
        ensure_lms_tables(conn)
        ensure_media_tables(conn)
        ensure_rag_tables(conn)
        conn.commit()
    finally:
        conn.close()


def ensure_core_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            nickname TEXT,
            password_hash TEXT,
            google_id TEXT,
            native_lang TEXT,
            affiliation TEXT,
            time_pref TEXT,
            interests TEXT,
            goal TEXT,
            exam_level TEXT,
            reason TEXT,
            style TEXT,
            created_at TEXT,
            is_admin INTEGER DEFAULT 0,
            role TEXT DEFAULT 'learner',
            credits_used INTEGER DEFAULT 0,
            credits_reset_date TEXT
        );

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

        CREATE TABLE IF NOT EXISTS word_score_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            word_id TEXT NOT NULL,
            score INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_word_score_user_word
            ON word_score_history(user_id, word_id, created_at);

        CREATE TABLE IF NOT EXISTS user_voice_recordings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            sentence_id TEXT,
            file_path TEXT,
            score REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def ensure_roleplay_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_roleplay_scenarios (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            level TEXT NOT NULL DEFAULT 'B1',
            initial_message TEXT NOT NULL,
            persona TEXT NOT NULL DEFAULT '대화 상대',
            era TEXT NOT NULL DEFAULT '현대',
            speaking_style TEXT NOT NULL DEFAULT '친절하고 자연스러운 말투',
            topics_json TEXT NOT NULL DEFAULT '[]',
            goals_json TEXT NOT NULL DEFAULT '[]',
            keywords_json TEXT NOT NULL DEFAULT '[]',
            tts_voice TEXT NOT NULL DEFAULT 'Kore',
            image TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    _add_missing_columns(conn, "user_roleplay_scenarios", {
        "sort_order": "INTEGER NOT NULL DEFAULT 0",
    })
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_roleplay_scenarios_user
            ON user_roleplay_scenarios(user_id, sort_order ASC, updated_at DESC);
        """
    )



def ensure_learning_aux_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS pronunciation_attempt_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            sentence_id TEXT,
            sentence_text TEXT NOT NULL DEFAULT '',
            overall_score REAL DEFAULT 0,
            score REAL,
            accuracy REAL,
            completeness REAL,
            fluency_accuracy REAL DEFAULT 0,
            detail_json TEXT,
            audio_path TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_pron_attempt_history_user
            ON pronunciation_attempt_history(user_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS sentence_score_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            sentence_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_sentence_score_history_user
            ON sentence_score_history(user_id, sentence_id, created_at);
        """
    )
    _add_missing_columns(conn, "pronunciation_attempt_history", {
        "sentence_text": "TEXT NOT NULL DEFAULT ''",
        "overall_score": "REAL DEFAULT 0",
        "score": "REAL",
        "accuracy": "REAL",
        "completeness": "REAL",
        "fluency_accuracy": "REAL DEFAULT 0",
        "detail_json": "TEXT",
        "audio_path": "TEXT",
    })


def ensure_content_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ai_content_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            content_type TEXT,
            model_used TEXT,
            prompt TEXT,
            result TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_ai_content_history_user
            ON ai_content_history(user_id, created_at);

        CREATE TABLE IF NOT EXISTS saved_textbooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            topic TEXT NOT NULL,
            level TEXT,
            dialogue TEXT NOT NULL,
            vocabulary TEXT,
            image_url TEXT,
            saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_saved_textbooks_user
            ON saved_textbooks(user_id, saved_at);

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
    _add_missing_columns(conn, "saved_textbooks", {
        "image_url": "TEXT",
        "saved_at": "TEXT",
    })


def ensure_lms_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS lecture_attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            video_id TEXT NOT NULL,
            week TEXT,
            status TEXT DEFAULT 'absent',
            watched_pct REAL DEFAULT 0,
            study_seconds INTEGER DEFAULT 0,
            attended_at TEXT,
            term_id TEXT DEFAULT '2026-1',
            modified_by INTEGER,
            modified_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, video_id)
        );
        CREATE INDEX IF NOT EXISTS idx_lecture_attendance_user_term
            ON lecture_attendance(user_id, term_id);

        CREATE TABLE IF NOT EXISTS study_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            page TEXT,
            page_type TEXT DEFAULT 'other',
            duration_seconds INTEGER NOT NULL DEFAULT 0,
            term_id TEXT DEFAULT '2026-1',
            device_type TEXT,
            ui_lang TEXT DEFAULT 'en',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_study_sessions_user_term
            ON study_sessions(user_id, term_id, created_at);
        """
    )
    _add_missing_columns(conn, "lecture_attendance", {
        "week": "TEXT",
        "term_id": "TEXT DEFAULT '2026-1'",
        "modified_by": "INTEGER",
        "modified_at": "TEXT",
    })
    _add_missing_columns(conn, "study_sessions", {
        "term_id": "TEXT DEFAULT '2026-1'",
        "device_type": "TEXT",
        "ui_lang": "TEXT DEFAULT 'en'",
    })


def ensure_media_tables(conn: sqlite3.Connection) -> None:
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

        CREATE TABLE IF NOT EXISTS user_video_progress (
            user_id TEXT NOT NULL,
            video_id TEXT NOT NULL,
            watched_seconds INTEGER DEFAULT 0,
            duration_seconds INTEGER DEFAULT 0,
            completed INTEGER DEFAULT 0,
            last_position INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, video_id)
        );
        """
    )


def ensure_rag_tables(conn: sqlite3.Connection) -> None:
    _migrate_legacy_rag_settings(conn)
    conn.executescript(
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
            title TEXT,
            source TEXT,
            mime_type TEXT,
            content TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS rag_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_rag_chunks_document
            ON rag_chunks(document_id, chunk_index);

        CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunks_fts
            USING fts5(content, chunk_id UNINDEXED);
        """
    )
    _add_missing_columns(conn, "rag_documents", {
        "mime_type": "TEXT",
        "content": "TEXT",
    })


def _migrate_legacy_rag_settings(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='rag_settings'"
    ).fetchone()
    if not row:
        return

    columns = {r[1] for r in conn.execute("PRAGMA table_info(rag_settings)").fetchall()}
    if {"id", "enabled", "top_k"}.issubset(columns):
        return

    legacy_enabled = 0
    legacy_top_k = 5
    if {"key", "value"}.issubset(columns):
        try:
            values = {
                str(k): str(v)
                for k, v in conn.execute("SELECT key, value FROM rag_settings").fetchall()
            }
            legacy_enabled = 1 if values.get("enabled", "0").lower() in {"1", "true", "yes", "on"} else 0
            legacy_top_k = int(values.get("top_k", "5") or 5)
        except Exception:
            legacy_enabled = 0
            legacy_top_k = 5

    conn.execute("ALTER TABLE rag_settings RENAME TO rag_settings_legacy")
    conn.execute(
        """
        CREATE TABLE rag_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            enabled INTEGER NOT NULL DEFAULT 0,
            top_k INTEGER NOT NULL DEFAULT 5,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "INSERT INTO rag_settings (id, enabled, top_k) VALUES (1, ?, ?)",
        (legacy_enabled, max(1, min(legacy_top_k, 10))),
    )


def _add_missing_columns(conn: sqlite3.Connection, table_name: str, columns: dict[str, str]) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}")

import re
from typing import Optional
from fastapi import HTTPException
from datetime import datetime
ROLE_LEARNER = "learner"
PBKDF_ITERATIONS = 120_000

def _hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF_ITERATIONS)
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(derived).decode()}"

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def get_user_by_email(db_path: str, email: str) -> Optional[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id, email, nickname, password_hash, is_admin, role FROM users WHERE email=?",
        (email.strip().lower(),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_nickname(db_path: str, nickname: str) -> Optional[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id, email, nickname, password_hash, is_admin, role FROM users WHERE nickname=?",
        (nickname.strip(),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_google_id(db_path: str, google_id: str) -> Optional[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id, email, nickname, password_hash, is_admin, role FROM users WHERE google_id=?",
        (google_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def create_google_user(db_path: str, email: str, nickname: str, google_id: str) -> dict:
    clean_email = (email or "").strip().lower()
    clean_nickname = (nickname or clean_email.split("@")[0]).strip()
    if not clean_email or not EMAIL_REGEX.match(clean_email):
        raise HTTPException(status_code=400, detail="Google 계정 이메일이 올바르지 않습니다.")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            "INSERT INTO users (email, nickname, google_id, created_at, role) VALUES (?,?,?,?,?)",
            (clean_email, clean_nickname, google_id, datetime.utcnow().isoformat(), ROLE_LEARNER),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, email, nickname, password_hash, is_admin, role FROM users WHERE id=?",
            (cursor.lastrowid,)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()

def store_user_signup(db_path: str, payload: dict) -> dict:
    email = (payload.get("email") or "").strip().lower()
    nickname = (payload.get("nickname") or "").strip()
    password = payload.get("password") or ""
    if not (email and EMAIL_REGEX.match(email) and nickname and len(password) >= 8):
        raise HTTPException(status_code=400, detail="입력값이 올바르지 않습니다.")
    
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO users (email, nickname, password_hash, created_at, role) VALUES (?,?,?,?,?)",
            (email, nickname, _hash_password(password), datetime.utcnow().isoformat(), ROLE_LEARNER)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="이미 가입된 이메일입니다.")
    finally:
        conn.close()
    return {"email": email, "nickname": nickname}

def get_word_score_history(db_path: str, user_id: int, word_id: str) -> list:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT score, created_at FROM word_score_history WHERE user_id=? AND word_id=? ORDER BY created_at DESC",
            (user_id, word_id)
        ).fetchall()
        return [{"score": r[0], "date": r[1]} for r in rows]
    finally:
        conn.close()

def get_sentence_score_history(db_path: str, user_id: int, sentence_id: str) -> list:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT score_latest, last_attempted_at FROM sentence_scores WHERE user_id=? AND sentence_id=? ORDER BY last_attempted_at DESC",
            (user_id, sentence_id)
        ).fetchall()
        return [{"score": r[0], "date": r[1]} for r in rows]
    finally:
        conn.close()
