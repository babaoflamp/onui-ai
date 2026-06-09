from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from backend.database import ensure_ai_learning_tables

FEATURE_DEFAULTS = {
    "ai_coach": True,
    "ai_feedback_reports": True,
    "speaking_missions": True,
    "lesson_packages": True,
    "admin_ai_insights": True,
}

SPEAKING_MISSIONS = [
    {
        "id": "refund-convenience-store",
        "title": "편의점에서 환불 요청하기",
        "level": "초급",
        "scenario": "편의점에서 잘못 산 물건을 정중하게 환불 요청합니다.",
        "required_phrases": ["환불", "영수증", "죄송합니다"],
        "target_seconds": 45,
        "next_url": "/voice-call",
    },
    {
        "id": "explain-absence-professor",
        "title": "교수님께 결석 사유 설명하기",
        "level": "중급",
        "scenario": "수업에 빠진 이유를 설명하고 보충 방법을 질문합니다.",
        "required_phrases": ["결석", "과제", "보충"],
        "target_seconds": 60,
        "next_url": "/roleplay",
    },
    {
        "id": "change-plans-friend",
        "title": "친구와 약속 변경하기",
        "level": "초급",
        "scenario": "친구에게 약속 시간을 바꾸자고 자연스럽게 말합니다.",
        "required_phrases": ["미안", "시간", "괜찮아"],
        "target_seconds": 45,
        "next_url": "/voice-call",
    },
    {
        "id": "order-restaurant",
        "title": "식당에서 주문하기",
        "level": "초급",
        "scenario": "식당에서 메뉴를 묻고 원하는 음식을 주문합니다.",
        "required_phrases": ["주세요", "메뉴", "추천"],
        "target_seconds": 45,
        "next_url": "/content-generation",
    },
    {
        "id": "ask-directions",
        "title": "길 묻기",
        "level": "중급",
        "scenario": "처음 가는 장소까지 가는 방법을 묻고 확인합니다.",
        "required_phrases": ["어디", "가려면", "감사합니다"],
        "target_seconds": 60,
        "next_url": "/video-learning",
    },
]


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def json_loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def ensure_ai_schema(conn: sqlite3.Connection) -> None:
    ensure_ai_learning_tables(conn)
    conn.commit()


def is_feature_enabled(conn: sqlite3.Connection, feature_key: str) -> bool:
    ensure_ai_schema(conn)
    row = conn.execute(
        "SELECT enabled FROM ai_feature_settings WHERE feature_key = ?",
        (feature_key,),
    ).fetchone()
    if row is None:
        return FEATURE_DEFAULTS.get(feature_key, True)
    return bool(row[0])


def list_feature_settings(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    ensure_ai_schema(conn)
    rows = conn.execute(
        "SELECT feature_key, enabled, updated_at FROM ai_feature_settings ORDER BY feature_key"
    ).fetchall()
    return [
        {"feature_key": row[0], "enabled": bool(row[1]), "updated_at": row[2]}
        for row in rows
    ]


def set_feature_settings(conn: sqlite3.Connection, settings: dict[str, bool]) -> None:
    ensure_ai_schema(conn)
    for key, enabled in settings.items():
        if key not in FEATURE_DEFAULTS:
            continue
        conn.execute(
            """
            INSERT INTO ai_feature_settings (feature_key, enabled, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(feature_key) DO UPDATE SET
                enabled = excluded.enabled,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, 1 if enabled else 0),
        )
    conn.commit()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def _date_part(value: Any) -> str:
    return str(value or "").split(" ")[0].split("T")[0]


def collect_user_activity(conn: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    ensure_ai_schema(conn)
    today = datetime.now().date()
    since = (today - timedelta(days=13)).isoformat()

    sentence_rows = []
    if _table_exists(conn, "sentence_scores"):
        sentence_rows = [dict(r) for r in conn.execute(
            """
            SELECT sentence_id, sentence_text, score_latest, accuracy_latest,
                   fluency_accuracy_latest, attempt_count, last_attempted_at
            FROM sentence_scores
            WHERE (user_id = ? OR user_id = ?) AND COALESCE(score_latest, 0) > 0
            ORDER BY last_attempted_at DESC, id DESC
            LIMIT 50
            """,
            (user_id, str(user_id)),
        ).fetchall()]

    pron_rows = []
    if _table_exists(conn, "pronunciation_attempt_history"):
        pron_rows = [dict(r) for r in conn.execute(
            """
            SELECT sentence_id, sentence_text, overall_score AS score_latest,
                   accuracy AS accuracy_latest, fluency_accuracy AS fluency_accuracy_latest,
                   1 AS attempt_count, created_at AS last_attempted_at
            FROM pronunciation_attempt_history
            WHERE user_id = ? AND COALESCE(overall_score, 0) > 0
            ORDER BY created_at DESC, id DESC
            LIMIT 50
            """,
            (user_id,),
        ).fetchall()]

    scores = pron_rows or sentence_rows
    score_values = [float(r.get("score_latest") or 0) for r in scores if float(r.get("score_latest") or 0) > 0]
    fluency_values = [float(r.get("fluency_accuracy_latest") or 0) for r in scores if float(r.get("fluency_accuracy_latest") or 0) > 0]
    low_sentences = [r for r in scores if float(r.get("score_latest") or 0) and float(r.get("score_latest") or 0) < 75][:5]

    saved_vocab_count = 0
    recent_vocab = []
    if _table_exists(conn, "user_saved_vocab"):
        vocab_rows = conn.execute(
            "SELECT label, meaning, saved_at FROM user_saved_vocab WHERE user_id = ? ORDER BY saved_at DESC LIMIT 20",
            (user_id,),
        ).fetchall()
        recent_vocab = [dict(r) for r in vocab_rows]
        saved_vocab_count = len(recent_vocab)

    video_progress = []
    if _table_exists(conn, "user_video_progress"):
        video_progress = [dict(r) for r in conn.execute(
            """
            SELECT video_id, watched_seconds, duration_seconds, completed, updated_at
            FROM user_video_progress
            WHERE user_id = ? OR user_id = ?
            ORDER BY updated_at DESC
            LIMIT 20
            """,
            (user_id, str(user_id)),
        ).fetchall()]

    study_minutes = 0
    study_dates = set()
    if _table_exists(conn, "study_sessions"):
        study_rows = conn.execute(
            "SELECT duration_seconds, created_at FROM study_sessions WHERE user_id = ? AND created_at >= ?",
            (user_id, since),
        ).fetchall()
        study_minutes = round(sum(float(r[0] or 0) for r in study_rows) / 60)
        study_dates = {_date_part(r[1]) for r in study_rows if r[1]}

    attendance_dates = set()
    if _table_exists(conn, "attendance"):
        attendance_dates = {
            str(r[0]) for r in conn.execute("SELECT date FROM attendance WHERE user_id = ?", (user_id,)).fetchall() if r[0]
        }

    score_dates = {_date_part(r.get("last_attempted_at")) for r in scores if r.get("last_attempted_at")}
    learning_dates = {d for d in (study_dates | attendance_dates | score_dates) if d}
    streak = 0
    check = today
    while check.isoformat() in learning_dates:
        streak += 1
        check -= timedelta(days=1)

    avg_score = round(sum(score_values) / len(score_values), 1) if score_values else 0
    avg_fluency = round(sum(fluency_values) / len(fluency_values), 1) if fluency_values else 0
    incomplete_videos = [v for v in video_progress if not int(v.get("completed") or 0)]

    return {
        "user_id": user_id,
        "avg_score": avg_score,
        "avg_fluency": avg_fluency,
        "total_practices": len(score_values),
        "low_sentences": low_sentences,
        "recent_vocab": recent_vocab,
        "saved_vocab_count": saved_vocab_count,
        "video_progress": video_progress,
        "incomplete_videos": incomplete_videos,
        "study_minutes_14d": study_minutes,
        "learning_days_14d": len([d for d in learning_dates if d >= since]),
        "streak": streak,
    }


def build_weakness_map(activity: dict[str, Any]) -> dict[str, Any]:
    categories = []
    def add(key: str, label: str, score: int, reason: str, next_action: str, url: str):
        categories.append({
            "key": key,
            "label": label,
            "score": max(0, min(100, int(score))),
            "reason": reason,
            "next_action": next_action,
            "url": url,
        })

    avg_score = float(activity.get("avg_score") or 0)
    avg_fluency = float(activity.get("avg_fluency") or 0)
    practices = int(activity.get("total_practices") or 0)
    vocab_count = int(activity.get("saved_vocab_count") or 0)
    learning_days = int(activity.get("learning_days_14d") or 0)
    incomplete_videos = len(activity.get("incomplete_videos") or [])

    add(
        "pronunciation",
        "발음 정확도",
        100 - int(avg_score or 40),
        "최근 발음 평균이 낮거나 연습 기록이 부족합니다." if avg_score < 75 else "좋은 수준이지만 유지 연습이 필요합니다.",
        "낮은 점수 문장 2개를 다시 녹음하세요.",
        "/speechpro-practice",
    )
    add(
        "fluency",
        "말하기 유창성",
        100 - int(avg_fluency or 45),
        "발화 흐름과 속도 연습이 필요합니다." if avg_fluency < 75 else "짧은 대화에서 긴 대화로 확장해보세요.",
        "AI 음성 통화로 3분 대화를 진행하세요.",
        "/voice-call",
    )
    add(
        "vocabulary",
        "어휘 회상",
        80 if vocab_count < 5 else max(20, 70 - vocab_count),
        "저장한 OnuiTube 단어가 부족합니다." if vocab_count < 5 else "저장 단어를 문장 안에서 써보세요.",
        "OnuiTube에서 단어 3개를 저장하고 예문을 만드세요.",
        "/video-learning",
    )
    add(
        "listening",
        "듣기 이해",
        75 if incomplete_videos else 35,
        "완료하지 않은 영상 학습이 있습니다." if incomplete_videos else "영상 학습 기록이 안정적입니다.",
        "미완료 영상을 하나 끝까지 보고 단어를 저장하세요.",
        "/video-learning",
    )
    add(
        "conversation",
        "상황 대화",
        70 if practices < 5 else 45,
        "실전 상황 대화 기록이 더 필요합니다." if practices < 5 else "역할극으로 표현 다양성을 늘리세요.",
        "말하기 미션 하나를 완료하세요.",
        "/roleplay",
    )
    add(
        "consistency",
        "학습 지속성",
        85 if learning_days < 3 else max(20, 80 - learning_days * 8),
        "최근 2주 학습일이 적습니다." if learning_days < 3 else "연속 학습 흐름을 유지 중입니다.",
        "오늘 15분 루틴을 완료하세요.",
        "/dashboard",
    )
    categories.sort(key=lambda item: item["score"], reverse=True)
    return {
        "primary": categories[0] if categories else None,
        "categories": categories,
        "summary": categories[0]["reason"] if categories else "분석할 학습 데이터가 아직 부족합니다.",
    }


def build_today_routine(activity: dict[str, Any], weakness: dict[str, Any]) -> list[dict[str, Any]]:
    low_sentence = None
    if activity.get("low_sentences"):
        low_sentence = activity["low_sentences"][0].get("sentence_text") or "최근 낮은 점수 문장"
    primary = (weakness.get("primary") or {}).get("key")
    routine = []
    routine.append({
        "id": "pronunciation-review",
        "title": "발음 리셋",
        "duration_min": 4,
        "reason": "최근 발음 기록을 바탕으로 가장 빠르게 점수를 올릴 수 있는 단계입니다.",
        "action": low_sentence or "짧은 예문을 하나 녹음하세요.",
        "url": "/speechpro-practice",
        "status": "pending",
    })
    routine.append({
        "id": "vocab-context",
        "title": "단어를 문장으로 바꾸기",
        "duration_min": 3,
        "reason": "저장 단어를 실제 대화에서 쓰도록 연결합니다.",
        "action": "OnuiTube 저장 단어 1개로 새 문장을 만드세요.",
        "url": "/video-learning",
        "status": "pending",
    })
    routine.append({
        "id": "speaking-mission",
        "title": "상황 말하기 미션",
        "duration_min": 5,
        "reason": "실전 회화 자신감을 높이는 연습입니다.",
        "action": "오늘의 말하기 미션을 1개 완료하세요.",
        "url": "/roleplay",
        "status": "pending",
    })
    if primary in {"listening", "vocabulary"}:
        routine.append({
            "id": "onuitube-listening",
            "title": "짧은 영상 듣기",
            "duration_min": 5,
            "reason": "듣기와 어휘를 동시에 보강합니다.",
            "action": "영상 하나를 보고 단어 3개를 저장하세요.",
            "url": "/video-learning",
            "status": "pending",
        })
    else:
        routine.append({
            "id": "ai-voice-call",
            "title": "AI 음성 통화",
            "duration_min": 5,
            "reason": "발음과 유창성을 자연 대화에서 확인합니다.",
            "action": "AI 튜터와 3분 대화를 진행하세요.",
            "url": "/voice-call",
            "status": "pending",
        })
    return routine[:4]


def get_or_create_today_recommendation(conn: sqlite3.Connection, user_id: int) -> dict[str, Any]:
    ensure_ai_schema(conn)
    today = datetime.now().date().isoformat()
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id, routine_json, weakness_json, status, created_at FROM ai_coach_recommendations WHERE user_id = ? AND recommendation_date = ?",
        (user_id, today),
    ).fetchone()
    if row:
        return {
            "id": row["id"],
            "date": today,
            "routine": json_loads(row["routine_json"], []),
            "weakness_map": json_loads(row["weakness_json"], {}),
            "status": row["status"],
            "created_at": row["created_at"],
        }

    activity = collect_user_activity(conn, user_id)
    weakness = build_weakness_map(activity)
    routine = build_today_routine(activity, weakness)
    cursor = conn.execute(
        """
        INSERT INTO ai_coach_recommendations
            (user_id, recommendation_date, routine_json, weakness_json, status)
        VALUES (?, ?, ?, ?, 'active')
        """,
        (user_id, today, json_dumps(routine), json_dumps(weakness)),
    )
    conn.commit()
    return {
        "id": cursor.lastrowid,
        "date": today,
        "routine": routine,
        "weakness_map": weakness,
        "status": "active",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def complete_routine_step(conn: sqlite3.Connection, user_id: int, step_id: str) -> dict[str, Any]:
    rec = get_or_create_today_recommendation(conn, user_id)
    routine = rec.get("routine") or []
    for step in routine:
        if step.get("id") == step_id:
            step["status"] = "completed"
            step["completed_at"] = datetime.now().isoformat(timespec="seconds")
    status = "completed" if routine and all(step.get("status") == "completed" for step in routine) else "active"
    conn.execute(
        "UPDATE ai_coach_recommendations SET routine_json = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
        (json_dumps(routine), status, rec["id"], user_id),
    )
    conn.commit()
    rec["routine"] = routine
    rec["status"] = status
    return rec


def build_curriculum(activity: dict[str, Any], weakness: dict[str, Any]) -> dict[str, Any]:
    categories = weakness.get("categories") or []
    focus = categories[:3]
    weeks = []
    for idx, item in enumerate(focus, start=1):
        weeks.append({
            "week": idx,
            "focus": item["label"],
            "goal": item["next_action"],
            "activities": [
                {"title": "짧은 복습", "url": item["url"], "minutes": 5},
                {"title": "실전 적용", "url": "/roleplay" if item["key"] != "listening" else "/video-learning", "minutes": 10},
            ],
        })
    return {
        "title": "나의 3주 보강 커리큘럼",
        "summary": weakness.get("summary") or "학습 데이터를 기반으로 보강 순서를 추천했습니다.",
        "weeks": weeks,
    }


def normalize_learning_report(source_type: str, input_text: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    text = (input_text or payload.get("text") or "").strip()
    score = float(payload.get("score") or payload.get("overall_score") or payload.get("accuracy_rate") or 0)
    strengths = []
    corrections = []
    if score >= 80:
        strengths.append("핵심 의미를 자연스럽게 전달했습니다.")
    elif score > 0:
        corrections.append("문장을 천천히 나누어 다시 말해보세요.")
    else:
        corrections.append("짧은 문장부터 녹음해 피드백 데이터를 쌓아보세요.")
    if text:
        strengths.append(f"연습 문장: {text[:80]}")
    return {
        "source_type": source_type,
        "level_estimate": "고급" if score >= 90 else "중급" if score >= 75 else "초급",
        "strengths": strengths[:3] or ["학습 기록을 시작했습니다."],
        "corrections": corrections[:3],
        "better_expressions": payload.get("better_expressions") or ["같은 표현을 더 천천히, 또렷하게 말해보세요."],
        "next_practice": payload.get("next_practice") or ["AI 음성 통화 3분", "발음 문장 2개 재녹음"],
        "transparency_note": "AI 생성 피드백은 학습 참고용이며 교사 피드백을 대체하지 않습니다.",
    }


def evaluate_mission(mission_id: str, transcript: str, pronunciation_score: float = 0) -> dict[str, Any]:
    mission = next((m for m in SPEAKING_MISSIONS if m["id"] == mission_id), None)
    if not mission:
        raise ValueError("Unknown mission")
    transcript_norm = re.sub(r"\s+", "", transcript or "").lower()
    phrase_results = []
    for phrase in mission["required_phrases"]:
        used = phrase.replace(" ", "").lower() in transcript_norm
        phrase_results.append({"phrase": phrase, "used": used})
    phrase_score = sum(1 for item in phrase_results if item["used"]) / max(len(phrase_results), 1) * 60
    length_score = min(len(transcript_norm) / 60, 1) * 20
    pron_score = min(max(float(pronunciation_score or 0), 0), 100) / 100 * 20
    total = round(phrase_score + length_score + pron_score, 1)
    return {
        "mission": mission,
        "score": total,
        "passed": total >= 70,
        "phrase_results": phrase_results,
        "feedback": "필수 표현을 잘 활용했습니다." if total >= 70 else "필수 표현을 더 명확하게 넣어 다시 시도해보세요.",
        "transparency_note": "AI/자동 평가는 학습 참고용입니다.",
    }


def build_lesson_package(topic: str, level: str, ai_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if ai_payload and isinstance(ai_payload, dict):
        package = dict(ai_payload)
    else:
        package = {}
    topic = (topic or "한국어 회화").strip()
    level = (level or "중급").strip()
    package.setdefault("title", f"{topic} 수업 패키지")
    package.setdefault("level", level)
    package.setdefault("warmup_questions", [f"{topic}에 대해 이야기해 본 적이 있나요?", "비슷한 상황에서 어떤 표현을 쓰고 싶나요?"])
    package.setdefault("key_expressions", ["괜찮아요", "다시 말씀해 주세요", "추천해 주세요"])
    package.setdefault("dialogue", [
        {"speaker": "지수", "text": f"오늘은 {topic}에 대해 연습해요."},
        {"speaker": "민준", "text": "좋아요. 어떤 표현이 중요해요?"},
        {"speaker": "지수", "text": "상황에 맞게 정중하게 말하는 것이 중요해요."},
        {"speaker": "민준", "text": "그럼 역할극으로 연습해 볼게요."},
    ])
    package.setdefault("vocabulary", ["상황", "표현", "연습", "질문", "대답"])
    package.setdefault("pronunciation_sentences", [f"{topic}을 자연스럽게 말해 보세요.", "천천히 또박또박 말하면 좋아요."])
    package.setdefault("roleplay", {"scenario": f"{topic} 상황에서 1분 동안 대화하기", "success_criteria": ["핵심 표현 2개 사용", "마무리 인사하기"]})
    package.setdefault("quiz", [{"display": "오늘의 주제는 ___ 입니다.", "blank_word": topic, "hint": "수업 제목"}])
    package.setdefault("homework", ["핵심 표현 3개로 짧은 문장 만들기", "AI 음성 통화에서 같은 주제로 말하기"])
    package["transparency_note"] = "AI 생성 수업 자료는 교사용 초안이며 최종 검토가 필요합니다."
    return package


def build_admin_insights(conn: sqlite3.Connection) -> dict[str, Any]:
    ensure_ai_schema(conn)
    conn.row_factory = sqlite3.Row
    users = [dict(r) for r in conn.execute("SELECT id, nickname, email FROM users WHERE COALESCE(role, 'learner') != 'system_admin' ORDER BY id DESC LIMIT 200").fetchall()]
    at_risk = []
    low_score_count = 0
    inactive_count = 0
    for user in users:
        activity = collect_user_activity(conn, int(user["id"]))
        if activity["avg_score"] and activity["avg_score"] < 70:
            low_score_count += 1
            at_risk.append({"user_id": user["id"], "nickname": user.get("nickname") or user.get("email"), "reason": "발음 평균 70점 미만", "avg_score": activity["avg_score"]})
        elif activity["learning_days_14d"] == 0:
            inactive_count += 1
            at_risk.append({"user_id": user["id"], "nickname": user.get("nickname") or user.get("email"), "reason": "최근 14일 학습 기록 없음", "avg_score": activity["avg_score"]})
    common_weaknesses = []
    if low_score_count:
        common_weaknesses.append({"label": "발음 정확도", "count": low_score_count, "recommendation": "짧은 문장 낭독과 받침 발음 복습을 배정하세요."})
    if inactive_count:
        common_weaknesses.append({"label": "학습 지속성", "count": inactive_count, "recommendation": "15분 루틴과 출석 체크 리마인드를 권장하세요."})
    if not common_weaknesses:
        common_weaknesses.append({"label": "데이터 부족", "count": 0, "recommendation": "학생들이 발음 평가와 영상 학습을 먼저 완료하도록 안내하세요."})
    recommended_activities = [
        "수업 시작 5분 발음 리셋 루틴",
        "OnuiTube 단어 3개로 짧은 대화 만들기",
        "상황 말하기 미션을 짝 활동으로 확장하기",
    ]
    ai_activity = [
        {"key": "feedback_reports", "label": "피드백 리포트", "count": conn.execute("SELECT COUNT(*) FROM ai_learning_reports").fetchone()[0]},
        {"key": "speaking_missions", "label": "말하기 미션", "count": conn.execute("SELECT COUNT(*) FROM speaking_mission_attempts").fetchone()[0]},
        {"key": "lesson_packages", "label": "수업 패키지", "count": conn.execute("SELECT COUNT(*) FROM lesson_packages").fetchone()[0]},
    ]
    return {
        "summary": f"분석 대상 {len(users)}명 중 개입 후보 {len(at_risk)}명입니다.",
        "learner_count": len(users),
        "common_weaknesses": common_weaknesses,
        "weakness_distribution": common_weaknesses,
        "at_risk_students": at_risk[:10],
        "at_risk_learners": at_risk[:10],
        "ai_activity": ai_activity,
        "recommended_class_activities": recommended_activities,
        "transparency_note": "AI/자동 인사이트는 교사용 참고 자료이며 최종 판단은 교사가 수행해야 합니다.",
    }
