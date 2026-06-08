import logging
import json
import os
import sqlite3
import time
import urllib.parse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from backend.utils import _get_state

router = APIRouter()


def _require_callable(request: Request, state_name: str, label: str):
    fn = _get_state(request, state_name)
    if not callable(fn):
        raise RuntimeError(f"{label} not configured")
    return fn


def _append_json_record(path: str, record: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rows = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                rows = json.load(f)
        except Exception:
            rows = []
    if not isinstance(rows, list):
        rows = []
    rows.append(record)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def _set_login_cookies(
    request: Request,
    response,
    *,
    token: str,
    user: dict,
    role: str | None = None,
    include_role: bool = False,
):
    session_expiry_seconds = _get_state(request, "session_expiry_seconds")
    if not isinstance(session_expiry_seconds, int) or session_expiry_seconds <= 0:
        raise RuntimeError("Session config not configured")

    secure_cookie = bool(_get_state(request, "session_cookie_secure", False))
    response.set_cookie(
        key="session_token",
        value=token,
        max_age=session_expiry_seconds,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key="user_nickname",
        value=urllib.parse.quote(user["nickname"]),
        max_age=session_expiry_seconds,
        secure=secure_cookie,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key="user_id",
        value=str(user["id"]),
        max_age=session_expiry_seconds,
        secure=secure_cookie,
        samesite="lax",
        path="/",
    )
    if include_role:
        response.set_cookie(
            key="user_role",
            value=role or "learner",
            max_age=session_expiry_seconds,
            secure=secure_cookie,
            samesite="lax",
            path="/",
        )
        response.set_cookie(
            key="is_admin",
            value="true" if user.get("is_admin") else "false",
            max_age=session_expiry_seconds,
            secure=secure_cookie,
            samesite="lax",
            path="/",
        )


@router.post("/api/signup")
async def signup(request: Request):
    payload = await request.json()
    store_user_signup = _require_callable(request, "store_user_signup", "Signup")
    user = store_user_signup(payload)
    return {"success": True, "email": user["email"], "nickname": user["nickname"]}


@router.post("/api/landing-intake")
async def landing_intake(request: Request):
    """Backward compatibility: reuse signup handler."""
    return await signup(request)


@router.post("/api/landing-intent")
async def landing_intent(request: Request):
    payload = await request.json()
    goal = str(payload.get("goal") or "").strip()
    level = str(payload.get("level") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    native_lang = str(payload.get("native_lang") or "").strip()
    if not goal:
        raise HTTPException(status_code=400, detail="goal is required")

    record = {
        "goal": goal,
        "level": level,
        "reason": reason,
        "native_lang": native_lang,
        "ts": time.time(),
    }
    _append_json_record("data/landing_intent.json", record)

    logger = _get_state(request, "logger") or logging.getLogger(__name__)
    logger.info(
        "[LANDING_INTENT] goal=%s level=%s lang=%s",
        goal,
        level or "-",
        native_lang or "-",
    )
    return {"success": True}


@router.get("/api/login/google")
async def login_google(request: Request):
    oauth = _get_state(request, "oauth")
    logger = _get_state(request, "logger") or logging.getLogger(__name__)

    if not oauth or not oauth.google:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")

    redirect_uri = request.url_for("auth_google_callback")
    if "localhost" not in str(redirect_uri) and str(redirect_uri).startswith("http://"):
        redirect_uri = str(redirect_uri).replace("http://", "https://", 1)

    logger.info(f"[OAuth] Generated redirect_uri: {redirect_uri}")
    return await oauth.google.authorize_redirect(request, str(redirect_uri))


@router.get("/api/login/google/callback")
async def auth_google_callback(request: Request):
    oauth = _get_state(request, "oauth")
    logger = _get_state(request, "logger") or logging.getLogger(__name__)
    get_user_by_google_id = _require_callable(
        request, "get_user_by_google_id", "Google user lookup"
    )
    get_user_by_email = _require_callable(request, "get_user_by_email", "Email lookup")
    create_google_user = _require_callable(
        request, "create_google_user", "Google user creation"
    )
    create_session_token = _require_callable(
        request, "create_session_token", "Session token creation"
    )
    normalize_role = _require_callable(request, "normalize_role", "Role normalization")
    session_expiry_seconds = _get_state(request, "session_expiry_seconds")
    db_path = _get_state(request, "db_path")

    if not oauth or not oauth.google:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")
    if not isinstance(session_expiry_seconds, int) or session_expiry_seconds <= 0:
        raise RuntimeError("Session config not configured")
    if not db_path:
        raise RuntimeError("DB path not configured")

    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        logger.error(f"OAuth error: {e}")
        return RedirectResponse(url="/login?error=oauth_failed")

    user_info = token.get("userinfo")
    if not user_info:
        return RedirectResponse(url="/login?error=no_user_info")

    email = user_info.get("email")
    google_id = user_info.get("sub")
    nickname = user_info.get("name") or email.split("@")[0]

    user = get_user_by_google_id(google_id)
    if not user:
        user = get_user_by_email(email)
        if user:
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    "UPDATE users SET google_id = ? WHERE id = ?",
                    (google_id, user["id"]),
                )
                conn.commit()
            finally:
                conn.close()
        else:
            user = create_google_user(email, nickname, google_id)

    session_token = create_session_token(
        user["id"], user["email"], bool(user.get("is_admin"))
    )

    response = RedirectResponse(url="/dashboard")
    _set_login_cookies(
        request,
        response,
        token=session_token,
        user=user,
        role=normalize_role(user.get("role"), user.get("is_admin")),
        include_role=True,
    )
    return response


@router.post("/api/login")
async def login(request: Request):
    """사용자 로그인: 닉네임과 비밀번호로 인증."""
    get_user_by_email = _require_callable(request, "get_user_by_email", "Email lookup")
    get_user_by_nickname = _require_callable(
        request, "get_user_by_nickname", "Nickname lookup"
    )
    verify_password = _require_callable(
        request, "verify_password", "Password verification"
    )
    create_session_token = _require_callable(
        request, "create_session_token", "Session token creation"
    )
    normalize_role = _require_callable(request, "normalize_role", "Role normalization")
    role_system_admin = _get_state(request, "role_system_admin")
    session_expiry_seconds = _get_state(request, "session_expiry_seconds")
    logger = _get_state(request, "logger") or logging.getLogger(__name__)

    if not isinstance(session_expiry_seconds, int) or session_expiry_seconds <= 0:
        raise RuntimeError("Session config not configured")

    payload = await request.json()
    identifier = (
        payload.get("username") or payload.get("nickname") or payload.get("email") or ""
    ).strip()
    password = payload.get("password") or ""

    if not identifier or not password:
        raise HTTPException(
            status_code=400, detail="이메일/닉네임과 비밀번호를 입력하세요."
        )

    user = get_user_by_email(identifier)
    if not user:
        user = get_user_by_nickname(identifier)

    if not user or not verify_password(user["password_hash"], password):
        raise HTTPException(
            status_code=401, detail="이메일/닉네임 또는 비밀번호가 올바르지 않습니다."
        )

    token = create_session_token(user["id"], user["email"], bool(user.get("is_admin")))
    client_host = request.client.host if request.client else "Unknown"
    logger.info(
        "[LOGIN] user=%s email=%s role=%s ip=%s",
        user["nickname"],
        user["email"],
        normalize_role(user.get("role"), user.get("is_admin")),
        client_host,
    )

    role = normalize_role(user.get("role"), user.get("is_admin"))
    response_data = {
        "success": True,
        "token": token,
        "email": user["email"],
        "nickname": user["nickname"],
        "is_admin": role == role_system_admin,
        "role": role,
    }

    response = JSONResponse(content=response_data)
    _set_login_cookies(request, response, token=token, user=user, role=role)
    return response


@router.post("/api/logout")
async def logout(request: Request):
    """사용자 로그아웃."""
    parse_session_token = _require_callable(
        request, "parse_session_token", "Session parser"
    )
    active_sessions = _get_state(request, "active_sessions")
    logger = _get_state(request, "logger") or logging.getLogger(__name__)

    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        token = request.cookies.get("session_token", "")

    if token:
        session = parse_session_token(token)
        if session:
            logger.info(
                f"[LOGOUT] user_id={session['user_id']} email={session['email']}"
            )
        if isinstance(active_sessions, dict) and token in active_sessions:
            del active_sessions[token]

    return {"success": True, "message": "로그아웃되었습니다."}
