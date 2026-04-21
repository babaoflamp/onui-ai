import os
import json
import logging
import sqlite3
import requests
import uuid
import wave
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.routes.deps import (
    get_current_user,
    ensure_wav_16k_mono,
    transcribe_with_vosk
)

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

class STTProxyRequest(BaseModel):
    base_url: str
    endpoint: str
    payload: dict

@router.post("/api/stt/proxy")
async def stt_proxy(request: STTProxyRequest, user: dict = Depends(get_current_user)):
    """Proxy STT JSON requests to avoid browser CORS."""
    base_url = (request.base_url or "").strip().rstrip("/")
    endpoint = (request.endpoint or "").strip()
    if not base_url or not endpoint:
        raise HTTPException(status_code=400, detail="base_url and endpoint are required")

    url = f"{base_url}{endpoint}"
    try:
        resp = requests.post(url, json=request.payload, timeout=30)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as e:
        logger.error(f"[STT_PROXY] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/stt/scorefile")
async def stt_scorefile(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    """Proxy SpeechPro scorefile (audio upload) request."""
    speechpro_url = os.getenv("MZTTS_API_URL") # Or get from app.state
    if not speechpro_url:
        raise HTTPException(status_code=500, detail="SpeechPro URL not configured")
    
    url = f"{speechpro_url}/scorefile"
    try:
        files = {"file": (file.filename, await file.read(), file.content_type)}
        resp = requests.post(url, files=files, timeout=30)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as e:
        logger.error(f"[STT_SCOREFILE] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/stt/whisper")
async def stt_whisper(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    client = request.app.state.openai_client
    if not client:
        raise HTTPException(status_code=500, detail="OpenAI client not initialized")
    
    tmp_path = Path(f"data/tmp/whisper_{uuid.uuid4().hex}.wav")
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(tmp_path, "wb") as f:
            f.write(await file.read())
        
        with open(tmp_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", file=audio_file, language="ko"
            )
        return {"text": transcript.text}
    finally:
        if tmp_path.exists(): os.remove(tmp_path)

@router.post("/api/stt/google")
async def stt_google(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    google_client = request.app.state.get_google_speech_client()
    if not google_client:
        raise HTTPException(status_code=500, detail="Google Speech client not initialized")
    
    tmp_path = Path(f"data/tmp/google_{uuid.uuid4().hex}.wav")
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    google_tmp = str(tmp_path) + ".g.wav"
    try:
        with open(tmp_path, "wb") as f:
            f.write(await file.read())
        
        ensure_wav_16k_mono(str(tmp_path), google_tmp)
        with open(google_tmp, "rb") as gfile:
            content = gfile.read()
            
        from google.cloud import speech
        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code="ko-KR"
        )
        response = google_client.recognize(config=config, audio=audio)
        text = response.results[0].alternatives[0].transcript if response.results else ""
        return {"text": text}
    finally:
        if tmp_path.exists(): os.remove(tmp_path)
        if os.path.exists(google_tmp): os.remove(google_tmp)

@router.post("/api/stt/vosk")
async def stt_vosk(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    vosk_model_path = os.getenv("VOSK_MODEL_PATH", "models/vosk-model-ko-0.22")
    tmp_path = Path(f"data/tmp/vosk_{uuid.uuid4().hex}.wav")
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    vosk_tmp = str(tmp_path) + ".v.wav"
    try:
        with open(tmp_path, "wb") as f:
            f.write(await file.read())
        ensure_wav_16k_mono(str(tmp_path), vosk_tmp)
        text = transcribe_with_vosk(vosk_tmp, vosk_model_path)
        return {"text": text}
    finally:
        if tmp_path.exists(): os.remove(tmp_path)
        if os.path.exists(vosk_tmp): os.remove(vosk_tmp)

@router.post("/api/voice-call/stt")
async def voice_call_stt(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    # Use whisper as default for voice call STT
    return await stt_whisper(request, file, user)
