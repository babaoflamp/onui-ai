import sqlite3

import pytest

from backend.services.ai_learning_service import (
    FEATURE_DEFAULTS,
    build_admin_insights,
    build_curriculum,
    build_lesson_package,
    build_weakness_map,
    complete_routine_step,
    ensure_ai_schema,
    evaluate_mission,
    get_or_create_today_recommendation,
    is_feature_enabled,
    list_feature_settings,
    normalize_learning_report,
    set_feature_settings,
)


def memory_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_ai_schema_creates_default_feature_settings():
    conn = memory_conn()
    try:
        ensure_ai_schema(conn)
        settings = {item["feature_key"]: item["enabled"] for item in list_feature_settings(conn)}

        assert set(FEATURE_DEFAULTS) <= set(settings)
        assert all(settings[key] is True for key in FEATURE_DEFAULTS)
    finally:
        conn.close()


def test_feature_settings_can_be_toggled_and_ignore_unknown_keys():
    conn = memory_conn()
    try:
        set_feature_settings(conn, {"ai_coach": False, "unknown_feature": False})

        assert is_feature_enabled(conn, "ai_coach") is False
        assert is_feature_enabled(conn, "lesson_packages") is True
        assert conn.execute("SELECT COUNT(*) FROM ai_feature_settings WHERE feature_key = 'unknown_feature'").fetchone()[0] == 0
    finally:
        conn.close()


def test_today_recommendation_is_persisted_and_step_can_complete():
    conn = memory_conn()
    try:
        first = get_or_create_today_recommendation(conn, 7)
        second = get_or_create_today_recommendation(conn, 7)

        assert first["id"] == second["id"]
        assert len(first["routine"]) >= 3

        completed = complete_routine_step(conn, 7, first["routine"][0]["id"])
        assert completed["routine"][0]["status"] == "completed"
    finally:
        conn.close()


def test_weakness_map_and_curriculum_prioritize_low_activity():
    activity = {
        "avg_score": 62,
        "avg_fluency": 58,
        "total_practices": 2,
        "saved_vocab_count": 1,
        "learning_days_14d": 1,
        "incomplete_videos": [{"video_id": "intro"}],
    }

    weakness = build_weakness_map(activity)
    curriculum = build_curriculum(activity, weakness)

    assert weakness["primary"]["key"] in {"pronunciation", "fluency", "vocabulary", "consistency"}
    assert len(weakness["categories"]) == 6
    assert curriculum["weeks"]
    assert curriculum["weeks"][0]["activities"]


def test_evaluate_mission_scores_required_phrases():
    result = evaluate_mission(
        "refund-convenience-store",
        "죄송합니다. 영수증이 있어요. 환불 받을 수 있을까요?",
        pronunciation_score=90,
    )

    assert result["passed"] is True
    assert result["score"] >= 70
    assert all(item["used"] for item in result["phrase_results"])


def test_evaluate_mission_rejects_unknown_mission():
    with pytest.raises(ValueError):
        evaluate_mission("missing", "안녕하세요")


def test_learning_report_and_lesson_package_include_transparency_notes():
    report = normalize_learning_report("speech", "안녕하세요", {"score": 81})
    package = build_lesson_package("병원 예약", "중급")

    assert report["level_estimate"] == "중급"
    assert report["transparency_note"]
    assert package["title"].startswith("병원 예약")
    assert package["dialogue"]
    assert package["transparency_note"]


def test_admin_insights_reports_risk_and_ai_activity():
    conn = memory_conn()
    try:
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, nickname TEXT, email TEXT, role TEXT)")
        conn.executemany(
            "INSERT INTO users (id, nickname, email, role) VALUES (?, ?, ?, ?)",
            [(1, "Learner", "learner@example.com", "learner"), (2, "Admin", "admin@example.com", "system_admin")],
        )
        ensure_ai_schema(conn)
        conn.execute("INSERT INTO ai_learning_reports (user_id, source_type, report_json) VALUES (1, 'speech', '{}')")
        conn.execute("INSERT INTO speaking_mission_attempts (user_id, mission_id, result_json) VALUES (1, 'order-restaurant', '{}')")
        conn.execute("INSERT INTO lesson_packages (user_id, topic, package_json) VALUES (1, '여행', '{}')")
        conn.commit()

        insights = build_admin_insights(conn)

        assert insights["learner_count"] == 1
        assert insights["at_risk_learners"]
        assert {item["key"]: item["count"] for item in insights["ai_activity"]} == {
            "feedback_reports": 1,
            "speaking_missions": 1,
            "lesson_packages": 1,
        }
    finally:
        conn.close()
