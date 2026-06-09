from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from backend.routes.deps import check_and_consume_credits, get_current_admin_user, get_current_user, parse_model_output
from backend.services.ai_learning_service import (
    SPEAKING_MISSIONS,
    build_admin_insights,
    build_curriculum,
    build_lesson_package,
    build_weakness_map,
    collect_user_activity,
    complete_routine_step,
    ensure_ai_schema,
    evaluate_mission,
    get_or_create_today_recommendation,
    is_feature_enabled,
    json_dumps,
    json_loads,
    list_feature_settings,
    normalize_learning_report,
    set_feature_settings,
)

router = APIRouter()
logger = logging.getLogger("uvicorn.error")


def _conn(request: Request) -> sqlite3.Connection:
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_ai_schema(conn)
    return conn


@contextmanager
def _managed_conn(request: Request):
    conn = _conn(request)
    try:
        yield conn
    finally:
        conn.close()


def _disabled(feature_key: str):
    return JSONResponse(status_code=403, content={"success": False, "disabled": True, "feature": feature_key})


def _credit(request: Request, user_id: int, cost_key: str) -> dict[str, Any]:
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    credit_costs = getattr(request.app.state, "credit_costs", {}) or {}
    daily_credits = int(getattr(request.app.state, "daily_credits", 100) or 100)
    return check_and_consume_credits(db_path, user_id, int(credit_costs.get(cost_key, 1)), daily_credits)


def _call_text_model(request: Request, prompt: str) -> str | None:
    backend = getattr(request.app.state, "model_backend", "gemini")
    try:
        if backend == "gemini" and getattr(request.app.state, "gemini_client", None):
            resp = request.app.state.gemini_client.models.generate_content(
                model=request.app.state.gemini_model,
                contents=prompt,
            )
            return getattr(resp, "text", "") or ""
        if backend == "openai" and getattr(request.app.state, "openai_client", None):
            resp = request.app.state.openai_client.chat.completions.create(
                model=request.app.state.openai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
            )
            return resp.choices[0].message.content or ""
    except Exception as e:
        logger.warning("AI text generation failed: %s", e)
    return None


@router.get("/api/coach/today")
async def get_today_coach(request: Request, user: dict = Depends(get_current_user)):
    with _managed_conn(request) as conn:
        if not is_feature_enabled(conn, "ai_coach"):
            return _disabled("ai_coach")
        rec = get_or_create_today_recommendation(conn, int(user["id"]))
        return {"success": True, **rec, "transparency_note": "AI/자동 추천은 학습 참고용입니다."}


@router.post("/api/coach/complete-step")
async def complete_today_step(request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    step_id = str(body.get("step_id") or "").strip()
    if not step_id:
        raise HTTPException(status_code=400, detail="step_id is required")
    with _managed_conn(request) as conn:
        if not is_feature_enabled(conn, "ai_coach"):
            return _disabled("ai_coach")
        rec = complete_routine_step(conn, int(user["id"]), step_id)
        return {"success": True, **rec}


@router.get("/api/coach/weakness-map")
async def get_weakness_map(request: Request, user: dict = Depends(get_current_user)):
    with _managed_conn(request) as conn:
        if not is_feature_enabled(conn, "ai_coach"):
            return _disabled("ai_coach")
        activity = collect_user_activity(conn, int(user["id"]))
        weakness = build_weakness_map(activity)
        return {"success": True, "activity": activity, "weakness_map": weakness}


@router.get("/api/coach/curriculum")
async def get_curriculum(request: Request, user: dict = Depends(get_current_user)):
    with _managed_conn(request) as conn:
        if not is_feature_enabled(conn, "ai_coach"):
            return _disabled("ai_coach")
        activity = collect_user_activity(conn, int(user["id"]))
        weakness = build_weakness_map(activity)
        return {"success": True, "curriculum": build_curriculum(activity, weakness), "weakness_map": weakness}


@router.post("/api/ai-feedback/session-report")
async def create_session_report(request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    source_type = str(body.get("source_type") or "practice").strip()
    source_id = str(body.get("source_id") or "").strip()
    input_text = str(body.get("input_text") or body.get("text") or "").strip()
    metrics = body.get("metrics") if isinstance(body.get("metrics"), dict) else {}
    use_ai = bool(body.get("use_ai", True))

    with _managed_conn(request) as conn:
        if not is_feature_enabled(conn, "ai_feedback_reports"):
            return _disabled("ai_feedback_reports")
        report = normalize_learning_report(source_type, input_text, metrics)
        ai_used = False
        if use_ai:
            credit = _credit(request, int(user["id"]), "chat")
            if not credit.get("ok"):
                return JSONResponse(status_code=429, content={"success": False, "message": "Credits exhausted", "remaining": credit.get("remaining", 0)})
            prompt = (
                "한국어 학습자의 활동 리포트를 JSON으로 작성하세요. "
                "필드는 strengths, corrections, better_expressions, next_practice, level_estimate 입니다.\n"
                f"활동: {source_type}\n문장/대화: {input_text}\n지표: {json.dumps(metrics, ensure_ascii=False)}"
            )
            out = _call_text_model(request, prompt)
            parsed = parse_model_output(out or "") if out else None
            if isinstance(parsed, dict):
                report = normalize_learning_report(source_type, input_text, {**metrics, **parsed})
                ai_used = True
        cursor = conn.execute(
            """
            INSERT INTO ai_learning_reports (user_id, source_type, source_id, input_text, report_json, ai_used)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (int(user["id"]), source_type, source_id, input_text, json_dumps(report), 1 if ai_used else 0),
        )
        conn.commit()
        return {"success": True, "id": cursor.lastrowid, "report": report, "ai_used": ai_used}


@router.get("/api/ai-feedback/session-report/recent")
async def recent_session_reports(request: Request, limit: int = 5, user: dict = Depends(get_current_user)):
    limit = max(1, min(int(limit or 5), 20))
    with _managed_conn(request) as conn:
        if not is_feature_enabled(conn, "ai_feedback_reports"):
            return _disabled("ai_feedback_reports")
        rows = conn.execute(
            """
            SELECT id, source_type, source_id, input_text, report_json, ai_used, created_at
            FROM ai_learning_reports
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (int(user["id"]), limit),
        ).fetchall()
        reports = []
        for row in rows:
            item = dict(row)
            item["report"] = json_loads(item.pop("report_json"), {})
            item["ai_used"] = bool(item["ai_used"])
            reports.append(item)
        return {"success": True, "reports": reports}


@router.get("/api/speaking-missions")
async def list_speaking_missions(request: Request, user: dict = Depends(get_current_user)):
    with _managed_conn(request) as conn:
        if not is_feature_enabled(conn, "speaking_missions"):
            return _disabled("speaking_missions")
        return {"success": True, "missions": SPEAKING_MISSIONS}


@router.post("/api/speaking-missions/{mission_id}/attempt")
async def attempt_speaking_mission(mission_id: str, request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    transcript = str(body.get("transcript") or "").strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="transcript is required")
    pronunciation_score = float(body.get("pronunciation_score") or 0)
    with _managed_conn(request) as conn:
        if not is_feature_enabled(conn, "speaking_missions"):
            return _disabled("speaking_missions")
        result = evaluate_mission(mission_id, transcript, pronunciation_score)
        cursor = conn.execute(
            """
            INSERT INTO speaking_mission_attempts (user_id, mission_id, transcript, score, result_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (int(user["id"]), mission_id, transcript, result["score"], json_dumps(result)),
        )
        conn.commit()
        return {"success": True, "id": cursor.lastrowid, "result": result}


@router.post("/api/lesson-packages/generate")
async def generate_lesson_package(request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    topic = str(body.get("topic") or "").strip()
    level = str(body.get("level") or "중급").strip()
    use_ai = bool(body.get("use_ai", True))
    if not topic:
        raise HTTPException(status_code=400, detail="topic is required")
    with _managed_conn(request) as conn:
        if not is_feature_enabled(conn, "lesson_packages"):
            return _disabled("lesson_packages")
        credit = _credit(request, int(user["id"]), "lesson")
        if not credit.get("ok"):
            return JSONResponse(status_code=429, content={"success": False, "message": "Credits exhausted", "remaining": credit.get("remaining", 0)})
        ai_payload = None
        ai_used = False
        if use_ai:
            prompt = (
                "한국어 수업 1회차 패키지를 JSON으로 작성하세요. "
                "필드는 title, warmup_questions, key_expressions, dialogue, vocabulary, "
                "pronunciation_sentences, roleplay, quiz, homework 입니다.\n"
                f"주제: {topic}\n레벨: {level}"
            )
            out = _call_text_model(request, prompt)
            parsed = parse_model_output(out or "") if out else None
            if isinstance(parsed, dict):
                ai_payload = parsed
                ai_used = True
        package = build_lesson_package(topic, level, ai_payload)
        cursor = conn.execute(
            "INSERT INTO lesson_packages (user_id, topic, level, package_json, ai_used) VALUES (?, ?, ?, ?, ?)",
            (int(user["id"]), topic, level, json_dumps(package), 1 if ai_used else 0),
        )
        conn.commit()
        return {"success": True, "id": cursor.lastrowid, "package": package, "ai_used": ai_used}


@router.get("/api/lesson-packages")
async def list_lesson_packages(request: Request, user: dict = Depends(get_current_user)):
    with _managed_conn(request) as conn:
        rows = conn.execute(
            "SELECT id, topic, level, ai_used, created_at FROM lesson_packages WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 50",
            (int(user["id"]),),
        ).fetchall()
        return {"success": True, "packages": [dict(row) for row in rows]}


@router.get("/api/lesson-packages/{package_id}")
async def get_lesson_package(package_id: int, request: Request, user: dict = Depends(get_current_user)):
    with _managed_conn(request) as conn:
        row = conn.execute(
            "SELECT id, topic, level, package_json, ai_used, created_at FROM lesson_packages WHERE id = ? AND user_id = ?",
            (package_id, int(user["id"])),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="package not found")
        item = dict(row)
        item["package"] = json_loads(item.pop("package_json"), {})
        item["ai_used"] = bool(item["ai_used"])
        return {"success": True, "lesson_package": item}


@router.get("/api/admin/ai-insights")
async def get_admin_ai_insights(request: Request, admin: dict = Depends(get_current_admin_user)):
    with _managed_conn(request) as conn:
        if not is_feature_enabled(conn, "admin_ai_insights"):
            return _disabled("admin_ai_insights")
        return {"success": True, "insights": build_admin_insights(conn)}


@router.get("/api/admin/ai-feature-settings")
async def get_ai_feature_settings(request: Request, admin: dict = Depends(get_current_admin_user)):
    with _managed_conn(request) as conn:
        return {"success": True, "settings": list_feature_settings(conn)}


@router.post("/api/admin/ai-feature-settings")
async def update_ai_feature_settings(request: Request, admin: dict = Depends(get_current_admin_user)):
    body = await request.json()
    settings = body.get("settings") if isinstance(body.get("settings"), dict) else body
    with _managed_conn(request) as conn:
        set_feature_settings(conn, {str(k): bool(v) for k, v in dict(settings).items()})
        return {"success": True, "settings": list_feature_settings(conn)}
