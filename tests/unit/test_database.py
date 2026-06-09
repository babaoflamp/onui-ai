import sqlite3

from backend.database import initialize_database
from backend.utils import ensure_rag_tables, rag_chunk_text, rag_get_settings


def test_initialize_database_creates_cross_feature_tables(tmp_path):
    db_path = tmp_path / "users.db"

    initialize_database(str(db_path))

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')"
            )
        }
        assert "users" in tables
        assert "saved_textbooks" in tables
        assert "ai_content_history" in tables
        assert "sentence_score_history" in tables
        assert "lecture_attendance" in tables
        assert "study_sessions" in tables
        assert "user_video_progress" in tables
        assert "rag_chunks" in tables

        conn.execute(
            "INSERT INTO saved_textbooks (user_id, topic, dialogue) VALUES (?, ?, ?)",
            (1, "ordering", "[]"),
        )
        conn.execute(
            "INSERT INTO lecture_attendance (user_id, video_id) VALUES (?, ?)",
            (1, "intro"),
        )
        conn.commit()
    finally:
        conn.close()


def test_rag_helpers_match_admin_schema(tmp_path):
    db_path = tmp_path / "users.db"
    conn = sqlite3.connect(db_path)
    try:
        ensure_rag_tables(conn)
        settings = rag_get_settings(conn)
        chunks = rag_chunk_text("abcdef", max_chars=2)

        assert settings["enabled"] is False
        assert settings["top_k"] == 5
        assert chunks == ["ab", "cd", "ef"]

        conn.execute("INSERT INTO rag_documents (title, source, mime_type) VALUES (?, ?, ?)", ("Doc", "test", "text/plain"))
        doc_id = conn.execute("SELECT id FROM rag_documents").fetchone()[0]
        conn.execute("INSERT INTO rag_chunks (document_id, chunk_index, content) VALUES (?, ?, ?)", (doc_id, 0, "hello korean"))
        chunk_id = conn.execute("SELECT id FROM rag_chunks").fetchone()[0]
        conn.execute("INSERT INTO rag_chunks_fts (content, chunk_id) VALUES (?, ?)", ("hello korean", chunk_id))
        conn.commit()
    finally:
        conn.close()
