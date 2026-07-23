import os
import json
import logging
import sqlite3
from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException, Depends, Form
from fastapi.responses import JSONResponse

from backend.routes.deps import get_current_user, load_json_data
from backend.database import ensure_media_tables
from backend.services.onui_tube_catalog import (
    annotate_tube_videos,
    build_tube_catalog_summary,
    strip_computed_tube_fields,
    validate_tube_video_catalog,
)

router = APIRouter()
logger = logging.getLogger("uvicorn.error")


def _ensure_saved_vocab_table(conn: sqlite3.Connection):
    ensure_media_tables(conn)
    conn.commit()

@router.get("/api/tube/videos")
async def get_tube_videos(user: dict = Depends(get_current_user)):
    videos = load_json_data("onui-tube.json") or []
    transcripts = load_json_data("onui-tube-transcripts.json") or {}
    videos = annotate_tube_videos(videos, transcripts)
    return {"success": True, "videos": videos, "summary": build_tube_catalog_summary(videos)}

@router.post("/api/tube/videos")
async def update_tube_videos(request: Request, user: dict = Depends(get_current_user)):
    # Admin check might be needed here, but for now matching previous logic
    try:
        data = await request.json()
        allow_unready = bool(data.get("allow_unready")) if isinstance(data, dict) else False
        videos = data.get("videos") if isinstance(data, dict) and "videos" in data else data

        transcripts = load_json_data("onui-tube-transcripts.json") or {}
        validation = validate_tube_video_catalog(
            videos,
            transcripts,
            allow_unready=allow_unready,
        )
        if not validation["valid"]:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "errors": validation["errors"],
                    "summary": validation["summary"],
                },
            )

        clean_videos = strip_computed_tube_fields(validation["videos"])
        with open("data/onui-tube.json", "w", encoding="utf-8") as f:
            json.dump(clean_videos, f, ensure_ascii=False, indent=2)
        return {"success": True, "summary": validation["summary"]}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.get("/api/tube/transcripts/{video_id}")
async def get_tube_transcript(video_id: str, user: dict = Depends(get_current_user)):
    transcripts = load_json_data("onui-tube-transcripts.json") or {}
    transcript = transcripts.get(video_id)
    if not transcript:
        return JSONResponse(status_code=404, content={"error": "Transcript not found"})
    return {"success": True, "transcripts": transcript}

@router.get("/api/tube/vocab/export")
async def export_tube_vocab(user: dict = Depends(get_current_user)):
    vocab = load_json_data("vocabulary.json") or []
    return {"success": True, "vocabulary": vocab}

@router.get("/api/tube/vocab")
async def get_user_tube_vocab(request: Request, user: dict = Depends(get_current_user)):
    db_path = request.app.state.db_path
    conn = sqlite3.connect(db_path)
    try:
        _ensure_saved_vocab_table(conn)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT label, pos, meaning, source, saved_at
            FROM user_saved_vocab
            WHERE user_id = ?
            ORDER BY saved_at DESC, id DESC
            """,
            (user["id"],),
        )
        vocab = [
            {
                "label": row["label"],
                "pos": row["pos"] or "",
                "meaning": row["meaning"] or "",
                "mean": row["meaning"] or "",
                "source": row["source"] or "tube",
                "savedAt": row["saved_at"],
            }
            for row in cursor.fetchall()
        ]
        return {"success": True, "vocab": vocab}
    finally:
        conn.close()

@router.post("/api/tube/vocab")
async def update_user_tube_vocab(request: Request, user: dict = Depends(get_current_user)):
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    conn = sqlite3.connect(db_path)
    try:
        _ensure_saved_vocab_table(conn)
        cursor = conn.cursor()
        content_type = (request.headers.get("content-type") or "").lower()
        if "application/json" in content_type:
            data = await request.json()
            vocab = data.get("vocabulary", [])
            if not isinstance(vocab, list):
                raise HTTPException(status_code=400, detail="Invalid vocabulary payload")

            cursor.execute("DELETE FROM user_saved_vocab WHERE user_id = ?", (user["id"],))
            for item in vocab:
                if isinstance(item, str):
                    label = item.strip()
                    pos = ""
                    meaning = ""
                    source = "tube"
                elif isinstance(item, dict):
                    label = str(item.get("label", "") or "").strip()
                    pos = str(item.get("pos", "") or "").strip()
                    meaning = str(item.get("meaning") or item.get("mean") or "").strip()
                    source = str(item.get("source", "tube") or "tube").strip()
                else:
                    continue

                if not label:
                    continue

                cursor.execute(
                    """
                    INSERT INTO user_saved_vocab (user_id, label, pos, meaning, source)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user["id"], label, pos, meaning, source),
                )
        else:
            form = await request.form()
            label = str(form.get("label", "") or "").strip()
            if not label:
                raise HTTPException(status_code=400, detail="label is required")

            pos = str(form.get("pos", "") or "").strip()
            meaning = str(form.get("meaning", "") or "").strip()
            source = str(form.get("source", "tube") or "tube").strip()

            cursor.execute(
                """
                INSERT INTO user_saved_vocab (user_id, label, pos, meaning, source)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, label) DO UPDATE SET
                    pos = excluded.pos,
                    meaning = excluded.meaning,
                    source = excluded.source,
                    saved_at = CURRENT_TIMESTAMP
                """,
                (user["id"], label, pos, meaning, source),
            )

        conn.commit()
        return {"success": True}
    finally:
        conn.close()

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

@router.get("/api/video-lessons")
async def api_video_lessons(user: dict = Depends(get_current_user)):
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
                    "mp4": None,
                    "has_mp4": False,
                    "pdf": None,
                    "has_pdf": False,
                    "html": None,
                    "has_html": False,
                }
            ext = f.suffix.lower()
            if ext == ".mp4":
                lessons[key]["mp4"] = f"/static/videos/{f.name}"
                lessons[key]["has_mp4"] = True
            elif ext == ".pdf":
                lessons[key]["pdf"] = f"/static/videos/{f.name}"
                lessons[key]["has_pdf"] = True
            elif ext == ".html":
                lessons[key]["html"] = f"/static/videos/{f.name}"
                lessons[key]["has_html"] = True

    # Group by level
    result: dict = {}
    for item in sorted(
        lessons.values(), key=lambda x: (x["level"], x["week"], x["session"])
    ):
        lvl = f"level{item['level']}"
        result.setdefault(lvl, []).append(item)

    return JSONResponse(content={"lessons": result})


def _ensure_video_progress_table(db_path: str = "data/users.db"):
    conn = sqlite3.connect(db_path)
    try:
        ensure_media_tables(conn)
        conn.commit()
    finally:
        conn.close()

@router.get("/api/video-progress/{user_id}")
async def get_video_progress(user_id: str, request: Request, user: dict = Depends(get_current_user)):
    """사용자의 전체 동영상 시청 진도를 반환합니다."""
    # 세션 검증: 본인 데이터 또는 관리자만 조회 가능
    session_role = getattr(request.app.state, "normalize_role", lambda r, a: "learner")(user.get("role"), user.get("is_admin"))
    role_system_admin = getattr(request.app.state, "role_system_admin", "system_admin")
    if str(user["id"]) != str(user_id) and session_role != role_system_admin:
        return JSONResponse(status_code=403, content={"error": "권한이 없습니다."})
    
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    try:
        _ensure_video_progress_table(db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT video_id, watched_seconds, duration_seconds, completed, last_position, updated_at "
            "FROM user_video_progress WHERE user_id = ?",
            (user_id,),
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
    video_id: str
    watched_seconds: int = 0
    duration_seconds: int = 0
    last_position: int = 0
    completed: bool = False

@router.post("/api/video-progress")
async def save_video_progress(request: Request, body: _VideoProgressBody, user: dict = Depends(get_current_user)):
    """동영상 시청 진도를 저장합니다."""
    user_id = str(user["id"])
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    try:
        _ensure_video_progress_table(db_path)
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            INSERT INTO user_video_progress
                (user_id, video_id, watched_seconds, duration_seconds, completed, last_position, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, video_id) DO UPDATE SET
                watched_seconds = MAX(excluded.watched_seconds, watched_seconds),
                duration_seconds = excluded.duration_seconds,
                completed = MAX(excluded.completed, completed),
                last_position = excluded.last_position,
                updated_at = CURRENT_TIMESTAMP
        """,
            (
                user_id,
                body.video_id,
                body.watched_seconds,
                body.duration_seconds,
                int(body.completed),
                body.last_position,
            ),
        )
        conn.commit()

        # LMS: 강의 출결 자동 연동 (실패 무시)
        try:
            _uid_int = int(user_id)
            _watched_pct = (
                round(body.watched_seconds / body.duration_seconds * 100, 1)
                if body.duration_seconds and body.duration_seconds > 0
                else 0.0
            )
            _status = "present" if (_watched_pct >= 80 or body.completed) else "absent"
            _now_str = (
                __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            )
            conn.execute(
                """
                INSERT INTO lecture_attendance
                    (user_id, video_id, week, status, watched_pct, study_seconds,
                     attended_at, term_id, created_at)
                VALUES (?,?,NULL,?,?,?,?,?,?)
                ON CONFLICT(user_id, video_id) DO UPDATE SET
                    status      = CASE WHEN excluded.watched_pct >= 80 OR excluded.status = 'present'
                                       THEN 'present'
                                       WHEN lecture_attendance.status = 'present' THEN 'present'
                                       ELSE 'absent' END,
                    watched_pct = MAX(lecture_attendance.watched_pct, excluded.watched_pct),
                    study_seconds = MAX(lecture_attendance.study_seconds, excluded.study_seconds),
                    attended_at = CASE WHEN (excluded.watched_pct >= 80 OR excluded.status = 'present')
                                         AND lecture_attendance.status != 'present'
                                       THEN excluded.attended_at
                                       ELSE lecture_attendance.attended_at END
                """,
                (
                    _uid_int,
                    body.video_id,
                    _status,
                    _watched_pct,
                    body.watched_seconds,
                    _now_str if _status == "present" else None,
                    "2026-1",
                    _now_str,
                ),
            )
            conn.commit()
        except Exception:
            pass

        conn.close()
        return JSONResponse(content={"saved": True})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
