import os
import json
import logging
import sqlite3
from datetime import datetime
from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException, Depends, Form
from fastapi.responses import JSONResponse

from backend.database import ensure_content_tables
from backend.routes.deps import (
    get_current_user,
    load_json_data,
    get_user_credits
)

router = APIRouter()
logger = logging.getLogger("uvicorn.error")


def _ensure_pronunciation_attempt_history_table(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS pronunciation_attempt_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            sentence_id TEXT,
            sentence_text TEXT NOT NULL,
            overall_score REAL DEFAULT 0,
            fluency_accuracy REAL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_pron_attempt_history_user
            ON pronunciation_attempt_history(user_id, created_at DESC);
        """
    )
    conn.commit()


def _load_expressions(preferred_month: Optional[int] = None) -> list[dict]:
    expressions = load_json_data("expressions.json") or []
    if preferred_month is None:
        return expressions
    prioritized = [item for item in expressions if item.get("month") == preferred_month]
    remainder = [item for item in expressions if item.get("month") != preferred_month]
    return prioritized + remainder


def _serialize_saved_textbook(row: sqlite3.Row) -> dict:
    dialogue = []
    vocabulary = []

    if row["dialogue"]:
        try:
            dialogue = json.loads(row["dialogue"])
        except Exception:
            dialogue = []

    if row["vocabulary"]:
        try:
            vocabulary = json.loads(row["vocabulary"])
        except Exception:
            vocabulary = []

    return {
        "id": row["id"],
        "topic": row["topic"],
        "level": row["level"] or "",
        "dialogue": dialogue,
        "vocabulary": vocabulary,
        "imageUrl": row["image_url"] or "",
        "savedAt": row["saved_at"],
    }

def _compute_attendance_streak(conn, user_id: int) -> int:
    cursor = conn.cursor()
    cursor.execute("SELECT date FROM attendance WHERE user_id = ? ORDER BY date DESC", (user_id,))
    rows = cursor.fetchall()
    if not rows:
        return 0
    
    dates = [row[0] for row in rows]
    today = datetime.now().date()
    yesterday = today - __import__("datetime").timedelta(days=1)
    
    streak = 0
    current = today
    
    if dates[0] == today.isoformat():
        streak = 1
        current = yesterday
    elif dates[0] == yesterday.isoformat():
        streak = 0 # started today or yesterday? wait.
        # simpler streak logic:
        pass

    # Simple streak logic
    streak = 0
    check_date = today
    date_set = set(dates)
    
    while check_date.isoformat() in date_set:
        streak += 1
        check_date -= __import__("datetime").timedelta(days=1)
        
    return streak


def _compute_streak_from_dates(date_values: set[str]) -> int:
    if not date_values:
        return 0
    streak = 0
    check_date = datetime.now().date()
    while check_date.isoformat() in date_values:
        streak += 1
        check_date -= __import__("datetime").timedelta(days=1)
    return streak


def _get_dashboard_quick_stats(conn: sqlite3.Connection, user_id: int) -> dict:
    conn.row_factory = sqlite3.Row
    _ensure_pronunciation_attempt_history_table(conn)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT overall_score, created_at
        FROM pronunciation_attempt_history
        WHERE user_id = ? AND overall_score > 0
        ORDER BY created_at DESC, id DESC
        """,
        (user_id,),
    )
    attempt_rows = cursor.fetchall()

    if attempt_rows:
        total_practices = len(attempt_rows)
        avg_score = round(
            sum(float(row["overall_score"] or 0) for row in attempt_rows) / total_practices,
            1,
        )
        learning_dates = {
            str(row["created_at"]).split(" ")[0]
            for row in attempt_rows
            if row["created_at"]
        }
    else:
        cursor.execute(
            """
            SELECT score_latest, attempt_count, last_attempted_at
            FROM sentence_scores
            WHERE (user_id = ? OR user_id = ?) AND score_latest > 0
            """,
            (user_id, str(user_id)),
        )
        score_rows = cursor.fetchall()
        total_practices = sum(int(row["attempt_count"] or 0) for row in score_rows)
        weighted_sum = sum(
            float(row["score_latest"] or 0) * max(int(row["attempt_count"] or 0), 1)
            for row in score_rows
        )
        avg_score = round((weighted_sum / total_practices), 1) if total_practices else 0
        learning_dates = {
            str(row["last_attempted_at"]).split(" ")[0]
            for row in score_rows
            if row["last_attempted_at"]
        }

    cursor.execute(
        "SELECT date FROM attendance WHERE user_id = ? ORDER BY date DESC",
        (user_id,),
    )
    attendance_dates = {str(row["date"]) for row in cursor.fetchall() if row["date"]}
    streak = _compute_streak_from_dates(learning_dates | attendance_dates)

    return {
        "success": True,
        "consecutive_days": streak,
        "avg_score": avg_score,
        "total_practices": total_practices,
    }


@router.get("/api/dashboard/quick-stats")
async def get_dashboard_quick_stats(request: Request, user: dict = Depends(get_current_user)):
    db_path = request.app.state.db_path
    conn = sqlite3.connect(db_path)
    try:
        return _get_dashboard_quick_stats(conn, user["id"])
    finally:
        conn.close()

@router.get("/api/dashboard/recent-pronunciation")
async def get_dashboard_recent_pronunciation(request: Request, user: dict = Depends(get_current_user)):
    db_path = request.app.state.db_path
    user_id = user["id"]
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        _ensure_pronunciation_attempt_history_table(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                sentence_text,
                overall_score AS score_latest,
                fluency_accuracy AS fluency_accuracy_latest,
                created_at AS last_attempted_at
            FROM pronunciation_attempt_history
            WHERE user_id = ? AND overall_score > 0
            ORDER BY created_at DESC, id DESC
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
        if not rows:
            cursor.execute(
                """
                SELECT sentence_text, score_latest, fluency_accuracy_latest, last_attempted_at
                FROM sentence_scores
                WHERE (user_id = ? OR user_id = ?) AND score_latest > 0
                ORDER BY last_attempted_at DESC, id DESC
                """,
                (user_id, str(user_id)),
            )
            rows = cursor.fetchall()
        conn.close()
        if rows:
            recent_items = [dict(row) for row in rows]
            return {
                "success": True,
                "recent": recent_items[0],
                "recent_list": recent_items,
                "total_count": len(recent_items),
            }
        return {
            "success": True,
            "recent": {"sentence_text": "아직 연습한 문장이 없습니다.", "score_latest": 0, "is_sample": True},
            "recent_list": [],
            "total_count": 0,
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.post("/api/attendance/check-in")
async def attendance_check_in(request: Request, user: dict = Depends(get_current_user)):
    db_path = request.app.state.db_path
    today = datetime.now().date().isoformat()
    conn = sqlite3.connect(db_path)
    try:
        ensure_content_tables(conn)
        conn.commit()
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO attendance (user_id, date) VALUES (?, ?)", (user["id"], today))
        conn.commit()
        checked_in = cursor.rowcount > 0
        streak = _compute_attendance_streak(conn, user["id"])
        return {"success": True, "date": today, "checked_in": checked_in, "streak": streak}
    finally:
        conn.close()

@router.get("/api/attendance/month")
async def attendance_month(request: Request, year: int, month: int, user: dict = Depends(get_current_user)):
    db_path = request.app.state.db_path
    start_date = datetime(year, month, 1).date()
    if month == 12: end_date = datetime(year + 1, 1, 1).date()
    else: end_date = datetime(year, month + 1, 1).date()
    conn = sqlite3.connect(db_path)
    try:
        ensure_content_tables(conn)
        conn.commit()
        cursor = conn.cursor()
        cursor.execute("SELECT date FROM attendance WHERE user_id = ? AND date >= ? AND date < ?", (user["id"], start_date.isoformat(), end_date.isoformat()))
        days = [int(r[0].split("-")[2]) for r in cursor.fetchall()]
        streak = _compute_attendance_streak(conn, user["id"])
        return {"success": True, "year": year, "month": month, "days": sorted(days), "streak": streak}
    finally:
        conn.close()

@router.get("/api/expressions")
async def get_expressions(month: Optional[int] = None, user: dict = Depends(get_current_user)):
    return {"success": True, "expressions": _load_expressions(month)}


@router.get("/api/expressions/today")
async def get_today_expressions(user: dict = Depends(get_current_user)):
    return {"success": True, "expressions": _load_expressions(datetime.now().month)}


@router.get("/api/expressions/daily")
async def get_daily_expressions(month: Optional[int] = None, user: dict = Depends(get_current_user)):
    return {"success": True, "expressions": _load_expressions(month)}


@router.get("/api/textbooks")
async def list_saved_textbooks(request: Request, user: dict = Depends(get_current_user)):
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    conn = sqlite3.connect(db_path)
    try:
        ensure_content_tables(conn)
        conn.commit()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, topic, level, dialogue, vocabulary, image_url, saved_at
            FROM saved_textbooks
            WHERE user_id = ?
            ORDER BY saved_at DESC, id DESC
            """,
            (user["id"],),
        )
        textbooks = [_serialize_saved_textbook(row) for row in cursor.fetchall()]
        return {"success": True, "textbooks": textbooks}
    finally:
        conn.close()


@router.post("/api/textbooks")
async def save_textbook(request: Request, user: dict = Depends(get_current_user)):
    payload = await request.json()
    topic = str(payload.get("topic", "") or "").strip()
    level = str(payload.get("level", "") or "").strip()
    dialogue = payload.get("dialogue") or []
    vocabulary = payload.get("vocabulary") or []
    image_url = str(payload.get("imageUrl", "") or "").strip()

    if not topic:
        raise HTTPException(status_code=400, detail="주제가 필요합니다.")
    if not isinstance(dialogue, list) or not dialogue:
        raise HTTPException(status_code=400, detail="대화 데이터가 필요합니다.")
    if not isinstance(vocabulary, list):
        vocabulary = []

    db_path = getattr(request.app.state, "db_path", "data/users.db")
    conn = sqlite3.connect(db_path)
    try:
        ensure_content_tables(conn)
        conn.commit()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO saved_textbooks (user_id, topic, level, dialogue, vocabulary, image_url)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                topic,
                level,
                json.dumps(dialogue, ensure_ascii=False),
                json.dumps(vocabulary, ensure_ascii=False),
                image_url,
            ),
        )
        conn.commit()
        return {"success": True, "id": cursor.lastrowid}
    finally:
        conn.close()


@router.delete("/api/textbooks/{textbook_id}")
async def delete_textbook(textbook_id: int, request: Request, user: dict = Depends(get_current_user)):
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    conn = sqlite3.connect(db_path)
    try:
        ensure_content_tables(conn)
        conn.commit()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM saved_textbooks WHERE id = ? AND user_id = ?",
            (textbook_id, user["id"]),
        )
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="저장된 교재를 찾을 수 없습니다.")
        return {"success": True}
    finally:
        conn.close()

@router.get("/api/vocabulary/levels")
async def get_vocab_levels(user: dict = Depends(get_current_user)):
    vocab = load_json_data("vocabulary.json") or []
    levels = sorted(list(set(str(v.get("level") or v.get("topikLevel") or "Other") for v in vocab)))
    return {"success": True, "levels": levels}

@router.get("/api/vocabulary/list")
async def get_vocab_list(level: str = None, user: dict = Depends(get_current_user)):
    vocab = load_json_data("vocabulary.json") or []
    if level:
        vocab = [v for v in vocab if str(v.get("level") or v.get("topikLevel")) == level]
    return {"success": True, "vocabulary": vocab}

@router.get("/api/kdict/search")
async def search_kdict(q: str, user: dict = Depends(get_current_user)):
    from backend.services.krdict_service import search_dictionary
    result = await search_dictionary(q)
    return {"success": True, "result": result}

@router.get("/data/locales/{filename}")
async def get_locale_file(filename: str):
    """Serve JSON locale files for frontend i18n."""
    safe_name = os.path.basename(filename)
    if not safe_name.endswith(".json"):
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    path = Path("data/locales") / safe_name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Locale not found")
        
    return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))
