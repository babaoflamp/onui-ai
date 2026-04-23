import logging
import csv
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.utils import _get_state

logger = logging.getLogger(__name__)
router = APIRouter()


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return bool(row)


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


def _load_total_sentences() -> int:
    path = Path("data/sp_ko_questions.csv")
    if not path.exists():
        return 0
    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            return sum(1 for _ in csv.DictReader(f))
    except Exception:
        return 0


def _load_total_vocabulary() -> int:
    path = Path("data/vocabulary.json")
    if not path.exists():
        return 0
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return len(data) if isinstance(data, list) else 0
    except Exception:
        return 0


def _build_learning_report_summary(conn: sqlite3.Connection, user_id: int) -> dict:
    conn.row_factory = sqlite3.Row
    _ensure_pronunciation_attempt_history_table(conn)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT sentence_id, sentence_text, overall_score, fluency_accuracy, created_at
        FROM pronunciation_attempt_history
        WHERE user_id = ? AND overall_score > 0
        ORDER BY created_at DESC, id DESC
        """,
        (user_id,),
    )
    attempts = [dict(row) for row in cur.fetchall()]

    if not attempts and _table_exists(conn, "sentence_scores"):
        cur.execute(
            """
            SELECT
                sentence_id,
                sentence_text,
                score_latest AS overall_score,
                fluency_accuracy_latest AS fluency_accuracy,
                attempt_count,
                last_attempted_at AS created_at
            FROM sentence_scores
            WHERE (user_id = ? OR user_id = ?) AND score_latest > 0
            ORDER BY last_attempted_at DESC, id DESC
            """,
            (user_id, str(user_id)),
        )
        legacy_rows = [dict(row) for row in cur.fetchall()]
        for row in legacy_rows:
            repeat = max(int(row.get("attempt_count") or 1), 1)
            for _ in range(repeat):
                attempts.append(
                    {
                        "sentence_id": row.get("sentence_id"),
                        "sentence_text": row.get("sentence_text"),
                        "overall_score": row.get("overall_score"),
                        "fluency_accuracy": row.get("fluency_accuracy"),
                        "created_at": row.get("created_at"),
                    }
                )

    total_practices = len(attempts)
    avg_score = round(
        sum(float(a.get("overall_score") or 0) for a in attempts) / total_practices,
        1,
    ) if total_practices else 0
    best_score = round(
        max((float(a.get("overall_score") or 0) for a in attempts), default=0),
        1,
    )

    today_iso = datetime.now().date().isoformat()
    days = {}
    for item in attempts:
        created_at = str(item.get("created_at") or "")
        day = created_at.split(" ")[0] if created_at else today_iso
        bucket = days.setdefault(day, {"date": day, "practices": 0, "duration": 0, "avg_score_sum": 0.0})
        bucket["practices"] += 1
        bucket["avg_score_sum"] += float(item.get("overall_score") or 0)

    study_seconds_total = 0
    today_study_minutes = 0
    if _table_exists(conn, "study_sessions"):
        cur.execute(
            """
            SELECT created_at, COALESCE(duration_seconds, 0) AS duration_seconds
            FROM study_sessions
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,),
        )
        for row in cur.fetchall():
            created_at = str(row["created_at"] or "")
            day = created_at.split(" ")[0] if created_at else today_iso
            minutes = round((int(row["duration_seconds"] or 0)) / 60)
            study_seconds_total += int(row["duration_seconds"] or 0)
            bucket = days.setdefault(day, {"date": day, "practices": 0, "duration": 0, "avg_score_sum": 0.0})
            bucket["duration"] += minutes
            if day == today_iso:
                today_study_minutes += minutes

    daily_log = []
    for day in sorted(days):
        entry = days[day]
        practices = entry["practices"]
        avg_for_day = round((entry["avg_score_sum"] / practices), 1) if practices else 0
        daily_log.append(
            {
                "date": day,
                "practices": practices,
                "duration": entry["duration"],
                "avg_score": avg_for_day,
            }
        )

    window_start = datetime.now().date() - timedelta(days=29)
    daily_window = []
    for offset in range(30):
        d = window_start + timedelta(days=offset)
        iso = d.isoformat()
        found = next((item for item in daily_log if item["date"] == iso), None)
        daily_window.append(found or {"date": iso, "practices": 0, "duration": 0, "avg_score": 0})

    attendance_dates = set()
    if _table_exists(conn, "attendance"):
        cur.execute("SELECT date FROM attendance WHERE user_id = ? ORDER BY date DESC", (user_id,))
        attendance_dates = {str(row["date"]) for row in cur.fetchall() if row["date"]}

    learning_dates = {item["date"] for item in daily_window if item["practices"] > 0 or item["duration"] > 0}
    streak_dates = learning_dates | attendance_dates
    consecutive_days = 0
    check_date = datetime.now().date()
    while check_date.isoformat() in streak_dates:
        consecutive_days += 1
        check_date -= timedelta(days=1)

    words_learned = 0
    if _table_exists(conn, "user_saved_vocab"):
        cur.execute("SELECT COUNT(*) AS cnt FROM user_saved_vocab WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        words_learned = int((row["cnt"] if row else 0) or 0)

    sentences_learned = 0
    if _table_exists(conn, "sentence_scores"):
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM sentence_scores WHERE (user_id = ? OR user_id = ?) AND score_latest > 0",
            (user_id, str(user_id)),
        )
        row = cur.fetchone()
        sentences_learned = int((row["cnt"] if row else 0) or 0)

    content_completed = 0
    if _table_exists(conn, "saved_textbooks"):
        cur.execute("SELECT COUNT(*) AS cnt FROM saved_textbooks WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        content_completed = int((row["cnt"] if row else 0) or 0)

    lecture_present = 0
    lecture_total = 0
    if _table_exists(conn, "lecture_attendance"):
        cur.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'present' THEN 1 ELSE 0 END) AS present_count
            FROM lecture_attendance
            WHERE user_id = ?
            """,
            (user_id,),
        )
        row = cur.fetchone()
        lecture_total = int((row["total"] if row else 0) or 0)
        lecture_present = int((row["present_count"] if row else 0) or 0)
    attendance_rate = round((lecture_present / lecture_total) * 100) if lecture_total else (
        round((len(attendance_dates) / len(streak_dates)) * 100) if streak_dates else 0
    )

    excellent = sum(1 for a in attempts if float(a.get("overall_score") or 0) >= 90)
    good = sum(1 for a in attempts if 80 <= float(a.get("overall_score") or 0) < 90)
    fair = sum(1 for a in attempts if 70 <= float(a.get("overall_score") or 0) < 80)
    need_improvement = sum(1 for a in attempts if float(a.get("overall_score") or 0) < 70)

    activity_items = [
        {"name": "발음 평가", "icon": "🎤", "count": total_practices},
        {"name": "단어 학습", "icon": "📚", "count": words_learned},
        {"name": "문장 학습", "icon": "📝", "count": sentences_learned},
        {"name": "AI 교재", "icon": "🤖", "count": content_completed},
    ]
    activity_total = sum(item["count"] for item in activity_items) or 1
    activity_breakdown = [
        {**item, "pct": round((item["count"] / activity_total) * 100)}
        for item in activity_items
        if item["count"] > 0
    ]

    achievements = []
    if total_practices >= 1:
        achievements.append({"name": "First Eval", "icon": "🌟"})
    if consecutive_days >= 3:
        achievements.append({"name": "3-Day Streak", "icon": "🔥"})
    if avg_score >= 80 and total_practices >= 3:
        achievements.append({"name": "80+ Accuracy", "icon": "⭐"})
    if total_practices >= 5:
        achievements.append({"name": "5 Evaluations", "icon": "💪"})

    return {
        "total_practices": total_practices,
        "avg_score": avg_score,
        "best_score": best_score,
        "total_duration": round(study_seconds_total / 60),
        "learning_days": len(streak_dates),
        "consecutive_days": consecutive_days,
        "daily_log": daily_window,
        "activity_breakdown": activity_breakdown,
        "accuracy_distribution": {
            "excellent": excellent,
            "good": good,
            "fair": fair,
            "need_improvement": need_improvement,
        },
        "achievements": achievements,
        "words_learned": words_learned,
        "words_total": _load_total_vocabulary(),
        "sentences_learned": sentences_learned,
        "sentences_total": _load_total_sentences(),
        "content_completed": content_completed,
        "content_total": 20,
        "attendance_rate": attendance_rate,
        "today_practices": next((item["practices"] for item in daily_window if item["date"] == today_iso), 0),
        "today_duration": next((item["duration"] for item in daily_window if item["date"] == today_iso), today_study_minutes),
        "today_avg_score": next((item["avg_score"] for item in daily_window if item["date"] == today_iso), 0),
    }


@router.post("/api/learning/pronunciation-completed")
async def record_pronunciation_completed(request: Request):
    """발음 연습 완료 기록 (인증 필요)"""
    try:
        require_authenticated_user = _get_state(request, "require_authenticated_user")
        learning_service = _get_state(request, "learning_service")
        if require_authenticated_user is None or learning_service is None:
            return JSONResponse(status_code=500, content={"error": "Auth or learning service not configured"})

        user = require_authenticated_user(request)
        user_id = user["id"]

        data = await request.json()
        logger.info(f"[API_CALL] user_id={user_id} endpoint={request.url.path} method={request.method}")
        score = int(data.get("score", 0))

        result = learning_service.update_pronunciation_practice(user_id, score)
        popup_trigger = learning_service.check_popup_trigger(user_id)
        return JSONResponse({"success": True, "updated": result, "popup": popup_trigger})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/api/learning/sentence-learned")
async def record_sentence_learned(request: Request):
    """문장 학습 완료 기록 (인증 필요)"""
    try:
        require_authenticated_user = _get_state(request, "require_authenticated_user")
        learning_service = _get_state(request, "learning_service")
        if require_authenticated_user is None or learning_service is None:
            return JSONResponse(status_code=500, content={"error": "Auth or learning service not configured"})

        user = require_authenticated_user(request)
        user_id = user["id"]

        data = await request.json()
        logger.info(f"[API_CALL] user_id={user_id} endpoint={request.url.path} method={request.method}")
        count = data.get("count", 1)

        result = learning_service.update_sentence_learned(user_id, count=count)
        popup_trigger = learning_service.check_popup_trigger(user_id)
        return JSONResponse({"success": True, "updated": result, "popup": popup_trigger})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/api/learning/popup-shown")
async def record_popup_shown(request: Request):
    """Pop-Up 표시 기록 (인증 필요)"""
    try:
        require_authenticated_user = _get_state(request, "require_authenticated_user")
        learning_service = _get_state(request, "learning_service")
        if require_authenticated_user is None or learning_service is None:
            return JSONResponse(status_code=500, content={"error": "Auth or learning service not configured"})

        user = require_authenticated_user(request)

        data = await request.json()
        user_id = user["id"]
        popup_type = data.get("popup_type")
        character = data.get("character")
        message = data.get("message")
        trigger_reason = data.get("trigger_reason", "user_activity")

        learning_service.record_popup_shown(user_id, popup_type, character, message, trigger_reason)
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/api/learning/user-stats/{user_id}")
async def get_user_learning_stats(request: Request, user_id: str):
    """사용자 학습 통계 조회 (인증 필요; path param은 무시되고 인증된 사용자 ID 사용)"""
    try:
        require_authenticated_user = _get_state(request, "require_authenticated_user")
        learning_service = _get_state(request, "learning_service")
        if require_authenticated_user is None or learning_service is None:
            return JSONResponse(status_code=500, content={"error": "Auth or learning service not configured"})
        user = require_authenticated_user(request)
        stats = learning_service.get_user_stats(user["id"])
        return JSONResponse(stats)
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"error": e.detail})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/api/learning/report-summary")
async def get_learning_report_summary(request: Request):
    """learning-progress page summary based on real stored activity data."""
    try:
        require_authenticated_user = _get_state(request, "require_authenticated_user")
        db_path = _get_state(request, "db_path")
        if require_authenticated_user is None or not db_path:
            return JSONResponse(status_code=500, content={"error": "Auth or db not configured"})

        user = require_authenticated_user(request)
        conn = sqlite3.connect(db_path)
        try:
            summary = _build_learning_report_summary(conn, int(user["id"]))
            return JSONResponse(summary)
        finally:
            conn.close()
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"error": e.detail})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/api/learning/today-progress/{user_id}")
async def get_today_progress(request: Request, user_id: str):
    """오늘의 학습 진도 조회 (인증 필요; path param은 무시되고 인증된 사용자 ID 사용)"""
    try:
        require_authenticated_user = _get_state(request, "require_authenticated_user")
        learning_service = _get_state(request, "learning_service")
        if require_authenticated_user is None or learning_service is None:
            return JSONResponse(status_code=500, content={"error": "Auth or learning service not configured"})
        user = require_authenticated_user(request)
        progress = learning_service.get_or_create_today_progress(user["id"])
        return JSONResponse(progress)
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"error": e.detail})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/api/learning/check-popup")
async def check_popup_trigger(request: Request):
    """Pop-Up 트리거 확인 (인증 필요)"""
    try:
        require_authenticated_user = _get_state(request, "require_authenticated_user")
        normalize_role = _get_state(request, "normalize_role")
        role_instructor = _get_state(request, "role_instructor")
        role_system_admin = _get_state(request, "role_system_admin")
        learning_service = _get_state(request, "learning_service")
        if (
            require_authenticated_user is None
            or normalize_role is None
            or role_instructor is None
            or role_system_admin is None
            or learning_service is None
        ):
            return JSONResponse(status_code=500, content={"error": "Auth or learning service not configured"})

        user = require_authenticated_user(request)
        role = normalize_role(user.get("role"), user.get("is_admin"))
        if role in (role_instructor, role_system_admin):
            return JSONResponse({"popup": None})

        popup = learning_service.check_popup_trigger(user["id"])
        if popup and popup.get("should_show"):
            return JSONResponse({"popup": popup})
        return JSONResponse({"popup": None})
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"error": e.detail})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/api/learning/word-scores")
async def get_word_scores(request: Request, limit: int = 3):
    """Get per-word score history for the current user."""
    require_authenticated_user = _get_state(request, "require_authenticated_user")
    get_word_score_history = _get_state(request, "get_word_score_history")
    if require_authenticated_user is None or get_word_score_history is None:
        return JSONResponse(status_code=500, content={"error": "Auth or score history not configured"})

    user = require_authenticated_user(request)
    limit = max(1, min(limit, 10))
    history = get_word_score_history(user["id"], limit=limit)
    return JSONResponse({"scores": history})


@router.get("/api/learning/word-scores/recent")
async def get_recent_word_score_target(request: Request):
    """Return the most recently scored word_id for the current user."""
    require_authenticated_user = _get_state(request, "require_authenticated_user")
    db_path = _get_state(request, "db_path")
    if require_authenticated_user is None or not db_path:
        return JSONResponse(status_code=500, content={"error": "Auth or db not configured"})

    user = require_authenticated_user(request)
    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT word_id
            FROM word_score_history
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user["id"],),
        )
        row = cursor.fetchone()
        return JSONResponse({"word_id": row[0] if row else None})
    finally:
        conn.close()


@router.post("/api/learning/word-scores")
async def add_word_score(request: Request):
    """Add a word score entry for the current user."""
    require_authenticated_user = _get_state(request, "require_authenticated_user")
    find_vocab_id_by_word = _get_state(request, "find_vocab_id_by_word")
    db_path = _get_state(request, "db_path")
    if require_authenticated_user is None or find_vocab_id_by_word is None or not db_path:
        return JSONResponse(status_code=500, content={"error": "Auth or db not configured"})

    user = require_authenticated_user(request)
    payload = await request.json()
    word_id = (payload.get("word_id") or "").strip()
    word_text = (payload.get("word_text") or "").strip()
    if not word_id and word_text:
        word_id = find_vocab_id_by_word(word_text)

    score = payload.get("score")
    if not word_id:
        return JSONResponse({"success": False, "skipped": True})
    try:
        score = int(score)
    except Exception:
        raise HTTPException(status_code=400, detail="score must be an integer")
    if score < 0 or score > 100:
        raise HTTPException(status_code=400, detail="score must be 0-100")

    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO word_score_history (user_id, word_id, score)
            VALUES (?, ?, ?)
            """,
            (user["id"], word_id, score),
        )
        conn.commit()
    finally:
        conn.close()

    return JSONResponse({"success": True})


@router.get("/api/learning/sentence-scores")
async def get_sentence_scores(request: Request, limit: int = 3):
    """Get per-sentence score history for the current user."""
    require_authenticated_user = _get_state(request, "require_authenticated_user")
    get_sentence_score_history = _get_state(request, "get_sentence_score_history")
    if require_authenticated_user is None or get_sentence_score_history is None:
        return JSONResponse(status_code=500, content={"error": "Auth or score history not configured"})

    user = require_authenticated_user(request)
    limit = max(1, min(limit, 10))
    history = get_sentence_score_history(user["id"], limit=limit)
    return JSONResponse({"scores": history})


@router.post("/api/learning/sentence-scores")
async def add_sentence_score(request: Request):
    """Add a sentence score entry for the current user."""
    require_authenticated_user = _get_state(request, "require_authenticated_user")
    db_path = _get_state(request, "db_path")
    if require_authenticated_user is None or not db_path:
        return JSONResponse(status_code=500, content={"error": "Auth or db not configured"})

    user = require_authenticated_user(request)
    payload = await request.json()
    sentence_id = payload.get("sentence_id")
    score = payload.get("score")
    if sentence_id is None:
        raise HTTPException(status_code=400, detail="sentence_id is required")
    try:
        sentence_id = int(sentence_id)
    except Exception:
        raise HTTPException(status_code=400, detail="sentence_id must be an integer")
    try:
        score = int(score)
    except Exception:
        raise HTTPException(status_code=400, detail="score must be an integer")
    if score < 0 or score > 100:
        raise HTTPException(status_code=400, detail="score must be 0-100")

    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO sentence_score_history (user_id, sentence_id, score)
            VALUES (?, ?, ?)
            """,
            (user["id"], sentence_id, score),
        )
        conn.commit()
    finally:
        conn.close()

    # 단어 학습 진도 업데이트 (단어 1개 누적)
    learning_service = _get_state(request, "learning_service")
    if learning_service:
        learning_service.update_words_learned(str(user["id"]), 1)

    return JSONResponse({"success": True})
