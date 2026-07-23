"""
LMS Routes — 성적 · 출결 · 체류시간 API
Phase 1 (~3/18)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.utils import _get_state
from backend.database import ensure_lms_tables

router = APIRouter()

# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────


def _db(request: Request):
    db_path = _get_state(request, "db_path")
    if not db_path:
        raise RuntimeError("db_path not configured")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    ensure_lms_tables(conn)
    conn.commit()
    return conn


def _require_user(request: Request) -> dict:
    fn = _get_state(request, "require_authenticated_user")
    if not callable(fn):
        raise RuntimeError("Auth not configured")
    return fn(request)


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ══════════════════════════════════════════════
# 1. 문장별 성적 (sentence_scores)
# ══════════════════════════════════════════════


@router.post("/api/lms/scores/sentence")
async def save_sentence_score(request: Request):
    """
    발음 평가 결과를 sentence_scores에 저장.
    최초/최고/최근 3포인트 방식으로 UPSERT.
    """
    try:
        user = _require_user(request)
    except Exception as e:
        return JSONResponse(status_code=401, content={"error": str(e)})

    payload = await request.json()

    sentence_id = str(payload.get("sentence_id", ""))
    sentence_text = payload.get("sentence_text", "")
    level = payload.get("level", "")
    score = float(payload.get("score", 0))
    accuracy = float(payload.get("accuracy", 0))
    completeness = float(payload.get("completeness", 0))
    fluency_acc = float(payload.get("fluency_accuracy", 0))
    term_id = payload.get("term_id", "2026-1")
    device_type = payload.get("device_type", "pc")
    ui_lang = payload.get("ui_lang", "en")

    if not sentence_id:
        return JSONResponse(status_code=400, content={"error": "sentence_id required"})

    now = _utcnow()
    user_id = user["id"]

    try:
        conn = _db(request)
        cur = conn.cursor()

        # 기존 레코드 조회
        cur.execute(
            "SELECT id, score_first, score_best, attempt_count FROM sentence_scores "
            "WHERE user_id = ? AND sentence_id = ?",
            (user_id, sentence_id),
        )
        row = cur.fetchone()

        if row is None:
            # 최초 기록
            cur.execute(
                """
                INSERT INTO sentence_scores (
                    user_id, sentence_id, sentence_text, level,
                    score_first, score_best, score_latest,
                    accuracy_first, accuracy_best, accuracy_latest,
                    completeness_latest, fluency_accuracy_latest,
                    attempt_count, term_id, device_type, ui_lang,
                    last_attempted_at, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?,?,?)
                """,
                (
                    user_id,
                    sentence_id,
                    sentence_text,
                    level,
                    score,
                    score,
                    score,
                    accuracy,
                    accuracy,
                    accuracy,
                    completeness,
                    fluency_acc,
                    term_id,
                    device_type,
                    ui_lang,
                    now,
                    now,
                ),
            )
        else:
            new_best = max(row["score_best"] or 0, score)
            new_count = (row["attempt_count"] or 1) + 1
            cur.execute(
                """
                UPDATE sentence_scores SET
                    score_best = ?, score_latest = ?,
                    accuracy_best = MAX(accuracy_best, ?),
                    accuracy_latest = ?,
                    completeness_latest = ?,
                    fluency_accuracy_latest = ?,
                    attempt_count = ?,
                    last_attempted_at = ?
                WHERE user_id = ? AND sentence_id = ?
                """,
                (
                    new_best,
                    score,
                    accuracy,
                    accuracy,
                    completeness,
                    fluency_acc,
                    new_count,
                    now,
                    user_id,
                    sentence_id,
                ),
            )
        conn.commit()
        conn.close()
        return JSONResponse(content={"success": True})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/api/lms/scores/sentence/{user_id}")
async def get_sentence_scores(
    request: Request, user_id: int, level: Optional[str] = None, limit: int = 100
):
    """학생의 문장별 성적 목록 조회 (선생님/관리자 또는 본인)."""
    try:
        me = _require_user(request)
    except Exception as e:
        return JSONResponse(status_code=401, content={"error": str(e)})

    normalize_role = _get_state(request, "normalize_role")
    role_instructor = _get_state(request, "role_instructor")
    role_admin = _get_state(request, "role_system_admin")
    my_role = (
        normalize_role(me.get("role"), me.get("is_admin"))
        if callable(normalize_role)
        else "learner"
    )

    # 본인이거나 선생님/관리자만 조회 가능
    if me["id"] != user_id and my_role not in {role_instructor, role_admin}:
        return JSONResponse(status_code=403, content={"error": "권한이 없습니다"})

    try:
        conn = _db(request)
        cur = conn.cursor()
        if level:
            cur.execute(
                "SELECT * FROM sentence_scores WHERE user_id = ? AND level = ? "
                "ORDER BY last_attempted_at DESC LIMIT ?",
                (user_id, level, limit),
            )
        else:
            cur.execute(
                "SELECT * FROM sentence_scores WHERE user_id = ? "
                "ORDER BY last_attempted_at DESC LIMIT ?",
                (user_id, limit),
            )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return JSONResponse(content={"scores": rows, "count": len(rows)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/api/lms/scores/sentence/{user_id}/summary")
async def get_sentence_score_summary(request: Request, user_id: int):
    """학생 성적 요약: 레벨별 평균/최고/시도수 + 최근 10개 이력."""
    try:
        me = _require_user(request)
    except Exception as e:
        return JSONResponse(status_code=401, content={"error": str(e)})

    normalize_role = _get_state(request, "normalize_role")
    role_instructor = _get_state(request, "role_instructor")
    role_admin = _get_state(request, "role_system_admin")
    my_role = (
        normalize_role(me.get("role"), me.get("is_admin"))
        if callable(normalize_role)
        else "learner"
    )

    if me["id"] != user_id and my_role not in {role_instructor, role_admin}:
        return JSONResponse(status_code=403, content={"error": "권한이 없습니다"})

    try:
        conn = _db(request)
        cur = conn.cursor()

        # 레벨별 집계
        cur.execute(
            """
            SELECT level,
                   COUNT(*) AS sentences_tried,
                   ROUND(AVG(score_latest), 1) AS avg_latest,
                   ROUND(AVG(score_best), 1)   AS avg_best,
                   ROUND(MAX(score_best), 1)    AS top_score,
                   SUM(attempt_count)           AS total_attempts
            FROM sentence_scores
            WHERE user_id = ?
            GROUP BY level
            ORDER BY level
            """,
            (user_id,),
        )
        by_level = [dict(r) for r in cur.fetchall()]

        # 전체 요약
        cur.execute(
            """
            SELECT COUNT(*) AS total_sentences,
                   ROUND(AVG(score_latest), 1) AS overall_avg,
                   ROUND(MAX(score_best), 1)    AS overall_best,
                   SUM(attempt_count)           AS overall_attempts
            FROM sentence_scores
            WHERE user_id = ?
            """,
            (user_id,),
        )
        overall = dict(cur.fetchone() or {})

        # 최근 10개 성적 이력
        cur.execute(
            """
            SELECT sentence_id, sentence_text, level,
                   score_first, score_best, score_latest,
                   attempt_count, last_attempted_at
            FROM sentence_scores
            WHERE user_id = ?
            ORDER BY last_attempted_at DESC
            LIMIT 10
            """,
            (user_id,),
        )
        recent = [dict(r) for r in cur.fetchall()]

        conn.close()
        return JSONResponse(
            content={
                "user_id": user_id,
                "overall": overall,
                "by_level": by_level,
                "recent": recent,
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ══════════════════════════════════════════════
# 2. 강의 출결 (lecture_attendance)
# ══════════════════════════════════════════════


@router.post("/api/lms/attendance/video")
async def record_video_attendance(request: Request):
    """
    강의 시청률을 기반으로 출결 처리.
    watched_pct >= 80 이면 status = 'present'.
    세션에서 user_id를 가져옴 (body의 user_id는 무시).
    """
    # 세션 인증 필수
    try:
        session_user = _require_user(request)
    except Exception as e:
        return JSONResponse(status_code=401, content={"error": str(e)})

    payload = await request.json()

    video_id = payload.get("video_id", "")
    watched_pct = float(payload.get("watched_pct", 0))
    study_secs = int(payload.get("study_seconds", 0))
    week = payload.get("week")
    term_id = payload.get("term_id", "2026-1")

    # 세션에서 user_id 추출
    try:
        user_id = int(session_user.get("id"))
    except (TypeError, ValueError):
        return JSONResponse(content={"success": False, "reason": "invalid_user"})

    if not video_id:
        return JSONResponse(status_code=400, content={"error": "video_id required"})

    status = "present" if watched_pct >= 80.0 else "absent"
    now = _utcnow()

    try:
        conn = _db(request)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO lecture_attendance
                (user_id, video_id, week, status, watched_pct, study_seconds,
                 attended_at, term_id, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id, video_id) DO UPDATE SET
                status        = CASE WHEN excluded.watched_pct >= 80 THEN 'present'
                                     WHEN lecture_attendance.status = 'present' THEN 'present'
                                     ELSE 'absent' END,
                watched_pct   = MAX(lecture_attendance.watched_pct, excluded.watched_pct),
                study_seconds = MAX(lecture_attendance.study_seconds, excluded.study_seconds),
                attended_at   = CASE WHEN excluded.watched_pct >= 80
                                       AND lecture_attendance.status != 'present'
                                     THEN excluded.attended_at
                                     ELSE lecture_attendance.attended_at END
            """,
            (
                user_id,
                video_id,
                week,
                status,
                watched_pct,
                study_secs,
                now if status == "present" else None,
                term_id,
                now,
            ),
        )
        conn.commit()
        conn.close()
        return JSONResponse(
            content={"success": True, "status": status, "watched_pct": watched_pct}
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/api/lms/attendance/summary/{user_id}")
async def get_attendance_summary(
    request: Request, user_id: int, term_id: str = "2026-1"
):
    """학생의 출석률 요약 (주차별 + 전체)."""
    try:
        me = _require_user(request)
    except Exception as e:
        return JSONResponse(status_code=401, content={"error": str(e)})

    normalize_role = _get_state(request, "normalize_role")
    role_instructor = _get_state(request, "role_instructor")
    role_admin = _get_state(request, "role_system_admin")
    my_role = (
        normalize_role(me.get("role"), me.get("is_admin"))
        if callable(normalize_role)
        else "learner"
    )

    if me["id"] != user_id and my_role not in {role_instructor, role_admin}:
        return JSONResponse(status_code=403, content={"error": "권한이 없습니다"})

    try:
        conn = _db(request)
        cur = conn.cursor()

        # 전체 출석률
        cur.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status = 'present' THEN 1 ELSE 0 END) AS present_count
            FROM lecture_attendance
            WHERE user_id = ? AND term_id = ?
            """,
            (user_id, term_id),
        )
        row = dict(cur.fetchone() or {})
        total = row.get("total") or 0
        present = row.get("present_count") or 0
        rate = round(present / total * 100, 1) if total > 0 else 0.0

        # 주차별 출석 현황
        cur.execute(
            """
            SELECT week, video_id, status, watched_pct, study_seconds, attended_at
            FROM lecture_attendance
            WHERE user_id = ? AND term_id = ?
            ORDER BY week, video_id
            """,
            (user_id, term_id),
        )
        by_week_raw = [dict(r) for r in cur.fetchall()]

        conn.close()
        return JSONResponse(
            content={
                "user_id": user_id,
                "term_id": term_id,
                "total_lectures": total,
                "present_count": present,
                "attendance_rate": rate,
                "by_lecture": by_week_raw,
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/api/lms/attendance/manual")
async def manual_attendance_update(request: Request):
    """선생님/관리자가 출결을 수동 수정. 수정 이력 로그 기록."""
    try:
        me = _require_user(request)
    except Exception as e:
        return JSONResponse(status_code=401, content={"error": str(e)})

    normalize_role = _get_state(request, "normalize_role")
    role_instructor = _get_state(request, "role_instructor")
    role_admin = _get_state(request, "role_system_admin")
    my_role = (
        normalize_role(me.get("role"), me.get("is_admin"))
        if callable(normalize_role)
        else "learner"
    )

    if my_role not in {role_instructor, role_admin}:
        return JSONResponse(
            status_code=403, content={"error": "선생님/관리자만 수정 가능합니다"}
        )

    payload = await request.json()
    target_user_id = payload.get("user_id")
    video_id = payload.get("video_id", "")
    new_status = payload.get("status", "")  # 'present' or 'absent'

    if not target_user_id or not video_id or new_status not in ("present", "absent"):
        return JSONResponse(
            status_code=400,
            content={"error": "user_id, video_id, status(present/absent) required"},
        )

    now = _utcnow()
    logger = _get_state(request, "logger")

    try:
        conn = _db(request)
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE lecture_attendance
            SET status = ?, modified_by = ?, modified_at = ?
            WHERE user_id = ? AND video_id = ?
            """,
            (new_status, me["id"], now, target_user_id, video_id),
        )
        affected = cur.rowcount
        conn.commit()
        conn.close()

        if logger:
            logger.info(
                "[LMS_ATTENDANCE_MANUAL] modifier=%s target_user=%s video_id=%s new_status=%s",
                me.get("email"),
                target_user_id,
                video_id,
                new_status,
            )

        return JSONResponse(content={"success": True, "affected": affected})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ══════════════════════════════════════════════
# 3. 체류 시간 (study_sessions)
# ══════════════════════════════════════════════


@router.post("/api/lms/study-session")
async def save_study_session(request: Request):
    """
    페이지 이탈 시 유효 학습 시간(초)을 저장.
    60초 미만은 서버에서 무시.
    세션에서 user_id를 가져옴 (body의 user_id는 무시).
    """
    # 세션 인증 필수
    try:
        session_user = _require_user(request)
    except Exception as e:
        return JSONResponse(status_code=401, content={"error": str(e)})

    payload = await request.json()

    page = payload.get("page", "")
    page_type = payload.get(
        "page_type", "other"
    )  # lecture / pronunciation / quiz / other
    duration = int(payload.get("duration_seconds", 0))
    term_id = payload.get("term_id", "2026-1")
    device_type = payload.get("device_type", "pc")
    ui_lang = payload.get("ui_lang", "en")

    # 세션에서 user_id 추출
    try:
        user_id = int(session_user.get("id"))
    except (TypeError, ValueError):
        return JSONResponse(content={"success": False, "reason": "invalid_user"})

    # 60초 미만 미집계
    if duration < 60:
        return JSONResponse(
            content={"success": False, "reason": "too_short", "duration": duration}
        )

    try:
        conn = _db(request)
        conn.execute(
            """
            INSERT INTO study_sessions
                (user_id, page, page_type, duration_seconds, term_id, device_type, ui_lang, created_at)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                user_id,
                page,
                page_type,
                duration,
                term_id,
                device_type,
                ui_lang,
                _utcnow(),
            ),
        )
        conn.commit()
        conn.close()

        # 통합 학습 진도(total_learning_time) 업데이트 (60초 이상일 때 분 단위로 누적)
        learning_service = _get_state(request, "learning_service")
        if learning_service and duration >= 60:
            learning_service.update_total_learning_time(str(user_id), duration // 60)

        return JSONResponse(content={"success": True, "duration_seconds": duration})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/api/lms/study-session/summary/{user_id}")
async def get_study_session_summary(
    request: Request, user_id: int, term_id: str = "2026-1"
):
    """학생의 총 학습 시간 + 페이지 유형별 분류 요약."""
    try:
        me = _require_user(request)
    except Exception as e:
        return JSONResponse(status_code=401, content={"error": str(e)})

    normalize_role = _get_state(request, "normalize_role")
    role_instructor = _get_state(request, "role_instructor")
    role_admin = _get_state(request, "role_system_admin")
    my_role = (
        normalize_role(me.get("role"), me.get("is_admin"))
        if callable(normalize_role)
        else "learner"
    )

    if me["id"] != user_id and my_role not in {role_instructor, role_admin}:
        return JSONResponse(status_code=403, content={"error": "권한이 없습니다"})

    try:
        conn = _db(request)
        cur = conn.cursor()

        # 총 학습 시간
        cur.execute(
            "SELECT SUM(duration_seconds) AS total_seconds FROM study_sessions "
            "WHERE user_id = ? AND term_id = ?",
            (user_id, term_id),
        )
        total_secs = cur.fetchone()["total_seconds"] or 0

        # 페이지 유형별 시간
        cur.execute(
            """
            SELECT page_type,
                   SUM(duration_seconds) AS seconds,
                   COUNT(*) AS sessions
            FROM study_sessions
            WHERE user_id = ? AND term_id = ?
            GROUP BY page_type
            ORDER BY seconds DESC
            """,
            (user_id, term_id),
        )
        by_type = [dict(r) for r in cur.fetchall()]

        # 최근 7일 일별 학습 시간
        cur.execute(
            """
            SELECT DATE(created_at) AS day,
                   SUM(duration_seconds) AS seconds
            FROM study_sessions
            WHERE user_id = ? AND term_id = ?
                AND created_at >= DATE('now', '-7 days')
            GROUP BY day
            ORDER BY day
            """,
            (user_id, term_id),
        )
        daily = [dict(r) for r in cur.fetchall()]

        conn.close()
        return JSONResponse(
            content={
                "user_id": user_id,
                "term_id": term_id,
                "total_seconds": total_secs,
                "total_minutes": round(total_secs / 60, 1),
                "by_page_type": by_type,
                "daily_last_7days": daily,
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ══════════════════════════════════════════════
# 4. 반 전체 통계 (선생님/관리자용)
# ══════════════════════════════════════════════


@router.get("/api/lms/stats/class")
async def get_class_stats(request: Request, term_id: str = "2026-1"):
    """반 전체 성적/출석 통계 요약 (선생님/관리자 전용)."""
    try:
        me = _require_user(request)
    except Exception as e:
        return JSONResponse(status_code=401, content={"error": str(e)})

    normalize_role = _get_state(request, "normalize_role")
    role_instructor = _get_state(request, "role_instructor")
    role_admin = _get_state(request, "role_system_admin")
    my_role = (
        normalize_role(me.get("role"), me.get("is_admin"))
        if callable(normalize_role)
        else "learner"
    )

    if my_role not in {role_instructor, role_admin}:
        return JSONResponse(
            status_code=403, content={"error": "선생님/관리자만 접근 가능합니다"}
        )

    try:
        conn = _db(request)
        cur = conn.cursor()

        # 학생별 평균 성적
        cur.execute(
            """
            SELECT ss.user_id,
                   u.nickname,
                   ROUND(AVG(ss.score_latest), 1) AS avg_score,
                   ROUND(MAX(ss.score_best), 1)   AS best_score,
                   COUNT(*) AS sentences_tried,
                   SUM(ss.attempt_count) AS total_attempts
            FROM sentence_scores ss
            JOIN users u ON u.id = ss.user_id
            WHERE ss.term_id = ?
            GROUP BY ss.user_id
            ORDER BY avg_score DESC
            """,
            (term_id,),
        )
        score_ranking = [dict(r) for r in cur.fetchall()]

        # 학생별 출석률
        cur.execute(
            """
            SELECT la.user_id,
                   u.nickname,
                   COUNT(*) AS total,
                   SUM(CASE WHEN la.status = 'present' THEN 1 ELSE 0 END) AS present_count,
                   ROUND(
                       100.0 * SUM(CASE WHEN la.status = 'present' THEN 1 ELSE 0 END) / COUNT(*), 1
                   ) AS attendance_rate
            FROM lecture_attendance la
            JOIN users u ON u.id = la.user_id
            WHERE la.term_id = ?
            GROUP BY la.user_id
            ORDER BY attendance_rate DESC
            """,
            (term_id,),
        )
        attendance_list = [dict(r) for r in cur.fetchall()]

        # 반 전체 평균
        cur.execute(
            "SELECT ROUND(AVG(score_latest), 1) AS class_avg_score FROM sentence_scores WHERE term_id = ?",
            (term_id,),
        )
        class_avg = dict(cur.fetchone() or {})

        # 학습 세션 요약 (학생별 총 학습 시간)
        cur.execute(
            """
            SELECT user_id, ROUND(SUM(duration_seconds)/60.0, 1) AS total_minutes
            FROM study_sessions
            WHERE term_id = ?
            GROUP BY user_id
            """,
            (term_id,),
        )
        study_sessions = [dict(r) for r in cur.fetchall()]

        # 전체 학생 수 (role='learner' 기준)
        cur.execute("SELECT COUNT(*) FROM users WHERE role = 'learner'")
        total_students = cur.fetchone()[0]

        conn.close()
        return JSONResponse(
            content={
                "term_id": term_id,
                "class_avg_score": class_avg.get("class_avg_score"),
                "score_ranking": score_ranking,
                "attendance": attendance_list,
                "study_sessions": study_sessions,
                "total_students": total_students,
            }
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
