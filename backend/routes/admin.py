import sqlite3
import json
import logging
import os
import re
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from backend.routes.deps import (
    get_current_admin_user, 
    get_optional_user,
    get_user_by_id,
    get_session,
    load_json_data,
    get_user_credits,
    hash_password,
    ensure_rag_tables,
    rag_chunk_text,
    rag_get_settings,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

logger = logging.getLogger("uvicorn.error")

# Log Parsing Constants
_LOG_TS_FORMAT = "%Y-%m-%d %H:%M:%S,%f"
_LOGIN_RE = re.compile(
    r"\[LOGIN\]\s+user=(?P<user>\S+)\s+email=(?P<email>\S+)\s+role=(?P<role>\S+)\s+ip=(?P<ip>\S+)"
)
_PAGE_VIEW_RE = re.compile(
    r"\[PAGE_VIEW\]\s+user=(?P<user>\S+)\s+email=(?P<email>\S*)\s+role=(?P<role>\S*)\s+page=(?P<page>\S+)\s+ip=(?P<ip>\S+)"
)
# Structured log line: "YYYY-MM-DD HH:MM:SS,mmm - logger - LEVEL - message"
_LOG_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s+-\s+\S+\s+-\s+(?P<level>\w+)\s+-\s+(?P<message>.+)$"
)
# New REQUEST format: [REQUEST] METHOD /path | User: nick (email) | IP: ip | Status: code
_REQUEST_NEW_RE = re.compile(
    r"\[REQUEST\]\s+(?P<method>\w+)\s+(?P<path>\S+)\s+\|\s+User:\s+(?P<user_info>.+?)\s*(?:\|\s*IP:\s*(?P<ip>[\w\.\:]+?)\s*)?(?:\|\s*Status:\s*(?P<status>\d+))?$"
)
# Old REQUEST format: [REQUEST] METHOD /path from IP | User: nick (email)
_REQUEST_OLD_RE = re.compile(
    r"\[REQUEST\]\s+(?P<method>\w+)\s+(?P<path>\S+)\s+from\s+(?P<ip>[\w\.]+)\s+\|\s+User:\s+(?P<user_info>.+)$"
)
_USER_NICK_EMAIL_RE = re.compile(r"^(?P<nick>.+?)\s+\((?P<email>[^)]+)\)$")

_LOG_TYPE_CATEGORY_MAP: Dict[str, set] = {
    "access": {"ACCESS"},
    "login": {"LOGIN"},
    "admin": {"ADMIN"},
    "error": {"ERROR"},
    "system": {"SYSTEM"},
}


def _categorize_message(level: str, msg: str) -> str:
    if msg.startswith("[REQUEST]"):
        return "ACCESS"
    if msg.startswith("[LOGIN]"):
        return "LOGIN"
    if msg.startswith("[ADMIN"):
        return "ADMIN"
    if level in ("ERROR", "CRITICAL") or msg.startswith("[ERROR]"):
        return "ERROR"
    return "SYSTEM"


def _parse_log_line_structured(line: str) -> Optional[dict]:
    m = _LOG_LINE_RE.match(line.strip())
    if not m:
        return None
    level = m.group("level")
    msg = m.group("message")
    return {
        "timestamp": m.group("timestamp"),
        "level": level,
        "category": _categorize_message(level, msg),
        "message": msg,
    }


def _parse_access_entry(msg: str) -> Optional[dict]:
    """Parse [REQUEST] or [LOGIN] message into structured access log entry."""
    entry = {"method": "", "path": "", "user": "", "email": "", "ip": "-", "status": ""}
    if msg.startswith("[REQUEST]"):
        m = _REQUEST_NEW_RE.match(msg)
        if not m:
            m = _REQUEST_OLD_RE.match(msg)
        if not m:
            return None
        entry["method"] = m.group("method")
        entry["path"] = m.group("path")
        entry["ip"] = (m.group("ip") or "-").strip()
        entry["status"] = m.group("status") if "status" in m.groupdict() else ""
        user_info = (m.group("user_info") or "").strip()
        um = _USER_NICK_EMAIL_RE.match(user_info)
        if um:
            entry["user"] = um.group("nick")
            entry["email"] = um.group("email")
        else:
            entry["user"] = user_info
    elif msg.startswith("[LOGIN]"):
        lm = _LOGIN_RE.search(msg)
        if not lm:
            return None
        entry["method"] = "POST"
        entry["path"] = "/login"
        entry["user"] = lm.group("user")
        entry["email"] = lm.group("email")
        entry["ip"] = lm.group("ip")
        entry["status"] = "200"
    else:
        return None
    return entry


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


def _extract_log_timestamp(line: str) -> str:
    if not line:
        return ""
    try:
        ts_str = line.split(" - ", 1)[0].strip()
        dt = datetime.strptime(ts_str, _LOG_TS_FORMAT)
        return dt.isoformat(sep=" ", timespec="seconds")
    except Exception:
        return ""


def _last_activity_from_logs(
    nicknames: List[str], limit: int = 50000
) -> Dict[str, Dict]:
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


def _check_admin_for_page(request: Request):
    """For HTML admin pages: returns RedirectResponse to /admin/login if not admin, else None."""
    session = get_session(request)
    if not session:
        return RedirectResponse(url="/admin/login", status_code=302)

    db_path = getattr(request.app.state, "db_path", "data/users.db")
    user = get_user_by_id(db_path, session["user_id"])
    if not user or not user.get("is_admin"):
        return RedirectResponse(url="/admin/login", status_code=302)

    return None

def _get_user_stats(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), SUM(is_admin) FROM users")
        total, admin_count = cursor.fetchone() or (0, 0)
        cursor.execute(
            "SELECT email, nickname, created_at FROM users ORDER BY created_at DESC LIMIT 5"
        )
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

# HTML Pages
@router.get("/admin/login")
def admin_login_page(request: Request):
    return templates.TemplateResponse(request, "admin-login.html")

@router.get("/admin/dashboard")
def admin_dashboard_page(request: Request):
    redirect = _check_admin_for_page(request)
    if redirect: return redirect
    return templates.TemplateResponse(request, "admin-dashboard.html")

@router.get("/admin/users")
def admin_users_page(request: Request):
    redirect = _check_admin_for_page(request)
    if redirect: return redirect
    return templates.TemplateResponse(request, "admin-users.html")

@router.get("/admin")
def admin_shell_page(request: Request):
    redirect = _check_admin_for_page(request)
    if redirect: return redirect
    return templates.TemplateResponse(request, "admin.html")

@router.get("/admin/api")
def admin_api_page(request: Request):
    redirect = _check_admin_for_page(request)
    if redirect: return redirect
    return templates.TemplateResponse(request, "admin-api.html")

@router.get("/admin/system")
def admin_system_page(request: Request):
    redirect = _check_admin_for_page(request)
    if redirect: return redirect
    return templates.TemplateResponse(request, "admin-system.html")

@router.get("/admin/logs")
def admin_logs_page(request: Request):
    redirect = _check_admin_for_page(request)
    if redirect: return redirect
    return templates.TemplateResponse(request, "admin-logs.html")

@router.get("/admin/settings")
def admin_settings_page(request: Request):
    redirect = _check_admin_for_page(request)
    if redirect: return redirect
    return templates.TemplateResponse(request, "admin-settings.html")

# API Endpoints
@router.get("/api/admin/summary")
async def admin_summary(request: Request, admin: dict = Depends(get_current_admin_user)):
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    stats = _get_user_stats(db_path)
    logger.info(f"[ADMIN_SUMMARY] {admin['email']} accessed summary")
    return {
        "success": True,
        "admin": {
            "email": admin["email"],
            "nickname": admin["nickname"],
        },
        "stats": stats,
    }

@router.get("/api/admin/landing-intent-summary")
async def admin_landing_intent_summary(request: Request, limit: int = 5, admin: dict = Depends(get_current_admin_user)):
    limit = max(1, min(limit, 20))
    events = []
    path = Path("data/landing_intent.json")
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, list):
                events = [x for x in loaded if isinstance(x, dict)]
        except Exception:
            events = []

    goal_counts = {}
    level_counts = {}
    reason_counts = {}
    for row in events:
        goal = str(row.get("goal") or "unknown").strip() or "unknown"
        level = str(row.get("level") or "unknown").strip() or "unknown"
        reason = str(row.get("reason") or "unknown").strip() or "unknown"
        goal_counts[goal] = goal_counts.get(goal, 0) + 1
        level_counts[level] = level_counts.get(level, 0) + 1
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    def _top_items(counts: Dict[str, int]):
        return [{"key": k, "count": v} for k, v in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]]

    recent = events[-limit:]
    recent.reverse()
    recent_items = [{"goal": str(x.get("goal") or "unknown"), "level": str(x.get("level") or "unknown"), "reason": str(x.get("reason") or ""), "native_lang": str(x.get("native_lang") or ""), "ts": x.get("ts")} for x in recent]

    logger.info("[ADMIN_LANDING_INTENT] %s retrieved intent summary (events=%s)", admin["email"], len(events))
    return {"success": True, "stats": {"total_events": len(events), "top_goals": _top_items(goal_counts), "top_levels": _top_items(level_counts), "top_reasons": _top_items(reason_counts), "recent": recent_items}}

@router.get("/api/admin/learner/{user_id}/detail")
async def admin_learner_detail(request: Request, user_id: int, admin: dict = Depends(get_current_admin_user)):
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, email, nickname, native_lang, created_at, role FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user: return JSONResponse(status_code=404, content={"success": False, "detail": "User not found"})
        cursor.execute("""
            SELECT SUM(total_learning_time) as total_time, AVG(pronunciation_avg_score) as avg_score, SUM(words_learned) as total_words, SUM(sentences_learned) as total_sentences, SUM(content_generated) as total_content, MAX(achievement_level) as current_level
            FROM user_learning_progress WHERE user_id = ?
        """, (str(user_id),))
        stats = cursor.fetchone()
        return {"success": True, "user": dict(user), "stats": dict(stats) if stats["total_time"] is not None else {"total_time": 0, "avg_score": 0, "total_words": 0, "total_sentences": 0, "total_content": 0, "current_level": "beginner"}}
    except Exception as e:
        logger.error(f"Error fetching learner details: {e}")
        return JSONResponse(status_code=500, content={"success": False, "detail": str(e)})
    finally:
        conn.close()

@router.get("/api/admin/content-history")
async def admin_content_history(request: Request, limit: int = 100, admin: dict = Depends(get_current_admin_user)):
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT h.id, h.content_type, h.model_used, h.created_at, u.nickname as user_nickname, u.email as user_email
            FROM ai_content_history h LEFT JOIN users u ON h.user_id = CAST(u.id AS TEXT)
            ORDER BY h.created_at DESC LIMIT ?
        """, (limit,))
        history = [dict(row) for row in cursor.fetchall()]
        return {"success": True, "history": history}
    finally:
        conn.close()

@router.get("/api/admin/recordings")
async def admin_recordings_history(request: Request, limit: int = 100, admin: dict = Depends(get_current_admin_user)):
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT r.id, r.sentence_id, r.file_path, r.score, r.created_at, u.nickname as user_nickname, u.email as user_email
            FROM user_voice_recordings r LEFT JOIN users u ON r.user_id = CAST(u.id AS TEXT)
            ORDER BY r.created_at DESC LIMIT ?
        """, (limit,))
        recordings = [dict(row) for row in cursor.fetchall()]
        return {"success": True, "recordings": recordings}
    finally:
        conn.close()

@router.get("/api/admin/learner-status")
async def admin_learner_status(request: Request, q: str = "", limit: int = 200, admin: dict = Depends(get_current_admin_user)):
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    role_learner = getattr(request.app.state, "role_learner", "learner")
    limit = max(1, min(int(limit or 200), 500))
    q = (q or "").strip()
    today = datetime.now().date().isoformat()
    since_7d_dt = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    since_7d_date = (datetime.now().date() - timedelta(days=6)).isoformat()
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        where = "WHERE role = ?"
        params: list = [role_learner]
        if q:
            where += " AND (LOWER(nickname) LIKE ? OR LOWER(email) LIKE ?)"
            like = f"%{q.lower()}%"
            params.extend([like, like])
        cursor.execute(f"SELECT id, email, nickname, created_at FROM users {where} ORDER BY created_at DESC LIMIT ?", (*params, limit))
        users = [dict(row) for row in cursor.fetchall()]
        if not users: return {"success": True, "stats": {"learners": 0, "today_attendance": 0, "word_7d": 0, "sentence_7d": 0}, "users": []}
        user_ids = [u["id"] for u in users]
        nicknames = [u.get("nickname") or "" for u in users]
        placeholders = ",".join(["?"] * len(user_ids))
        cursor.execute(f"SELECT user_id, MAX(date) AS last_date, SUM(CASE WHEN date = ? THEN 1 ELSE 0 END) AS today_cnt, SUM(CASE WHEN date >= ? THEN 1 ELSE 0 END) AS days_7d FROM attendance WHERE user_id IN ({placeholders}) GROUP BY user_id", (today, since_7d_date, *user_ids))
        attendance_rows = {row["user_id"]: dict(row) for row in cursor.fetchall()}
        cursor.execute(f"SELECT user_id, COUNT(*) AS total, MAX(created_at) AS last_at, SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS cnt_7d FROM word_score_history WHERE user_id IN ({placeholders}) GROUP BY user_id", (since_7d_dt, *user_ids))
        word_rows = {row["user_id"]: dict(row) for row in cursor.fetchall()}
        cursor.execute(f"SELECT user_id, COUNT(*) AS total, MAX(created_at) AS last_at, SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS cnt_7d FROM sentence_score_history WHERE user_id IN ({placeholders}) GROUP BY user_id", (since_7d_dt, *user_ids))
        sentence_rows = {row["user_id"]: dict(row) for row in cursor.fetchall()}
        cursor.execute(f"SELECT user_id, date FROM attendance WHERE user_id IN ({placeholders})", user_ids)
        attendance_dates = {}
        for row in cursor.fetchall(): attendance_dates.setdefault(row["user_id"], set()).add(row["date"])
        def _streak_from_dates(dates: set) -> int:
            streak = 0; day = datetime.now().date()
            while day.isoformat() in dates: streak += 1; day = day - timedelta(days=1)
            return streak
        streaks = {uid: _streak_from_dates(attendance_dates.get(uid, set())) for uid in user_ids}
    finally:
        conn.close()
    last_activity = _last_activity_from_logs(nicknames, limit=50000)
    merged_users = []; today_attendance = 0; total_word_7d = 0; total_sentence_7d = 0
    for u in users:
        uid = u["id"]; a = attendance_rows.get(uid) or {}; w = word_rows.get(uid) or {}; s = sentence_rows.get(uid) or {}; la = last_activity.get(u.get("nickname") or "", {})
        today_cnt = int(a.get("today_cnt") or 0); today_attendance += 1 if today_cnt > 0 else 0; total_word_7d += int(w.get("cnt_7d") or 0); total_sentence_7d += int(s.get("cnt_7d") or 0)
        merged_users.append({"id": uid, "email": u.get("email") or "", "nickname": u.get("nickname") or "", "created_at": u.get("created_at") or "", "attendance_streak": int(streaks.get(uid) or 0), "last_attendance_date": a.get("last_date") or "", "word_total": int(w.get("total") or 0), "word_last_at": w.get("last_at") or "", "sentence_total": int(s.get("total") or 0), "sentence_last_at": s.get("last_at") or "", "last_login_at": la.get("last_login_at") or "", "last_page_view_at": la.get("last_page_view_at") or "", "last_page": la.get("last_page") or ""})
    return {"success": True, "stats": {"learners": len(merged_users), "today_attendance": today_attendance, "word_7d": total_word_7d, "sentence_7d": total_sentence_7d}, "users": merged_users}

@router.get("/api/admin/logs/download")
async def download_admin_logs(request: Request, admin: dict = Depends(get_current_admin_user)):
    log_path = "logs/detailed.log"
    if not os.path.exists(log_path):
        raise HTTPException(status_code=404, detail="Log file not found.")
    return FileResponse(path=log_path, media_type="text/plain", filename=f"onui_logs_{datetime.now().strftime('%Y%m%d')}.log")

@router.get("/api/admin/logs-tail")
async def admin_logs_tail(
    request: Request,
    level: str = "",
    search: str = "",
    log_type: str = "all",
    date: str = "",
    page: int = 1,
    per_page: int = 100,
    admin: dict = Depends(get_current_admin_user),
):
    log_file = Path("logs/detailed.log")
    if not log_file.exists():
        return {"success": True, "logs": [], "total": 0, "page": 1, "per_page": per_page, "total_pages": 0}
    per_page = min(max(per_page, 10), 500)
    page = max(page, 1)
    level_upper = level.upper() if level else ""
    search_lower = search.lower() if search else ""
    wanted_cats = _LOG_TYPE_CATEGORY_MAP.get(log_type.lower()) if log_type and log_type != "all" else None
    try:
        raw_lines = _read_last_log_lines(log_file, limit=50000)
        filtered = []
        for line in raw_lines:
            entry = _parse_log_line_structured(line)
            if not entry:
                continue
            if date and not entry["timestamp"].startswith(date):
                continue
            if level_upper and entry["level"] != level_upper:
                continue
            if wanted_cats and entry["category"] not in wanted_cats:
                continue
            if search_lower and search_lower not in entry["message"].lower():
                continue
            filtered.append(entry)
        total = len(filtered)
        # newest first
        filtered.reverse()
        start = (page - 1) * per_page
        page_data = filtered[start:start + per_page]
        logger.info(f"[ADMIN_LOGS] {admin['email']} retrieved {len(page_data)} lines (type={log_type}, level={level}, date={date}, page={page})")
        return {
            "success": True,
            "logs": page_data,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": max(1, (total + per_page - 1) // per_page),
        }
    except Exception as e:
        logger.error(f"Failed to read logs: {e}")
        return {"success": False, "detail": str(e)}


@router.get("/api/admin/access-logs")
async def admin_access_logs(
    request: Request,
    user_filter: str = "",
    path_filter: str = "",
    date: str = "",
    page: int = 1,
    per_page: int = 100,
    admin: dict = Depends(get_current_admin_user),
):
    log_file = Path("logs/detailed.log")
    per_page = min(max(per_page, 10), 500)
    page = max(page, 1)
    user_lower = user_filter.lower() if user_filter else ""
    today_str = datetime.now().strftime("%Y-%m-%d")
    filter_date = date if date else today_str

    if not log_file.exists():
        return {"success": True, "logs": [], "total": 0, "page": 1, "per_page": per_page, "total_pages": 0, "stats": {}}
    try:
        raw_lines = _read_last_log_lines(log_file, limit=100000)

        # global stats accumulators (over entire file, no date filter)
        total_requests_g = 0
        unique_users_g: set = set()
        error_count_g = 0
        today_visits_g = 0

        all_access = []
        for line in raw_lines:
            entry = _parse_log_line_structured(line)
            if not entry or entry["category"] not in ("ACCESS", "LOGIN"):
                continue
            parsed = _parse_access_entry(entry["message"])
            if not parsed:
                continue
            parsed["timestamp"] = entry["timestamp"]
            parsed["type"] = entry["category"]

            # accumulate global stats
            total_requests_g += 1
            if parsed["user"] and parsed["user"] not in ("Guest", "-"):
                unique_users_g.add(parsed["user"])
            if parsed["status"] and parsed["status"][:1] in ("4", "5"):
                error_count_g += 1
            if entry["timestamp"].startswith(today_str):
                today_visits_g += 1

            all_access.append(parsed)

        # apply filters
        filtered = []
        for e in all_access:
            if not e["timestamp"].startswith(filter_date):
                continue
            if user_lower and user_lower not in e["user"].lower() and user_lower not in e["email"].lower():
                continue
            if path_filter and not e["path"].startswith(path_filter):
                continue
            filtered.append(e)

        total = len(filtered)
        filtered.reverse()  # newest first
        start = (page - 1) * per_page
        page_data = filtered[start:start + per_page]

        logger.info(f"[ADMIN_ACCESS_LOGS] {admin['email']} retrieved {len(page_data)} entries (date={filter_date})")
        return {
            "success": True,
            "logs": page_data,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": max(1, (total + per_page - 1) // per_page),
            "stats": {
                "total_requests": total_requests_g,
                "unique_users": len(unique_users_g),
                "error_count": error_count_g,
                "today_visits": today_visits_g,
            },
        }
    except Exception as e:
        logger.error(f"Failed to read access logs: {e}")
        return {"success": False, "detail": str(e)}

@router.get("/api/admin/access-summary")
async def admin_access_summary(
    request: Request,
    date: str = "",
    admin: dict = Depends(get_current_admin_user),
):
    log_file = Path("logs/detailed.log")
    today_str = datetime.now().strftime("%Y-%m-%d")
    target_date = date if date else today_str
    db_path = getattr(request.app.state, "db_path", "data/users.db")

    MENU_NAMES = {
        "/": "홈",
        "/dashboard": "대시보드",
        "/video-learning": "비디오 학습",
        "/roleplay": "AI 롤플레이",
        "/voice-call": "AI 음성통화",
        "/onui-grammar": "AI 문법코치",
        "/onui-beats": "OAI Beats",
        "/daily-expression": "오늘의 표현",
        "/sentence-evaluation": "문장 평가",
        "/learning-progress": "학습 진도",
        "/speechpro-practice": "발음 연습",
        "/mypage": "마이페이지",
        "/content-generation": "콘텐츠 생성",
        "/admin/dashboard": "관리 대시보드",
        "/admin/users": "사용자 관리",
        "/admin/logs": "로그 콘솔",
        "/admin/system": "시스템",
        "/admin/settings": "설정",
    }

    def is_menu_path(p: str) -> bool:
        return not p.startswith(("/api/", "/static/", "/data/", "/uploads/", "/openapi", "/favicon"))

    if not log_file.exists():
        return {"success": True, "date": target_date, "users": [], "new_signups": [], "stats": {}}

    try:
        raw_lines = _read_last_log_lines(log_file, limit=200000)
        user_map: Dict[str, dict] = {}
        total_requests = 0
        error_count = 0

        for line in raw_lines:
            entry = _parse_log_line_structured(line)
            if not entry or not entry["timestamp"].startswith(target_date):
                continue
            if entry["category"] not in ("ACCESS", "LOGIN"):
                continue
            parsed = _parse_access_entry(entry["message"])
            if not parsed:
                continue

            ukey = parsed["user"] or "Guest"
            ts = entry["timestamp"]

            if ukey not in user_map:
                user_map[ukey] = {
                    "user": ukey,
                    "email": parsed["email"] or "",
                    "ip": parsed["ip"] or "-",
                    "login_times": [],
                    "_page_order": [],
                    "_page_seen": set(),
                    "request_count": 0,
                    "error_count": 0,
                    "first_seen": ts,
                    "last_seen": ts,
                }
            u = user_map[ukey]
            if parsed["email"] and not u["email"]:
                u["email"] = parsed["email"]
            if ts < u["first_seen"]: u["first_seen"] = ts
            if ts > u["last_seen"]:  u["last_seen"] = ts

            if entry["category"] == "LOGIN":
                u["login_times"].append(ts[11:16])
            else:
                path = parsed["path"]
                status = parsed["status"] or ""
                u["request_count"] += 1
                total_requests += 1
                if status[:1] in ("4", "5"):
                    u["error_count"] += 1
                    error_count += 1
                if is_menu_path(path) and path not in u["_page_seen"]:
                    u["_page_seen"].add(path)
                    u["_page_order"].append({
                        "time": ts[11:16],
                        "path": path,
                        "name": MENU_NAMES.get(path, path),
                    })

        users_out = []
        for u in sorted(user_map.values(), key=lambda x: x["first_seen"], reverse=True):
            users_out.append({
                "user":          u["user"],
                "email":         u["email"],
                "ip":            u["ip"],
                "login_times":   sorted(set(u["login_times"])),
                "pages":         u["_page_order"],
                "request_count": u["request_count"],
                "error_count":   u["error_count"],
                "first_seen":    u["first_seen"][11:16],
                "last_seen":     u["last_seen"][11:16],
            })

        conn = sqlite3.connect(db_path)
        try:
            conn.row_factory = sqlite3.Row
            new_signups = [
                {"nickname": r["nickname"], "email": r["email"],
                 "created_at": (r["created_at"] or "")[:16]}
                for r in conn.execute(
                    "SELECT nickname, email, created_at FROM users "
                    "WHERE created_at LIKE ? ORDER BY created_at DESC",
                    (f"{target_date}%",)
                ).fetchall()
            ]
        finally:
            conn.close()

        logger.info(f"[ADMIN_ACCESS_SUMMARY] {admin['email']} retrieved summary for {target_date}")
        return {
            "success": True,
            "date": target_date,
            "users": users_out,
            "new_signups": new_signups,
            "stats": {
                "total_requests": total_requests,
                "unique_users": len([u for u in users_out if u["user"] not in ("Guest", "-")]),
                "error_count": error_count,
                "new_signups": len(new_signups),
            },
        }
    except Exception as e:
        logger.error(f"Failed to build access summary: {e}")
        return {"success": False, "detail": str(e)}


@router.get("/api/admin/analytics")
async def admin_analytics(request: Request, admin: dict = Depends(get_current_admin_user)):
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    role_learner = getattr(request.app.state, "role_learner", "learner")
    learning_service = getattr(request.app.state, "learning_service", None)
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row; cursor = conn.cursor()
        if learning_service:
            try: learning_service._init_db()
            except Exception: pass
        cursor.execute("SELECT COUNT(*) AS n FROM users"); total_users = int(cursor.fetchone()["n"])
        since_date = (datetime.now().date() - timedelta(days=6)).isoformat()
        cursor.execute("SELECT COUNT(DISTINCT user_id) AS n FROM user_learning_progress WHERE date >= ?", (since_date,))
        active_users = int(cursor.fetchone()["n"] or 0)
        cursor.execute("SELECT AVG(total_learning_time) AS avg_minutes, AVG(NULLIF(pronunciation_avg_score, 0)) AS avg_score FROM user_learning_progress WHERE date >= ?", (since_date,))
        row = cursor.fetchone() or {}; avg_minutes = float(row["avg_minutes"] or 0); avg_score = float(row["avg_score"] or 0); avg_hours = avg_minutes / 60.0 if avg_minutes else 0.0
        cursor.execute("SELECT date, SUM(pronunciation_practice_count + words_learned + sentences_learned) AS cnt FROM user_learning_progress WHERE date >= ? GROUP BY date", (since_date,))
        activity_map = {row["date"]: int(row["cnt"] or 0) for row in cursor.fetchall()}
        activity = []
        for i in range(7):
            d = (datetime.now().date() - timedelta(days=6 - i)).isoformat()
            activity.append({"date": d, "count": activity_map.get(d, 0)})
        vocab = load_json_data("vocabulary.json") or []
        dist = {}
        for item in (vocab if isinstance(vocab, list) else []):
            if not isinstance(item, dict): continue
            key = str(item.get("level") or item.get("topikLevel") or item.get("kiipLevel") or "기타")
            dist[key] = dist.get(key, 0) + 1
        difficulty = [{"label": k, "count": v} for k, v in sorted(dist.items(), key=lambda x: x[0])]
        cursor.execute("SELECT user_id, SUM(pronunciation_practice_count + words_learned + sentences_learned) AS learning_count, AVG(NULLIF(pronunciation_avg_score, 0)) AS avg_score, MAX(date) AS last_learning FROM user_learning_progress GROUP BY user_id")
        progress_rows = {str(row["user_id"]): dict(row) for row in cursor.fetchall()}
        cursor.execute("SELECT id, nickname, email FROM users WHERE role = ?", (role_learner,))
        users = cursor.fetchall(); table = []
        for user in users:
            uid = str(user["id"]); nick = user["nickname"] or uid; email = user["email"] or ""; progress = progress_rows.get(uid) or progress_rows.get(nick) or {}
            table.append({"user": f"{nick} ({email})" if email else nick, "learning_count": int(progress.get("learning_count") or 0), "avg_score": round(float(progress.get("avg_score") or 0), 1), "last_learning": progress.get("last_learning") or "-"})
        return {"success": True, "stats": {"total_users": total_users, "active_users": active_users, "avg_study_hours": round(avg_hours, 2), "avg_score": round(avg_score, 2)}, "activity": activity, "difficulty": difficulty, "table": table}
    finally:
        conn.close()

@router.get("/api/admin/users")
async def admin_users_list(request: Request, skip: int = 0, limit: int = 50, admin: dict = Depends(get_current_admin_user)):
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    normalize_role = getattr(request.app.state, "normalize_role", lambda r, a: r)
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row; cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users"); total = cursor.fetchone()[0]
        cursor.execute("SELECT id, email, nickname, is_admin, role, created_at FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, skip))
        users = [dict(row) for row in cursor.fetchall()]
        for user in users: user["role"] = normalize_role(user.get("role"), user.get("is_admin"))
        logger.info(f"[ADMIN_USERS] {admin['email']} retrieved {len(users)} users")
        return {"success": True, "users": users, "total": total, "skip": skip, "limit": limit}
    finally:
        conn.close()

@router.get("/api/admin/words")
async def admin_words_list(request: Request, q: str = "", skip: int = 0, limit: int = 200, admin: dict = Depends(get_current_admin_user)):
    skip = max(0, int(skip or 0)); limit = max(1, min(int(limit or 200), 500)); q = (q or "").strip().lower()
    vocab = load_json_data("vocabulary.json") or []
    if not isinstance(vocab, list): vocab = []
    def matches(item: dict) -> bool:
        if not q: return True
        hay = " ".join([str(item.get(k, "")) for k in ["word", "meaningKo", "meaning", "meaningEn", "roman", "category", "topic", "topikLevel"]]).lower()
        return q in hay
    filtered = [item for item in vocab if isinstance(item, dict) and matches(item)]
    total = len(filtered)
    categories = {str(item.get("category") or "") for item in filtered if item.get("category")}
    levels = {str(item.get("level") or item.get("topikLevel") or "") for item in filtered if (item.get("level") or item.get("topikLevel"))}
    sliced = filtered[skip : skip + limit]
    words = [{"id": item.get("id") or "", "word": item.get("word") or "", "meaning": item.get("meaningKo") or item.get("meaning") or item.get("meaningEn") or "", "category": item.get("category") or item.get("topic") or "", "level": item.get("level") or item.get("topikLevel") or ""} for item in sliced]
    return {"success": True, "stats": {"total": total, "categories": len([c for c in categories if c]), "levels": len([l for l in levels if l])}, "words": words, "skip": skip, "limit": limit}

@router.post("/api/admin/users/{user_id}/credits")
async def admin_set_user_credits(request: Request, user_id: int, admin: dict = Depends(get_current_admin_user)):
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    payload = await request.json(); action = payload.get("action"); credits_used = payload.get("credits_used")
    conn = sqlite3.connect(db_path)
    try:
        if action == "reset": conn.execute("UPDATE users SET credits_used = 0, credits_reset_date = '' WHERE id = ?", (user_id,))
        elif credits_used is not None: conn.execute("UPDATE users SET credits_used = ?, credits_reset_date = ? WHERE id = ?", (max(0, int(credits_used)), datetime.now().strftime("%Y-%m-%d"), user_id))
        else: return JSONResponse(status_code=400, content={"success": False, "message": "action=reset 또는 credits_used 값이 필요합니다."})
        conn.commit()
    finally: conn.close()
    if hasattr(request.app.state, "clear_user_cache"): request.app.state.clear_user_cache()
    info = get_user_credits(db_path, user_id)
    logger.info(f"[ADMIN_CREDITS] user_id={user_id} action={action or 'set'} credits_used={credits_used}")
    return JSONResponse({"success": True, **info})

@router.post("/api/admin/users/{user_id}/toggle-admin")
async def admin_toggle_user_admin(request: Request, user_id: int, admin: dict = Depends(get_current_admin_user)):
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    role_system_admin = getattr(request.app.state, "role_system_admin", "system_admin")
    role_learner = getattr(request.app.state, "role_learner", "learner")
    payload = await request.json()
    if admin["id"] == user_id: raise HTTPException(status_code=400, detail="자신의 관리자 권한은 수정할 수 없습니다.")
    is_admin = payload.get("is_admin", False); new_role = role_system_admin if is_admin else role_learner
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_admin = ?, role = ? WHERE id = ?", (int(bool(is_admin)), new_role, user_id))
        conn.commit()
    finally: conn.close()
    if hasattr(request.app.state, "clear_user_cache"): request.app.state.clear_user_cache()
    logger.info(f"[ADMIN_TOGGLE] {admin['email']} set is_admin={is_admin} for user {user_id}")
    return {"success": True, "user": {"id": user_id, "is_admin": bool(is_admin), "role": new_role}}

@router.post("/api/admin/users/{user_id}/role")
async def admin_update_user_role(request: Request, user_id: int, admin: dict = Depends(get_current_admin_user)):
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    role_system_admin = getattr(request.app.state, "role_system_admin", "system_admin")
    role_choices = getattr(request.app.state, "role_choices", {role_system_admin})
    payload = await request.json()
    if admin["id"] == user_id: raise HTTPException(status_code=400, detail="자신의 역할은 변경할 수 없습니다.")
    role = (payload.get("role") or "").strip().lower()
    if role not in role_choices: raise HTTPException(status_code=400, detail="유효하지 않은 역할입니다.")
    is_admin = role == role_system_admin
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET role = ?, is_admin = ? WHERE id = ?", (role, int(is_admin), user_id))
        conn.commit()
    finally: conn.close()
    if hasattr(request.app.state, "clear_user_cache"): request.app.state.clear_user_cache()
    logger.info(f"[ADMIN_ROLE] {admin['email']} set role={role} for user {user_id}")
    return {"success": True, "user": {"id": user_id, "role": role, "is_admin": bool(is_admin)}}

@router.post("/api/admin/users/{user_id}/reset-password")
async def admin_reset_user_password(request: Request, user_id: int, admin: dict = Depends(get_current_admin_user)):
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    payload = await request.json()
    if admin["id"] == user_id: raise HTTPException(status_code=400, detail="자신의 비밀번호는 이 방법으로 초기화할 수 없습니다.")
    new_password = payload.get("new_password", "")
    if not new_password or len(new_password) < 8: raise HTTPException(status_code=400, detail="새 비밀번호는 8자 이상이어야 합니다.")
    new_hash = hash_password(new_password)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
        conn.commit()
    finally: conn.close()
    if hasattr(request.app.state, "clear_user_cache"): request.app.state.clear_user_cache()
    logger.info(f"[ADMIN_RESET_PWD] {admin['email']} reset password for user {user_id}")
    return {"success": True, "message": "비밀번호가 초기화되었습니다."}

@router.get("/api/admin/users/{user_id}")
async def admin_get_user_detail(request: Request, user_id: int, admin: dict = Depends(get_current_admin_user)):
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    role_choices = getattr(request.app.state, "role_choices", set())
    from backend.utils import get_user_by_id
    user = get_user_by_id(db_path, user_id, role_choices)
    if not user: raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    user.pop("password_hash", None)
    logger.info(f"[ADMIN_VIEW_USER] {admin['email']} viewed user {user['email']}")
    return {"success": True, "user": user}

@router.get("/api/admin/settings")
async def admin_get_settings(request: Request, admin: dict = Depends(get_current_admin_user)):
    settings = {
        "model_backend": os.getenv("MODEL_BACKEND"),
        "model_backend_fallback": os.getenv("MODEL_BACKEND_FALLBACK", ""),
        "ollama_url": os.getenv("OLLAMA_URL"),
        "ollama_model": os.getenv("OLLAMA_MODEL"),
        "mztts_url": os.getenv("MZTTS_API_URL"),
        "romanize_mode": os.getenv("ROMANIZE_MODE"),
    }
    logger.info(f"[ADMIN_SETTINGS] {admin['email']} retrieved settings")
    return {"success": True, "settings": settings}

@router.get("/api/admin/rag/settings")
async def admin_rag_get_settings(request: Request, admin: dict = Depends(get_current_admin_user)):
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    conn = sqlite3.connect(db_path)
    try:
        ensure_rag_tables(conn); settings = rag_get_settings(conn); conn.row_factory = sqlite3.Row; cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS n FROM rag_documents"); docs = int(cursor.fetchone()["n"])
        cursor.execute("SELECT COUNT(*) AS n FROM rag_chunks"); chunks = int(cursor.fetchone()["n"])
        logger.info("[ADMIN_RAG] %s viewed settings", admin.get("email"))
        return {"success": True, "settings": settings, "stats": {"documents": docs, "chunks": chunks}}
    finally: conn.close()

@router.post("/api/admin/rag/settings")
async def admin_rag_update_settings(request: Request, admin: dict = Depends(get_current_admin_user)):
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    payload = await request.json(); enabled = 1 if bool(payload.get("enabled")) else 0; top_k = int(payload.get("top_k") or 5); top_k = max(1, min(top_k, 10))
    conn = sqlite3.connect(db_path)
    try:
        ensure_rag_tables(conn); cursor = conn.cursor()
        cursor.execute("UPDATE rag_settings SET enabled = ?, top_k = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1", (enabled, top_k))
        conn.commit()
        logger.info("[ADMIN_RAG] %s updated settings enabled=%s top_k=%s", admin.get("email"), enabled, top_k)
        return {"success": True}
    finally: conn.close()

@router.get("/api/admin/rag/documents")
async def admin_rag_list_documents(request: Request, admin: dict = Depends(get_current_admin_user)):
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    conn = sqlite3.connect(db_path)
    try:
        ensure_rag_tables(conn); conn.row_factory = sqlite3.Row; cursor = conn.cursor()
        cursor.execute("SELECT id, title, source, mime_type, created_at FROM rag_documents ORDER BY created_at DESC LIMIT 200")
        docs = [dict(r) for r in cursor.fetchall()]; return {"success": True, "documents": docs}
    finally: conn.close()

@router.delete("/api/admin/rag/documents/{doc_id}")
async def admin_rag_delete_document(request: Request, doc_id: int, admin: dict = Depends(get_current_admin_user)):
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    conn = sqlite3.connect(db_path)
    try:
        ensure_rag_tables(conn); cursor = conn.cursor()
        cursor.execute("SELECT id FROM rag_documents WHERE id = ?", (doc_id,))
        if not cursor.fetchone(): raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
        cursor.execute("SELECT id FROM rag_chunks WHERE document_id = ?", (doc_id,))
        chunk_ids = [row[0] for row in cursor.fetchall()]
        if chunk_ids:
            placeholders = ",".join(["?"] * len(chunk_ids))
            cursor.execute(f"DELETE FROM rag_chunks_fts WHERE chunk_id IN ({placeholders})", chunk_ids)
        cursor.execute("DELETE FROM rag_chunks WHERE document_id = ?", (doc_id,))
        cursor.execute("DELETE FROM rag_documents WHERE id = ?", (doc_id,))
        conn.commit()
        logger.info("[ADMIN_RAG] %s deleted document id=%s", admin.get("email"), doc_id)
        return {"success": True}
    finally: conn.close()

@router.post("/api/admin/rag/documents")
async def admin_rag_upload_document(request: Request, file: UploadFile = File(...), title: str = Form(""), source: str = Form(""), admin: dict = Depends(get_current_admin_user)):
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    raw = await file.read()
    if not raw: raise HTTPException(status_code=400, detail="빈 파일입니다.")
    mime_type = file.content_type or "text/plain"; text = raw.decode("utf-8", errors="ignore")
    title = (title or "").strip() or (file.filename or "문서"); source = (source or "").strip() or (file.filename or "upload")
    chunks = rag_chunk_text(text, max_chars=700)
    if not chunks: raise HTTPException(status_code=400, detail="텍스트를 추출할 수 없습니다.")
    conn = sqlite3.connect(db_path)
    try:
        ensure_rag_tables(conn); cursor = conn.cursor()
        cursor.execute("INSERT INTO rag_documents (title, source, mime_type) VALUES (?, ?, ?)", (title, source, mime_type)); doc_id = cursor.lastrowid
        for idx, chunk in enumerate(chunks):
            cursor.execute("INSERT INTO rag_chunks (document_id, chunk_index, content) VALUES (?, ?, ?)", (doc_id, idx, chunk)); chunk_id = cursor.lastrowid
            cursor.execute("INSERT INTO rag_chunks_fts (content, chunk_id) VALUES (?, ?)", (chunk, chunk_id))
        conn.commit()
        logger.info("[ADMIN_RAG] %s uploaded document id=%s chunks=%s", admin.get("email"), doc_id, len(chunks))
        return {"success": True, "document_id": doc_id, "chunks": len(chunks)}
    finally: conn.close()
