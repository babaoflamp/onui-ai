import os
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger("uvicorn.error")

@router.get("/")
def landing_page(request: Request):
    return templates.TemplateResponse(request, "index.html")

@router.get("/video-learning")
def video_learning_page(request: Request):
    videos = []
    try:
        if os.path.exists("data/onui-tube.json"):
            with open("data/onui-tube.json", "r", encoding="utf-8") as f:
                videos = json.load(f)
            for v in videos:
                v.setdefault('transcript_offset', 0)
    except Exception:
        pass
    return templates.TemplateResponse(request, "video-learning.html", {"videos": videos})

@router.get("/onui-beats")
def onui_beats_page(request: Request):
    songs = []
    try:
        if os.path.exists("data/onui-beats.json"):
            with open("data/onui-beats.json", "r", encoding="utf-8") as f:
                songs = json.load(f)
    except Exception:
        pass
    return templates.TemplateResponse(request, "onui-beats.html", {"songs": songs})

@router.get("/voice-call")
def voice_call_page(request: Request):
    return templates.TemplateResponse(request, "voice-call.html")

@router.get("/onui-grammar")
def onui_grammar_page(request: Request):
    active_sessions = getattr(request.app.state, "active_sessions", {})
    token = request.cookies.get("session_token", "")
    if not token or token not in active_sessions:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(request, "onui-grammar.html")

@router.get("/content-generation")
def content_generation_page(request: Request):
    return templates.TemplateResponse(request, "content-generation.html")

@router.get("/daily-expression")
def daily_expression_page(request: Request):
    return templates.TemplateResponse(request, "daily-expression.html")

@router.get("/signup")
def signup_page(request: Request):
    return templates.TemplateResponse(request, "signup.html")

@router.get("/stt-api-test")
def stt_api_test_page(request: Request):
    return templates.TemplateResponse(request, "stt-multi-test.html")

@router.get("/api-test")
def api_test_page(request: Request):
    return templates.TemplateResponse(request, "api-test.html")

@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")

@router.get("/learning-progress")
def learning_progress_page(request: Request):
    return templates.TemplateResponse(request, "learning-progress.html")

@router.get("/dashboard")
def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")
