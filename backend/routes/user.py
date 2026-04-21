import os
import sqlite3
import json
import logging
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Depends, Form
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from backend.routes.deps import (
    get_current_user,
    get_optional_user,
    get_user_credits,
    hash_password,
    verify_password
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

logger = logging.getLogger("uvicorn.error")

def _clear_user_cache(request: Request):
    """Helper to clear user cache if available in app.state."""
    if hasattr(request.app.state, "clear_user_cache"):
        request.app.state.clear_user_cache()

# HTML Pages
@router.get("/mypage")
def mypage_page(request: Request):
    # We could use a dependency for redirect but for now keep it simple
    active_sessions = getattr(request.app.state, "active_sessions", {})
    token = request.cookies.get("session_token", "")
    if not token or token not in active_sessions:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(request, "mypage.html")

@router.get("/change-password")
def change_password_page(request: Request):
    active_sessions = getattr(request.app.state, "active_sessions", {})
    token = request.cookies.get("session_token", "")
    if not token or token not in active_sessions:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(request, "change-password.html")

# API Endpoints
@router.get("/api/user/profile")
async def get_user_profile(user: dict = Depends(get_current_user)):
    # user is already fetched by get_current_user dependency
    profile = user.copy()
    profile.pop("password_hash", None)
    return {"success": True, "user": profile}

@router.post("/api/user/profile/update")
async def update_user_profile(
    request: Request,
    nickname: str = Form(None),
    native_lang: str = Form(None),
    affiliation: str = Form(None),
    time_pref: str = Form(None),
    interests: str = Form(None),
    goal: str = Form(None),
    exam_level: str = Form(None),
    reason: str = Form(None),
    style: str = Form(None),
    user: dict = Depends(get_current_user)
):
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    user_id = user["id"]
    
    # Process interests (string or json list)
    interests_list = []
    if interests:
        try:
            interests_list = json.loads(interests)
            if not isinstance(interests_list, list):
                interests_list = [str(interests)]
        except:
            interests_list = [interests]

    if nickname and len(nickname) > 50:
        raise HTTPException(status_code=400, detail="닉네임은 50자 이하여야 합니다.")

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        updates = []
        values = []

        if nickname:
            updates.append("nickname = ?")
            values.append(nickname)
        if native_lang:
            updates.append("native_lang = ?")
            values.append(native_lang)
        if affiliation:
            updates.append("affiliation = ?")
            values.append(affiliation)
        if time_pref:
            updates.append("time_pref = ?")
            values.append(time_pref)
        
        updates.append("interests = ?")
        values.append(json.dumps(interests_list, ensure_ascii=False))
        
        if goal:
            updates.append("goal = ?")
            values.append(goal)
        if exam_level:
            updates.append("exam_level = ?")
            values.append(exam_level)
        if reason:
            updates.append("reason = ?")
            values.append(reason)
        if style:
            updates.append("style = ?")
            values.append(style)

        if updates:
            values.append(user_id)
            cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", values)
            conn.commit()
    finally:
        conn.close()

    _clear_user_cache(request)
    # Return updated user info (will be re-fetched by dependency or frontend)
    return {"success": True}

@router.post("/api/user/password/change")
async def change_password(
    request: Request,
    user: dict = Depends(get_current_user)
):
    payload = await request.json()
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    user_id = user["id"]

    current_password = payload.get("current_password") or ""
    new_password = payload.get("new_password") or ""
    confirm_password = payload.get("confirm_password") or ""

    if not current_password or not new_password:
        raise HTTPException(status_code=400, detail="비밀번호를 입력하세요.")
    if new_password != confirm_password:
        raise HTTPException(status_code=400, detail="새 비밀번호가 일치하지 않습니다.")
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="새 비밀번호는 8자 이상이어야 합니다.")

    # Need password_hash to verify
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if not row or not verify_password(row["password_hash"], current_password):
            raise HTTPException(status_code=401, detail="현재 비밀번호가 올바르지 않습니다.")

        new_hash = hash_password(new_password)
        cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
        conn.commit()
    finally:
        conn.close()

    _clear_user_cache(request)
    return {"success": True, "message": "비밀번호가 변경되었습니다."}

@router.get("/api/credits")
async def get_credits_api(request: Request, user: dict = Depends(get_current_user)):
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    daily_credits = int(os.getenv("DAILY_CREDITS", "50"))
    info = get_user_credits(db_path, user["id"], daily_credits)
    return JSONResponse({"success": True, **info})
