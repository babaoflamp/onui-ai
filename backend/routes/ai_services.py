import os
import json
import logging
import sqlite3
import asyncio
import re
import time
import requests
import uuid
import threading
import tempfile
from typing import Optional, Dict, List
from pathlib import Path
from difflib import SequenceMatcher

from fastapi import APIRouter, Request, HTTPException, Depends, Form, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from backend.routes.deps import (
    get_current_user,
    get_user_credits,
    check_and_consume_credits,
    rag_get_settings,
    rag_search,
    ensure_rag_tables,
    load_json_data,
    romanize_korean,
    parse_model_output,
    list_ollama_models,
    ensure_wav_16k_mono,
    transcribe_with_vosk
)
from backend.services.dalle_service import (
    generate_image_dall_e,
    generate_image_gemini,
    enhance_prompt_for_korean_learning,
)

router = APIRouter()
logger = logging.getLogger("uvicorn.error")
WORD_IMAGE_CACHE_LOCK = threading.Lock()


def load_voice_call_scenarios() -> list[dict]:
    with open("data/voice-call.json", "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_json_payload(raw_text: str):
    if not raw_text:
        return None

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_text, re.IGNORECASE)
    candidates = []
    if fence:
        candidates.append(fence.group(1).strip())

    brace = re.search(r"(\{[\s\S]*\})", raw_text)
    if brace:
        candidates.append(brace.group(1).strip())

    bracket = re.search(r"(\[[\s\S]*\])", raw_text)
    if bracket:
        candidates.append(bracket.group(1).strip())

    candidates.append(raw_text.strip())

    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return None


@router.get("/api/voice-call/scenarios")
async def get_voice_call_scenarios():
    try:
        return {"success": True, "scenarios": load_voice_call_scenarios()}
    except Exception as e:
        logger.error(f"Failed to load voice-call scenarios: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"success": False, "message": "시나리오를 불러오지 못했습니다."})

@router.websocket("/ws/voice-call/{scenario_id}")
async def voice_call_live_ws(websocket: WebSocket, scenario_id: str):
    """Gemini Live API 실시간 오디오 스트리밍 WebSocket 엔드포인트"""
    await websocket.accept()

    gemini_live_client = websocket.app.state.gemini_live_client
    gemini_api_key = os.getenv("GEMINI_API_KEY")

    if not gemini_api_key or not gemini_live_client:
        await websocket.send_json({"type": "error", "text": "GEMINI_API_KEY not configured"})
        await websocket.close()
        return

    # Load scenario
    try:
        scenarios = load_voice_call_scenarios()
        scenario = next((s for s in scenarios if s["id"] == scenario_id), scenarios[0])
    except Exception as e:
        await websocket.send_json({"type": "error", "text": f"Scenario load failed: {e}"})
        await websocket.close()
        return

    system_prompt = f"""{scenario.get('system_prompt', '')}

규칙:
1. 반드시 한국어로만 짧게 대화하세요 (1-2문장).
2. 학습자가 자연스럽게 대답할 수 있도록 질문을 섞어주세요.
3. 친절하고 격려하는 말투로 대화하세요."""

    from google.genai.types import (
        LiveConnectConfig, SpeechConfig, VoiceConfig, PrebuiltVoiceConfig,
        AudioTranscriptionConfig,
    )
    live_config = LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=system_prompt,
        speech_config=SpeechConfig(
            voice_config=VoiceConfig(
                prebuilt_voice_config=PrebuiltVoiceConfig(voice_name="Kore")
            )
        ),
        input_audio_transcription=AudioTranscriptionConfig(),
        output_audio_transcription=AudioTranscriptionConfig(),
    )

    try:
        async with gemini_live_client.aio.live.connect(
            model="gemini-2.5-flash-native-audio-latest",
            config=live_config,
        ) as session:
            await websocket.send_json({"type": "status", "text": "connected"})

            # Send initial greeting
            initial_msg = scenario.get("initial_message", "안녕하세요! 한국어로 대화해 봐요.")
            await session.send(input=initial_msg, end_of_turn=True)

            async def browser_to_gemini():
                """브라우저 PCM 오디오 및 제어 메시지 → Gemini Live"""
                try:
                    while True:
                        message = await websocket.receive()
                        if message["type"] == "websocket.disconnect":
                            break
                        if "bytes" in message:
                            data = message["bytes"]
                            if len(data) == 0:
                                await session.send_realtime_input(audio_stream_end=True)
                            else:
                                from google.genai.types import Blob
                                await session.send_realtime_input(
                                    audio=Blob(data=data, mime_type="audio/pcm;rate=16000")
                                )
                        elif "text" in message:
                            try:
                                data = json.loads(message["text"])
                                if data.get("type") == "end_call":
                                    await session.send(input="대화를 마칠게요. 마무리 인사를 해줘.", end_of_turn=True)
                            except: pass
                except Exception: pass

            async def gemini_to_browser():
                """Gemini Live 응답 → 브라우저"""
                try:
                    async for response in session.receive():
                        if response.data:
                            await websocket.send_bytes(response.data)
                        sc = response.server_content
                        if sc:
                            if sc.input_transcription and sc.input_transcription.text:
                                await websocket.send_json({"type": "user_transcript", "text": sc.input_transcription.text.strip()})
                            if sc.output_transcription and sc.output_transcription.text:
                                await websocket.send_json({"type": "ai_transcript", "text": sc.output_transcription.text.strip()})
                            if sc.turn_complete:
                                await websocket.send_json({"type": "turn_complete"})
                except WebSocketDisconnect: pass
                except Exception: pass

            await asyncio.gather(browser_to_gemini(), gemini_to_browser())

    except WebSocketDisconnect: pass
    except Exception: pass
    finally:
        try: await websocket.close()
        except: pass

def _log_ai_content(
    request: Request, user_id: str, content_type: str, model_used: str, prompt: str, result: str
):
    """AI 생성 콘텐츠를 DB에 기록합니다."""
    db_path = request.app.state.db_path
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO ai_content_history (user_id, content_type, model_used, prompt, result) VALUES (?, ?, ?, ?, ?)",
            (str(user_id), content_type, model_used, prompt, result),
        )
        conn.commit()
        conn.close()

        # 맞춤형 교재/콘텐츠 생성 횟수를 학습 진도에 반영
        if str(user_id) != "anonymous":
            try:
                learning_service = request.app.state.learning_service
                learning_service.update_content_generated(str(user_id))
            except Exception as e:
                logger.error(f"Failed to update content generated progress: {e}")
    except Exception as e:
        logger.error(f"Failed to log AI content: {e}")

def _load_word_image_cache(cache_path: Path) -> dict:
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_word_image_cache(cache_path: Path, cache: dict) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(cache, ensure_ascii=True),
            encoding="utf-8",
        )
    except Exception:
        return

def _get_cached_word_image(cache_path: Path, key: str) -> Optional[Dict]:
    if not key:
        return None
    with WORD_IMAGE_CACHE_LOCK:
        cache = _load_word_image_cache(cache_path)
        return cache.get(key)

def _set_cached_word_image(cache_path: Path, key: str, url: str) -> None:
    if not key or not url:
        return
    with WORD_IMAGE_CACHE_LOCK:
        cache = _load_word_image_cache(cache_path)
        cache[key] = {"url": url, "updatedAt": int(time.time() * 1000)}
        _save_word_image_cache(cache_path, cache)

def _trim_history_messages(history: list, limit: int = 6) -> list[dict]:
    if not isinstance(history, list):
        return []
    cleaned: list[dict] = []
    for item in history[-limit:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            cleaned.append({"role": role, "content": content})
    return cleaned

def _format_history_for_prompt(history: list[dict]) -> str:
    if not history:
        return ""
    lines = []
    for item in history:
        speaker = "학습자" if item["role"] == "user" else "AI"
        lines.append(f"{speaker}: {item['content']}")
    return "\n".join(lines)

def _normalize_messenger_result(parsed: Optional[Dict], fallback_reply: str, user_message: str) -> dict:
    result = parsed if isinstance(parsed, dict) else {}

    correction_obj = result.get("correction")
    if not isinstance(correction_obj, dict):
        correction_obj = result if any(k in result for k in ("original", "corrected", "reason", "feedback")) else None

    normalized_correction = None
    if isinstance(correction_obj, dict):
        original = str(correction_obj.get("original") or user_message).strip()
        corrected = str(correction_obj.get("corrected") or correction_obj.get("rewrite") or "").strip()
        reason = str(correction_obj.get("reason") or correction_obj.get("feedback") or "").strip()
        if corrected and corrected != original:
            normalized_correction = {
                "original": original,
                "corrected": corrected,
                "reason": reason or "더 자연스러운 표현으로 수정했습니다.",
            }

    reply = str(result.get("reply") or fallback_reply or "").strip()
    if not reply:
        if normalized_correction:
            reply = normalized_correction["reason"]
        else:
            reply = "응답을 생성하지 못했습니다. 다시 시도해 주세요."

    return {"reply": reply, "correction": normalized_correction}

def _strip_code_fences(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()

def _extract_labeled_value(text: str, labels: list[str]) -> str:
    for label in labels:
        match = re.search(rf"(?:^|\n)\s*{label}\s*[:：]\s*(.+)", text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""

def _salvage_correction_result(raw_text: str, user_message: str) -> Optional[dict]:
    text = _strip_code_fences(raw_text)
    if not text:
        return None

    corrected = _extract_labeled_value(
        text,
        ["corrected", "correction", "rewrite", "교정문", "수정문", "자연스러운 표현", "고친 문장"],
    )
    reason = _extract_labeled_value(
        text,
        ["reason", "feedback", "explanation", "이유", "설명", "피드백"],
    )
    reply = _extract_labeled_value(
        text,
        ["reply", "response", "답변", "한줄 설명"],
    )

    if not corrected:
        lines = [line.strip("-* \t") for line in text.splitlines() if line.strip()]
        if lines:
            first_line = lines[0]
            if (
                first_line != user_message
                and len(first_line) <= 200
                and not first_line.startswith("{")
            ):
                corrected = first_line
                if len(lines) > 1 and not reason:
                    reason = " ".join(lines[1:]).strip()

    if corrected and corrected != user_message:
        return {
            "reply": reply or reason or "더 자연스러운 표현으로 고쳤어요.",
            "correction": {
                "original": user_message,
                "corrected": corrected,
                "reason": reason or "문장을 더 자연스럽고 올바르게 다듬었습니다.",
            },
        }
    return None

@router.post("/api/generate-content")
async def generate_content(
    request: Request,
    topic: str = Form(...),
    level: str = Form(...),
    model: str = Form(None),
    backend: str = Form(None),
    user: dict = Depends(get_current_user)
):
    db_path = request.app.state.db_path
    daily_credits = int(os.getenv("DAILY_CREDITS", "50"))
    credit_costs = request.app.state.credit_costs
    model_backend = request.app.state.model_backend
    romanize_mode = os.getenv("ROMANIZE_MODE", "force").lower()

    credit = check_and_consume_credits(db_path, user["id"], credit_costs["lesson"], daily_credits)
    if not credit["ok"]:
        return JSONResponse(status_code=429, content={"success": False, "message": f"오늘의 크레딧이 부족합니다. 자정에 리셋됩니다. (남은 크레딧: {credit['remaining']})", "remaining": credit["remaining"]})
    
    user_id = user["id"]

    # Level-specific guidance
    lvl = (level or "").strip()
    if lvl == "초급":
        level_guidance = "초급 학습자용으로 답변해주세요. 문장은 짧고 간단하게, 쉬운 어휘를 사용하고 각 문장에 대한 짧은 설명은 생략하세요."
    elif lvl == "중급":
        level_guidance = "중급 학습자용으로 답변해주세요. 문장은 자연스럽고 약간 복잡한 문장 구조를 포함할 수 있으며, 한두 개의 문법 포인트나 표현 설명을 포함하세요."
    elif lvl == "고급":
        level_guidance = "고급 학습자용으로 답변해주세요. 보다 풍부한 표현, 관용구, 뉘앙스 설명과 문화적 메모를 포함해 주세요."
    else:
        level_guidance = "요구된 레벨에 맞게 적절한 난이도로 작성해 주세요."

    prompt = f"""
    한국어 선생님입니다. 주제: '{topic}', 레벨: '{level}'. {level_guidance}
    짧은 한국어 대화문(3~4마디)과 주요 단어 3개를 JSON 형식으로 만들어주세요.
    형식 예시: {{"dialogue": [{{"speaker": "A", "text": "안녕", "pronunciation": "annyeong"}}], "vocabulary": ["단어1", "단어2", "단어3"]}}
    중요: 응답은 반드시 마지막에 하나의 JSON 객체만 포함된 코드 블럭(```json ... ```)으로 반환하세요.
    """

    selected_backend = backend or model_backend
    out = ""
    parsed = None

    if selected_backend == "gemini":
        gemini_client = request.app.state.gemini_client
        gemini_model = model or request.app.state.gemini_model
        if not gemini_client:
            return JSONResponse(status_code=500, content={"error": "Gemini client not initialized"})
        gen_resp = gemini_client.models.generate_content(model=gemini_model, contents=prompt)
        out = gen_resp.text
    elif selected_backend == "ollama":
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        use_model = model or request.app.state.ollama_model
        resp = requests.post(f"{ollama_url}/api/generate", json={"model": use_model, "prompt": prompt}, stream=True, timeout=30)
        for line in resp.iter_lines(decode_unicode=True):
            if line:
                try:
                    obj = json.loads(line)
                    out += obj.get("response", "")
                except: out += line
    elif selected_backend == "openai":
        openai_client = request.app.state.openai_client
        use_model = model or request.app.state.openai_model
        if not openai_client:
            return JSONResponse(status_code=500, content={"error": "OpenAI client not initialized"})
        response = openai_client.chat.completions.create(model=use_model, messages=[{"role": "user", "content": prompt}], temperature=0.7)
        out = response.choices[0].message.content.strip()
    else:
        return JSONResponse(status_code=501, content={"error": "Unknown backend"})

    parsed = parse_model_output(out)
    if parsed:
        try:
            dlg = parsed.get("dialogue")
            if isinstance(dlg, list):
                for item in dlg:
                    if not isinstance(item, dict): continue
                    item_text = item.get("text", "")
                    pron = item.get("pronunciation")
                    if romanize_mode == "force" or not pron or re.search(r"[\uac00-\ud7a3]", str(pron)):
                        pron = romanize_korean(item_text)
                    item["pronunciation"] = re.sub(r"\s+", " ", str(pron)).strip()
        except: pass
        _log_ai_content(request, user_id, "dialogue", selected_backend, prompt, json.dumps(parsed, ensure_ascii=False))
        return JSONResponse(content=parsed)

    _log_ai_content(request, user_id, "dialogue", selected_backend, prompt, out)
    return JSONResponse(content={"text": out})

@router.post("/api/gemini/image")
async def gemini_image(prompt: str = Form(...), save_locally: bool = Form(True), user: dict = Depends(get_current_user)):
    result = await generate_image_gemini(prompt, save_locally=save_locally)
    if not result.get("success"):
        fallback = await generate_image_dall_e(
            prompt=enhance_prompt_for_korean_learning(prompt, "illustration"),
            save_locally=save_locally
        )
        if fallback.get("success"):
            return JSONResponse(content=fallback)
        return JSONResponse(status_code=500, content=result)
    return JSONResponse(content=result)

@router.get("/api/word-images/cache")
async def get_word_image_cache(request: Request, key: str = None, user: dict = Depends(get_current_user)):
    if not key:
        return JSONResponse(status_code=400, content={"error": "key is required"})
    cache_path = Path(os.getenv("WORD_IMAGE_CACHE_PATH", "data/word_image_cache.json"))
    cached = _get_cached_word_image(cache_path, key)
    return JSONResponse(content={"cached": bool(cached), "entry": cached or {}})

@router.post("/api/word-images/cache")
async def set_word_image_cache(request: Request, user: dict = Depends(get_current_user)):
    try:
        data = await request.json()
    except: return JSONResponse(status_code=400, content={"error": "invalid json"})
    key = (data.get("key") or "").strip()
    url = (data.get("url") or "").strip()
    if not key or not url:
        return JSONResponse(status_code=400, content={"error": "key and url are required"})
    cache_path = Path(os.getenv("WORD_IMAGE_CACHE_PATH", "data/word_image_cache.json"))
    _set_cached_word_image(cache_path, key, url)
    return JSONResponse(content={"success": True})

@router.get("/api/ollama/models")
def get_ollama_models(request: Request, user: dict = Depends(get_current_user)):
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    try:
        models = list_ollama_models(ollama_url)
        return JSONResponse(content={"models": models})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.post("/api/ollama/test")
async def ollama_test(request: Request, prompt: str = Form(...), model: str = Form(None), user: dict = Depends(get_current_user)):
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    use_model = model or request.app.state.ollama_model
    try:
        resp = requests.post(f"{ollama_url}/api/generate", json={"model": use_model, "prompt": prompt}, stream=True, timeout=30)
        out = ""
        for line in resp.iter_lines(decode_unicode=True):
            if line:
                try:
                    obj = json.loads(line)
                    out += obj.get("response", "")
                except: out += line
        parsed = parse_model_output(out)
        return JSONResponse(content={"model": use_model, "parsed": parsed or out})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.post("/api/chat/test")
async def chat_test(request: Request, user: dict = Depends(get_current_user)):
    db_path = request.app.state.db_path
    credit_costs = request.app.state.credit_costs
    credit = check_and_consume_credits(db_path, user["id"], credit_costs["chat"])
    if not credit["ok"]:
        return JSONResponse(status_code=429, content={"success": False, "message": "Credits exhausted"})

    data = await request.json()
    prompt = data.get("prompt", "").strip()
    history = data.get("history", [])
    system_context = data.get("system_context", "")
    selected_backend = data.get("backend") or request.app.state.model_backend

    system_prompt = "당신은 한국어 학습 코치입니다." + (f"\n\n현재 학습 중인 교재 내용:\n{system_context}" if system_context else "")

    if selected_backend == "gemini":
        gemini_client = request.app.state.gemini_client
        contents = [{"role": "user", "parts": [{"text": system_prompt}]}, {"role": "model", "parts": [{"text": "알겠습니다!"}]}]
        for h in history[-10:]:
            contents.append({"role": "user" if h["role"] == "user" else "model", "parts": [{"text": h["content"]}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})
        resp = gemini_client.models.generate_content(model=request.app.state.gemini_model, contents=contents)
        return JSONResponse(content={"model": request.app.state.gemini_model, "text": resp.text})
    elif selected_backend == "openai":
        client = request.app.state.openai_client
        messages = [{"role": "system", "content": system_prompt}]
        for h in history[-10:]:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": prompt})
        completion = client.chat.completions.create(model=request.app.state.openai_model, messages=messages)
        return JSONResponse(content={"model": request.app.state.openai_model, "text": completion.choices[0].message.content})
    elif selected_backend == "ollama":
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        use_model = request.app.state.ollama_model
        resp = requests.post(f"{ollama_url}/api/generate", json={"model": use_model, "prompt": prompt}, stream=True, timeout=30)
        out = ""
        for line in resp.iter_lines(decode_unicode=True):
            if line:
                try: out += json.loads(line).get("response", "")
                except: out += line
        return JSONResponse(content={"model": use_model, "text": out})
    return JSONResponse(status_code=501, content={"error": "Backend not supported"})

@router.post("/api/fluency-check")
async def fluency_check(request: Request, user_text: str = Form(...), user_obj: dict = Depends(get_current_user)):
    user_id = str(user_obj["id"])
    prompt = f'사용자가 쓴 한국어 문장입니다: "{user_text}". 이 문장의 자연스러움을 100점 만점으로 평가하고 교정된 문장과 피드백을 JSON으로 주세요: {{"score": 85, "corrected": "...", "feedback": "..."}}'
    
    backend = request.app.state.model_backend
    out = ""
    if backend == "ollama":
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        resp = requests.post(f"{ollama_url}/api/generate", json={"model": request.app.state.ollama_model, "prompt": prompt}, stream=True, timeout=30)
        for line in resp.iter_lines(decode_unicode=True):
            if line:
                try: out += json.loads(line).get("response", "")
                except: out += line
    elif backend == "gemini":
        resp = request.app.state.gemini_client.models.generate_content(model=request.app.state.gemini_model, contents=prompt)
        out = resp.text
    elif backend == "openai":
        resp = request.app.state.openai_client.chat.completions.create(model=request.app.state.openai_model, messages=[{"role": "user", "content": prompt}])
        out = resp.choices[0].message.content
    
    parsed = parse_model_output(out)
    try: request.app.state.learning_service.update_fluency_test(user_id)
    except: pass
    return JSONResponse(content=parsed or {"text": out})

@router.post("/api/situational-content")
async def situational_content(request: Request, situation: str = Form(...), level: str = Form(...), model: str = Form(None), backend: str = Form(None), user: dict = Depends(get_current_user)):
    user_id = user["id"]
    prompt = f"상황: {situation}, 난이도: {level}. 한국어 학습용 컨텐츠(설명, 표현, 대화, 단어)를 JSON으로 생성하세요."
    selected_backend = backend or request.app.state.model_backend
    
    out = ""
    if selected_backend == "gemini":
        gemini_model = model or request.app.state.gemini_model
        resp = request.app.state.gemini_client.models.generate_content(model=gemini_model, contents=prompt)
        out = resp.text
    elif selected_backend == "ollama":
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        resp = requests.post(f"{ollama_url}/api/generate", json={"model": model or request.app.state.ollama_model, "prompt": prompt}, stream=True)
        for line in resp.iter_lines(decode_unicode=True):
            if line:
                try: out += json.loads(line).get("response", "")
                except: out += line
    
    parsed = parse_model_output(out)
    if parsed:
        _log_ai_content(request, user_id, "situational", selected_backend, prompt, json.dumps(parsed, ensure_ascii=False))
        return JSONResponse(content=parsed)
    return JSONResponse(content={"text": out})

@router.post("/api/pronunciation-check")
async def pronunciation_check(request: Request, target_text: str = Form(...), file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    tmp_dir = Path("data/tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = os.path.basename(file.filename or "upload").replace("..", "")
    file_location = tmp_dir / f"temp_{safe_filename}"
    
    try:
        with open(file_location, "wb") as buffer:
            shutil_copy = False # Placeholder for actual logic
            buffer.write(await file.read())

        stt_backend = request.app.state.stt_backend
        user_said = ""
        
        if stt_backend == "openai":
            with open(file_location, "rb") as f:
                transcript = request.app.state.openai_client.audio.transcriptions.create(model="whisper-1", file=f, language="ko")
                user_said = transcript.text
        elif stt_backend == "google":
            google_client = request.app.state.get_google_speech_client()
            if google_client:
                google_tmp = str(file_location) + ".g.wav"
                ensure_wav_16k_mono(str(file_location), google_tmp)
                with open(google_tmp, "rb") as gfile:
                    content = gfile.read()
                from google.cloud import speech
                audio = speech.RecognitionAudio(content=content)
                config = speech.RecognitionConfig(encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16, sample_rate_hertz=16000, language_code="ko-KR")
                response = google_client.recognize(config=config, audio=audio)
                if response.results:
                    user_said = response.results[0].alternatives[0].transcript
                os.remove(google_tmp)

        matcher = SequenceMatcher(None, target_text.replace(" ", ""), user_said.replace(" ", ""))
        similarity = matcher.ratio() * 100
        return {"user_said": user_said, "target_text": target_text, "score": round(similarity, 1), "feedback": "Good job!" if similarity > 80 else "Keep practicing!"}
    finally:
        if file_location.exists(): os.remove(file_location)

@router.post("/api/chatbot")
async def chatbot_api(request: Request, user: dict = Depends(get_current_user)):
    data = await request.json()
    user_message = data.get("message", "").strip()
    selected_model = data.get("model", "ollama").strip().lower()
    
    rag_context = ""
    db_path = request.app.state.db_path
    try:
        conn = sqlite3.connect(db_path)
        settings = rag_get_settings(conn)
        if settings.get("enabled"):
            hits = rag_search(conn, user_message, top_k=settings.get("top_k", 5))
            rag_context = "\n\n".join([f"[Source {i+1}] {h['content']}" for i, h in enumerate(hits)])
        conn.close()
    except: pass

    system_prompt = "당신은 한국어 교육 AI 튜터입니다."
    prompt = f"{system_prompt}\n\n{rag_context}\n\n질문: {user_message}"
    
    ai_response = ""
    if selected_model == "openai":
        resp = request.app.state.openai_client.chat.completions.create(model=request.app.state.openai_model, messages=[{"role": "user", "content": prompt}])
        ai_response = resp.choices[0].message.content
    elif selected_model == "gemini":
        resp = request.app.state.gemini_client.models.generate_content(model=request.app.state.gemini_model, contents=prompt)
        ai_response = resp.text
    else: # ollama
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        r = requests.post(f"{ollama_url}/api/generate", json={"model": request.app.state.ollama_model, "prompt": prompt, "stream": False})
        ai_response = r.json().get("response", "")
        
    return JSONResponse(content={"response": ai_response, "success": True})

@router.post("/api/messenger/chat")
async def messenger_chat_api(request: Request, user: dict = Depends(get_current_user)):
    data = await request.json()
    user_message = data.get("message", "").strip()
    character = data.get("character", "chaeon")
    mode = (data.get("mode") or "chat").strip().lower()
    history = _trim_history_messages(data.get("history", []))
    history_text = _format_history_for_prompt(history)
    character_names = {
        "chaeon": "Chaewon",
        "teacher": "Young-ja Teacher",
        "barista": "Minsu",
        "doctor": "Dr. Park",
    }
    character_label = character_names.get(character, character)

    if not user_message:
        return JSONResponse(status_code=400, content={"success": False, "message": "메시지가 비어 있습니다."})

    if mode == "correction":
        system_prompt = (
            f"당신은 한국어 문법 코치이자 대화 파트너 '{character_label}'입니다. "
            "학습자의 한국어 문장을 자연스럽게 교정해 주세요. "
            "반드시 JSON 객체 하나만 반환하세요. 형식: "
            '{"reply":"짧은 설명 또는 자연스러운 답장","correction":{"original":"원문","corrected":"교정문","reason":"교정 이유"}} '
            "correction.reason은 한국어로 한두 문장으로 쓰세요. "
            "문장이 이미 자연스러우면 correction은 null로 두고 reply에는 칭찬과 짧은 답장을 넣으세요."
        )
    else:
        system_prompt = (
            f"당신은 한국인 대화 파트너 '{character_label}'입니다. "
            "자연스럽고 짧게 한국어로 대화하세요. "
            "반드시 JSON 객체 하나만 반환하세요. 형식: "
            '{"reply":"짧은 대화 응답","correction":null} '
            "교정이 꼭 필요할 때만 correction 객체를 포함하세요."
        )

    prompt_parts = [system_prompt]
    if history_text:
        prompt_parts.append(f"이전 대화:\n{history_text}")
    prompt_parts.append(f"학습자 입력: {user_message}")
    prompt_parts.append("JSON 객체만 출력하세요.")
    prompt = "\n\n".join(prompt_parts)

    backend = request.app.state.model_backend
    response_text = ""
    try:
        if backend == "gemini":
            gemini_client = request.app.state.gemini_client
            if not gemini_client:
                raise RuntimeError("Gemini client not initialized")
            resp = gemini_client.models.generate_content(
                model=request.app.state.gemini_model,
                contents=prompt,
            )
            response_text = (resp.text or "").strip()
        elif backend == "openai":
            openai_client = request.app.state.openai_client
            if not openai_client:
                raise RuntimeError("OpenAI client not initialized")
            resp = openai_client.chat.completions.create(
                model=request.app.state.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": (f"이전 대화:\n{history_text}\n\n" if history_text else "") + f"학습자 입력: {user_message}\n\nJSON 객체만 출력하세요."},
                ],
                temperature=0.4,
            )
            response_text = (resp.choices[0].message.content or "").strip()
        elif backend == "ollama":
            ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
            resp = requests.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": request.app.state.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                },
                timeout=30,
            )
            resp.raise_for_status()
            response_text = str(resp.json().get("response", "") or "").strip()
        else:
            return JSONResponse(status_code=501, content={"success": False, "message": "Unknown backend"})
    except Exception as e:
        logger.error(f"Messenger chat generation failed: {e}", exc_info=True)
        return JSONResponse(
            status_code=502,
            content={"success": False, "message": "문법 응답 생성에 실패했습니다."},
        )

    parsed = parse_model_output(response_text)
    result = _normalize_messenger_result(parsed, response_text, user_message)
    if mode == "correction" and not result.get("correction"):
        salvaged = _salvage_correction_result(response_text, user_message)
        if salvaged:
            result = salvaged
    return JSONResponse(content={"success": True, **result})

@router.post("/api/textbook/quiz")
async def generate_textbook_quiz(request: Request, user: dict = Depends(get_current_user)):
    db_path = request.app.state.db_path
    credit_costs = request.app.state.credit_costs
    credit = check_and_consume_credits(db_path, user["id"], credit_costs["quiz"])
    if not credit["ok"]:
        return JSONResponse(status_code=429, content={"success": False, "message": "Credits exhausted"})

    body = await request.json()
    dialogue = body.get("dialogue", [])
    dialogue_text = "\n".join([f"{d.get('speaker','')}: {d.get('text','')}" for d in dialogue])
    try:
        prompt = (
            "다음 대화를 바탕으로 빈칸 채우기 퀴즈 4개를 만드세요.\n"
            "반드시 아래 JSON 형식만 반환하세요.\n"
            '{"questions":[{"display":"문장 ___ 나머지","blank_word":"정답","hint":"힌트"}]}\n'
            "display에는 반드시 밑줄 ___ 이 하나 포함되어야 합니다.\n"
            f"대화:\n{dialogue_text}"
        )

        resp = request.app.state.gemini_client.models.generate_content(
            model=request.app.state.gemini_model,
            contents=prompt,
        )
        parsed = _extract_json_payload(getattr(resp, "text", "") or "")
        if isinstance(parsed, list):
            parsed = {"questions": parsed}
        questions = parsed.get("questions") if isinstance(parsed, dict) else None
        if not isinstance(questions, list) or not questions:
            raise RuntimeError("Quiz model response did not contain valid questions")

        normalized = []
        for item in questions[:4]:
            if not isinstance(item, dict):
                continue
            display = str(item.get("display", "") or "").strip()
            blank_word = str(item.get("blank_word", "") or "").strip()
            hint = str(item.get("hint", "") or "").strip()
            if "___" not in display or not blank_word:
                continue
            normalized.append(
                {
                    "display": display,
                    "blank_word": blank_word,
                    "hint": hint,
                }
            )

        if not normalized:
            raise RuntimeError("Quiz questions could not be normalized")
        return JSONResponse(content={"success": True, "questions": normalized})
    except Exception as e:
        logger.error(f"Textbook quiz generation failed: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"success": False, "error": "Quiz generation failed"})

@router.post("/api/voice-call/translate")
async def translate_voice_text(request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    text = body.get("text", "")
    target = body.get("target", "en")
    prompt = f"Translate to {target}: {text}. Return only translation."
    resp = request.app.state.gemini_client.models.generate_content(model=request.app.state.gemini_model, contents=prompt)
    return {"translation": resp.text.strip()}

@router.post("/api/voice-call/chat")
async def voice_call_chat_api(request: Request, user: dict = Depends(get_current_user)):
    data = await request.json()
    user_message = data.get("message", "").strip()
    history = data.get("history", [])
    is_first = data.get("is_first", False)
    
    system_prompt = "한국어 학습용 AI 튜터입니다. 대화 응답과 피드백을 JSON으로 주세요."
    prompt = "첫 질문을 해주세요." if is_first else f"대화기록 바탕 응답: {user_message}"
    
    resp = request.app.state.gemini_client.models.generate_content(model=request.app.state.gemini_model, contents=f"{system_prompt}\n{prompt}")
    try:
        parsed = json.loads(re.search(r'\{[\s\S]*\}', resp.text).group())
        return JSONResponse(content={"success": True, **parsed})
    except:
        return JSONResponse(content={"success": True, "reply": resp.text, "feedback": ""})
