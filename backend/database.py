from __future__ import annotations

import sqlite3
from pathlib import Path


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
        ensure_learning_aux_tables(conn)
        ensure_content_tables(conn)
        ensure_lms_tables(conn)
        ensure_media_tables(conn)
        ensure_ai_learning_tables(conn)
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


def ensure_ai_learning_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ai_feature_settings (
            feature_key TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ai_coach_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            recommendation_date TEXT NOT NULL,
            routine_json TEXT NOT NULL,
            weakness_json TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, recommendation_date)
        );
        CREATE INDEX IF NOT EXISTS idx_ai_coach_user_date
            ON ai_coach_recommendations(user_id, recommendation_date DESC);

        CREATE TABLE IF NOT EXISTS ai_learning_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT,
            input_text TEXT,
            report_json TEXT NOT NULL,
            ai_used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_ai_learning_reports_user
            ON ai_learning_reports(user_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS speaking_mission_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            mission_id TEXT NOT NULL,
            transcript TEXT,
            score REAL DEFAULT 0,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_speaking_mission_attempts_user
            ON speaking_mission_attempts(user_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS lesson_packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            topic TEXT NOT NULL,
            level TEXT,
            package_json TEXT NOT NULL,
            ai_used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_lesson_packages_user
            ON lesson_packages(user_id, created_at DESC);
        """
    )
    for feature in (
        "ai_coach",
        "ai_feedback_reports",
        "speaking_missions",
        "lesson_packages",
        "admin_ai_insights",
    ):
        conn.execute(
            "INSERT OR IGNORE INTO ai_feature_settings (feature_key, enabled) VALUES (?, 1)",
            (feature,),
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
