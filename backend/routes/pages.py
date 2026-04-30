import os
import json
import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from backend.services.onui_tube_catalog import annotate_tube_videos

router = APIRouter()
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger("uvicorn.error")

@router.get("/")
def landing_page(request: Request):
    return templates.TemplateResponse(request, "index.html")

@router.head("/")
def landing_page_head(request: Request):
    return Response(status_code=200)

@router.get("/video-learning")
def video_learning_page(request: Request):
    if redir := getattr(request.app.state, "redirect_if_unauthenticated", lambda r: None)(request):
        return redir
    videos = []
    try:
        if os.path.exists("data/onui-tube.json"):
            with open("data/onui-tube.json", "r", encoding="utf-8") as f:
                videos = json.load(f)
            transcripts = {}
            if os.path.exists("data/onui-tube-transcripts.json"):
                with open("data/onui-tube-transcripts.json", "r", encoding="utf-8") as f:
                    transcripts = json.load(f) or {}
            videos = annotate_tube_videos(videos, transcripts)
    except Exception:
        pass
    return templates.TemplateResponse(request, "video-learning.html", {"videos": videos})

@router.get("/onui-beats")
def onui_beats_page(request: Request):
    if redir := getattr(request.app.state, "redirect_if_unauthenticated", lambda r: None)(request):
        return redir
    songs = []
    try:
        if os.path.exists("data/onui-beats.json"):
            with open("data/onui-beats.json", "r", encoding="utf-8") as f:
                songs = json.load(f)
    except Exception:
        pass
    return templates.TemplateResponse(request, "onui-beats.html", {"songs": songs})

from backend.routes.ai_services import load_voice_call_scenarios

@router.get("/voice-call")
def voice_call_page(request: Request):
    if redir := getattr(request.app.state, "redirect_if_unauthenticated", lambda r: None)(request):
        return redir
    scenarios = []
    try:
        scenarios = load_voice_call_scenarios()
    except Exception as e:
        logger.error(f"Failed to load scenarios for SSR: {e}")
    return templates.TemplateResponse(request, "voice-call.html", {"scenarios": scenarios})

@router.get("/onui-grammar")
def onui_grammar_page(request: Request):
    if redir := getattr(request.app.state, "redirect_if_unauthenticated", lambda r: None)(request):
        return redir
    return templates.TemplateResponse(request, "onui-grammar.html")

@router.get("/content-generation")
def content_generation_page(request: Request):
    if redir := getattr(request.app.state, "redirect_if_unauthenticated", lambda r: None)(request):
        return redir
    return templates.TemplateResponse(request, "content-generation.html")

@router.get("/daily-expression")
def daily_expression_page(request: Request):
    if redir := getattr(request.app.state, "redirect_if_unauthenticated", lambda r: None)(request):
        return redir
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
    if redir := getattr(request.app.state, "redirect_if_unauthenticated", lambda r: None)(request):
        return redir
    return templates.TemplateResponse(request, "learning-progress.html")

@router.get("/dashboard")
def dashboard_page(request: Request):
    if redir := getattr(request.app.state, "redirect_if_unauthenticated", lambda r: None)(request):
        return redir
    return templates.TemplateResponse(request, "dashboard.html")

@router.get("/privacy")
async def privacy_page(request: Request):
    return templates.TemplateResponse(request, "privacy.html")

@router.get("/sentence-evaluation")
def sentence_evaluation_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/speechpro-practice", status_code=301)
