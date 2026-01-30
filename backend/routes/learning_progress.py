import logging
logger = logging.getLogger(__name__)
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse


router = APIRouter()


def _get_state(request: Request, name: str):
    return getattr(request.app.state, name, None)


@router.post("/api/learning/pronunciation-completed")
async def record_pronunciation_completed(request: Request):
    """발음 연습 완료 기록"""
    try:
        data = await request.json()
        user_id = data.get("user_id", "anonymous")
        logger.info(f"[API_CALL] user_id={user_id} endpoint={request.url.path} method={request.method} params={data}")
        score = int(data.get("score", 0))

        learning_service = _get_state(request, "learning_service")
        if learning_service is None:
            return JSONResponse(status_code=500, content={"error": "Learning service not configured"})

        result = learning_service.update_pronunciation_practice(user_id, score)
        popup_trigger = learning_service.check_popup_trigger(user_id)
        return JSONResponse({"success": True, "updated": result, "popup": popup_trigger})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/api/learning/sentence-learned")
async def record_sentence_learned(request: Request):
    """문장 학습 완료 기록"""
    try:
        data = await request.json()
        user_id = data.get("user_id", "anonymous")
        logger.info(f"[API_CALL] user_id={user_id} endpoint={request.url.path} method={request.method} params={data}")
        count = data.get("count", 1)

        learning_service = _get_state(request, "learning_service")
        if learning_service is None:
            return JSONResponse(status_code=500, content={"error": "Learning service not configured"})

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
    """사용자 학습 통계 조회"""
    try:
        learning_service = _get_state(request, "learning_service")
        if learning_service is None:
            return JSONResponse(status_code=500, content={"error": "Learning service not configured"})
        stats = learning_service.get_user_stats(user_id)
        return JSONResponse(stats)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/api/learning/today-progress/{user_id}")
async def get_today_progress(request: Request, user_id: str):
    """오늘의 학습 진도 조회"""
    try:
        learning_service = _get_state(request, "learning_service")
        if learning_service is None:
            return JSONResponse(status_code=500, content={"error": "Learning service not configured"})
        progress = learning_service.get_or_create_today_progress(user_id)
        return JSONResponse(progress)
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

    return JSONResponse({"success": True})
