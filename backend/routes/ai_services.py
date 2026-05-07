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
    transcribe_with_vosk,
    parse_session_token,
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
    logger.info(f"[VoiceCall WS] Connection accepted for scenario: {scenario_id}")

    # Auth check via session cookie
    token = websocket.cookies.get("session_token", "")
    user_info = parse_session_token(token) if token else None
    if not user_info:
        logger.warning("[VoiceCall WS] Unauthenticated connection rejected")
        await websocket.send_json({"type": "error", "text": "로그인이 필요합니다."})
        await websocket.close()
        return

    # Credit check and consumption
    db_path = websocket.app.state.db_path
    credit_costs = websocket.app.state.credit_costs
    daily_credits = int(os.getenv("DAILY_CREDITS", "100"))
    credit = check_and_consume_credits(db_path, user_info["user_id"], credit_costs.get("voice", 5), daily_credits)
    if not credit["ok"]:
        logger.info(f"[VoiceCall WS] Insufficient credits for user {user_info['user_id']}")
        await websocket.send_json({"type": "error", "text": f"오늘의 크레딧이 부족합니다. 자정에 리셋됩니다. (남은 크레딧: {credit['remaining']})"})
        await websocket.close()
        return

    gemini_live_client = websocket.app.state.gemini_live_client
    gemini_api_key = os.getenv("GEMINI_API_KEY")

    if not gemini_api_key or not gemini_live_client:
        logger.error("[VoiceCall WS] GEMINI_API_KEY or gemini_live_client missing")
        await websocket.send_json({"type": "error", "text": "GEMINI_API_KEY not configured"})
        await websocket.close()
        return

    # Load scenario
    try:
        scenarios = load_voice_call_scenarios()
        scenario = next((s for s in scenarios if s["id"] == scenario_id), scenarios[0])
    except Exception as e:
        logger.error(f"[VoiceCall WS] Scenario load failed: {e}")
        await websocket.send_json({"type": "error", "text": f"Scenario load failed: {e}"})
        await websocket.close()
        return

    target_model = os.getenv("GEMINI_LIVE_MODEL", "gemini-2.5-flash-native-audio-latest")

    # native-audio (2.5) models support transcription + speech config + text greeting
    # 3.1 A2A model: no transcription, no speech config, no initial text input
    is_native_audio = "native-audio" in target_model

    # native-audio (2.5) models get a text [EXIT] marker we detect from output_transcription
    # non-native-audio (3.1) models TTS everything literally — no [EXIT] in spoken text;
    # instead we detect it from model_draft text (added below, stripped before preview send)
    if is_native_audio:
        exit_rules = """4. 대화를 완전히 끝낼 때는 자연스럽게 작별 인사를 하고 텍스트에 [EXIT]를 포함하세요.
5. 사용자가 먼저 작별 인사를 해도 정중하게 화답한 뒤 [EXIT]로 마무리하세요."""
    else:
        exit_rules = """4. 대화 목적이 완성되거나 자연스러운 마무리가 되면 "네, 감사합니다. 또 오세요!"라고 인사하고 텍스트 응답 마지막에 [EXIT]만 단독으로 추가하세요 (발화하지 마세요).
5. 사용자가 먼저 작별 인사를 하면 정중히 화답하고 같은 방식으로 마무리하세요."""

    system_prompt = f"""{scenario.get('system_prompt', '')}

규칙:
1. 반드시 한국어로만 짧게 대화하세요 (1-2문장).
2. 학습자가 충분히 연습할 수 있도록 대화를 리드하되, 목적(주문 완료, 진료 종료 등)이 달성되면 자연스럽게 작별 인사를 하세요.
3. 친절하고 격려하는 말투로 대화하세요.
{exit_rules}"""

    from google.genai.types import (
        LiveConnectConfig, SpeechConfig, VoiceConfig, PrebuiltVoiceConfig,
        AudioTranscriptionConfig, Blob,
    )

    config_kwargs = {"response_modalities": ["AUDIO"], "system_instruction": system_prompt}
    if is_native_audio:
        config_kwargs["speech_config"] = SpeechConfig(
            voice_config=VoiceConfig(prebuilt_voice_config=PrebuiltVoiceConfig(voice_name="Kore"))
        )
        config_kwargs["input_audio_transcription"] = AudioTranscriptionConfig()
        config_kwargs["output_audio_transcription"] = AudioTranscriptionConfig()

    live_config = LiveConnectConfig(**config_kwargs)

    try:
        logger.info(f"[VoiceCall WS] Connecting to Gemini Live API (Model: {target_model})...")
        async with gemini_live_client.aio.live.connect(
            model=target_model,
            config=live_config,
        ) as session:
            logger.info("[VoiceCall WS] Connected to Gemini Live API")
            await websocket.send_json({"type": "status", "text": "connected", "user_speaks_first": not is_native_audio})

            # Send initial greeting (text only supported on native-audio models)
            if is_native_audio:
                initial_msg = scenario.get("initial_message", "안녕하세요! 한국어로 대화해 봐요.")
                await session.send(input=initial_msg, end_of_turn=True)

            async def browser_to_gemini():
                """브라우저 PCM 오디오 및 제어 메시지 → Gemini Live"""
                try:
                    while True:
                        message = await websocket.receive()
                        if message["type"] == "websocket.disconnect":
                            logger.info("[VoiceCall WS] Browser disconnected")
                            break
                        if "bytes" in message:
                            data = message["bytes"]
                            if len(data) == 0:
                                await session.send_realtime_input(audio_stream_end=True)
                            else:
                                # Simple rate limiting for logging (Change to INFO to verify in logs)
                                if not hasattr(websocket.state, "byte_count"): websocket.state.byte_count = 0
                                websocket.state.byte_count += len(data)
                                if websocket.state.byte_count >= 32000: # Every ~1 second of audio
                                    logger.info(f"[VoiceCall WS] Received 1s of audio data ({len(data)} bytes chunk)")
                                    websocket.state.byte_count = 0

                                await session.send_realtime_input(
                                    audio=Blob(data=data, mime_type="audio/pcm;rate=16000")
                                )
                        elif "text" in message:
                            try:
                                data = json.loads(message["text"])
                                if data.get("type") == "end_call":
                                    logger.info("[VoiceCall WS] End call signal received")
                                    await session.send(input="대화를 마칠게요. 마무리 인사를 해줘.", end_of_turn=True)
                            except: pass
                except Exception as e:
                    logger.error(f"[VoiceCall WS] browser→gemini error: {e}")

            async def gemini_to_browser():
                """Gemini Live 응답 → 브라우저"""
                try:
                    while True:
                        async for response in session.receive():
                            if response.data:
                                try:
                                    # logger.debug(f"[VoiceCall WS] Sending {len(response.data)} bytes to browser")
                                    await websocket.send_bytes(response.data)
                                except RuntimeError:
                                    logger.info("[VoiceCall WS] Cannot send audio, websocket closed")
                                    return # Exit the entire task
                            
                            # Handle server_content (transcripts, etc.)
                            sc = response.server_content
                            if sc:
                                try:
                                    # 1. Try output_transcription (Final/Stable)
                                    if hasattr(sc, 'output_transcription') and sc.output_transcription and sc.output_transcription.text:
                                        t = sc.output_transcription.text.strip()

                                        # Check for exit marker
                                        if "[EXIT]" in t:
                                            t = t.replace("[EXIT]", "").strip()
                                            logger.info(f"[VoiceCall WS] AI Concluded conversation: {t}")
                                            await websocket.send_json({"type": "ai_transcript_final", "text": t})
                                            await websocket.send_json({"type": "call_concluded_by_ai"})
                                        else:
                                            logger.info(f"[VoiceCall WS] AI Transcript: {t}")
                                            await websocket.send_json({"type": "ai_transcript_final", "text": t})

                                    # 2. Try model_draft (Real-time preview + [EXIT] detection for 3.1)
                                    if hasattr(sc, 'model_draft') and sc.model_draft and sc.model_draft.parts:
                                        preview_parts = [part.text.strip() for part in sc.model_draft.parts if getattr(part, "text", None)]
                                        preview_text = " ".join(part for part in preview_parts if part).strip()
                                        if preview_text:
                                            has_exit = "[EXIT]" in preview_text
                                            preview_text = preview_text.replace("[EXIT]", "").strip()
                                            if preview_text:
                                                await websocket.send_json({"type": "ai_transcript_preview", "text": preview_text})
                                            if has_exit and not is_native_audio:
                                                logger.info("[VoiceCall WS] [EXIT] detected in model_draft (3.1 model)")
                                                await websocket.send_json({"type": "call_concluded_by_ai"})

                                    # 3. User input transcription
                                    if hasattr(sc, 'input_transcription') and sc.input_transcription and sc.input_transcription.text:
                                        t = sc.input_transcription.text.strip()
                                        logger.info(f"[VoiceCall WS] User Transcript: {t}")
                                        await websocket.send_json({"type": "user_transcript", "text": t})
                                    
                                    if hasattr(sc, 'turn_complete') and sc.turn_complete:
                                        logger.info("[VoiceCall WS] Turn complete")
                                        await websocket.send_json({"type": "turn_complete"})
                                except RuntimeError:
                                    logger.info("[VoiceCall WS] Cannot send JSON, websocket closed")
                                    return # Exit the entire task

                except WebSocketDisconnect:
                    logger.info("[VoiceCall WS] Gemini disconnected (WebSocketDisconnect)")
                except Exception as e:
                    logger.error(f"[VoiceCall WS] gemini→browser error: {e}")

            # Create tasks to run concurrently
            b2g_task = asyncio.create_task(browser_to_gemini())
            g2b_task = asyncio.create_task(gemini_to_browser())

            # Wait for either to finish (usually browser disconnect)
            done, pending = await asyncio.wait(
                [b2g_task, g2b_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel the remaining task
            for task in pending:
                task.cancel()
            
            # Allow tasks to clean up
            await asyncio.gather(*pending, return_exceptions=True)

    except Exception as e:
        logger.error(f"[VoiceCall WS] Exception: {e}", exc_info=True)
        try:
            await websocket.send_json({"type": "error", "text": str(e)})
        except Exception:
            pass
    finally:
        logger.info("[VoiceCall WS] Closing WebSocket")
        try:
            await websocket.close()
        except Exception:
            pass


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


def _ensure_correction_feedback(result: dict, user_message: str) -> dict:
    correction = result.get("correction")
    reply = str(result.get("reply") or "").strip()
    if isinstance(correction, dict):
        original = str(correction.get("original") or user_message).strip()
        corrected = str(correction.get("corrected") or original).strip()
        reason = str(correction.get("reason") or reply or "").strip()
        correction["original"] = original
        correction["corrected"] = corrected
        correction["reason"] = reason or "문장을 확인했고, 현재 표현도 자연스럽습니다."
        result["correction"] = correction
        if not result.get("reply"):
            result["reply"] = correction["reason"]
        return result

    result["correction"] = {
        "original": user_message,
        "corrected": user_message,
        "reason": reply or "문장을 확인했고, 현재 표현도 자연스럽습니다.",
    }
    return result

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
    daily_credits = int(os.getenv("DAILY_CREDITS", "100"))
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
    짧은 한국어 대화문과 주요 단어 3개를 JSON 형식으로 만들어주세요.

    대화문 규칙:
    - dialogue 배열은 반드시 정확히 4개 항목만 포함하세요.
    - 화자 순서는 반드시 1턴 지수(여자), 2턴 민준(남자), 3턴 지수(여자), 4턴 민준(남자)입니다.
    - speaker 값은 반드시 "지수" 또는 "민준"만 사용하세요.
    - 각 항목은 speaker, text, pronunciation 필드를 포함하세요.

    형식 예시: {{"dialogue": [{{"speaker": "지수", "text": "안녕하세요.", "pronunciation": "annyeonghaseyo."}}, {{"speaker": "민준", "text": "안녕하세요.", "pronunciation": "annyeonghaseyo."}}, {{"speaker": "지수", "text": "좋아요.", "pronunciation": "joayo."}}, {{"speaker": "민준", "text": "감사합니다.", "pronunciation": "gamsahamnida."}}], "vocabulary": ["단어1", "단어2", "단어3"]}}
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
                speakers = ["지수", "민준", "지수", "민준"]
                parsed["dialogue"] = dlg[:4]
                for idx, item in enumerate(parsed["dialogue"]):
                    if not isinstance(item, dict): continue
                    item["speaker"] = speakers[idx]
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
            f"당신은 한국어 선생님입니다. '{character_label}' 캐릭터 톤은 참고만 하고, 항상 한국어 선생님처럼 설명하세요. "
            "학습자의 한국어 문장을 자연스럽게 교정하고, 왜 그렇게 고치는지 짧고 분명하게 설명해 주세요. "
            "반드시 JSON 객체 하나만 반환하세요. 형식: "
            '{"reply":"short grammar explanation in English","correction":{"original":"original sentence","corrected":"corrected sentence","reason":"correction reason in English"}} '
            "reply와 correction.reason은 반드시 영어로 작성하세요. "
            "설명은 조사, 어순, 높임, 자연스러운 표현 중 핵심만 1~2문장으로 알려주세요. "
            "문장이 이미 자연스러우면 correction.corrected를 원문과 같게 두고, reply에는 왜 자연스러운지 영어로 설명하세요."
        )
    else:
        system_prompt = (
            f"당신은 한국어 선생님입니다. '{character_label}' 캐릭터 톤은 참고만 하고, 항상 한국어 학습자에게 설명하듯 답하세요. "
            "질문에 답할 때는 한국어 문법, 표현 차이, 자연스러운 말투를 짧고 분명하게 설명하세요. "
            "반드시 JSON 객체 하나만 반환하세요. 형식: "
            '{"reply":"short teacher explanation in English","correction":null} '
            "reply는 반드시 영어로 작성하고, 필요하면 짧은 한국어 예문을 포함하세요. "
            "학습자 문장에 분명한 오류가 있으면 correction 객체를 포함해도 됩니다."
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
    if mode == "correction":
        result = _ensure_correction_feedback(result, user_message)
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
async def translate_voice_text(request: Request):
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
    
    system_prompt = """당신은 한국인 친구입니다. 지금 학습자와 전화 통화를 하고 있습니다.
1. 친근하게 반말로 짧게 대답해 주세요.
2. 대화를 이어가기 위한 질문을 한 가지 해 주세요.
3. 응답은 JSON 형식이어야 합니다:
{
  "reply": "한국어 답변",
  "feedback": "학습자가 틀린 부분이 있다면 짧은 교정 (없으면 null)"
}
"""
    prompt = "전화를 먼저 걸어줘." if is_first else user_message
    contents = [{"role": "user", "parts": [{"text": system_prompt}]}]
    for h in history[-4:]:
        role = "user" if h["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": h["content"]}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})
    
    try:
        resp = request.app.state.gemini_client.models.generate_content(
            model=request.app.state.gemini_model, contents=contents
        )
        from backend.utils import parse_model_output
        parsed = parse_model_output(resp.text)
        return JSONResponse(content={"success": True, **(parsed or {"reply": resp.text})})
    except Exception as e:
        logger.error(f"[VOICE_CHAT] Error: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

# ============================================================================
# FluencyPro API (유창성 평가)
# ============================================================================

from backend.services.fluencypro_service import call_fluencypro_analyze, parse_fluency_output
from datetime import datetime

@router.post("/api/fluencypro/analyze")
async def fluency_analyze(request: Request, user: dict = Depends(get_current_user)):
    """음성 유창성 분석 - FluencyPro API (실제 연동)"""
    try:
        form_data = await request.form()
        text = form_data.get("text", "").strip()
        audio_file = form_data.get("audio")

        user_id = str(user["id"])

        if not text or not audio_file:
            return JSONResponse(
                status_code=400, content={"error": "text and audio are required"}
            )

        audio_data = await audio_file.read()
        logger.info(f"Calling FluencyPro API for text: {text[:50]}...")
        fluency_result = await call_fluencypro_analyze(text, audio_data)

        if not fluency_result.get("success"):
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": fluency_result.get("error", "유창성 분석에 실패했습니다."),
                },
            )

        parsed_output = parse_fluency_output(fluency_result.get("output", ""))
        response_data = {
            "success": True,
            "text": text,
            "total_reading_words": fluency_result.get("total_reading_words", 0),
            "total_correct_words": fluency_result.get("total_correct_words", 0),
            "total_duration": fluency_result.get("total_duration", 0.0),
            "reading_words_per_unit": fluency_result.get("reading_words_per_unit", 0.0),
            "correct_words_per_unit": fluency_result.get("correct_words_per_unit", 0.0),
            "accuracy_rate": fluency_result.get("accuracy_rate", 0.0),
            "recognized_text": parsed_output.get("recognized_text", ""),
            "pauses": parsed_output.get("pauses", []),
            "omitted_words": parsed_output.get("omitted_words", []),
            "error_words": parsed_output.get("error_words", []),
            "total_pauses": parsed_output.get("total_pauses", 0),
            "total_omissions": parsed_output.get("total_omissions", 0),
            "total_errors": parsed_output.get("total_errors", 0),
            "timestamp": datetime.now().isoformat(),
        }

        try:
            learning_service = getattr(request.app.state, "learning_service", None)
            if learning_service:
                learning_service.update_fluency_test(user_id)
        except Exception as e:
            logger.error(f"Failed to update fluency progress: {e}")

        logger.info(f"FluencyPro analysis completed: accuracy={response_data['accuracy_rate']}%")
        return JSONResponse(content=response_data)

    except Exception as e:
        logger.error(f"FluencyPro analyze error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"success": False, "error": f"서버 오류: {str(e)}"})


@router.post("/api/fluencypro/combined-feedback")
async def get_combined_feedback(request: Request, user: dict = Depends(get_current_user)):
    """FluencyPro와 SpeechPro 결과를 종합하여 AI 피드백 생성"""
    try:
        data = await request.json()
        text = data.get("text", "")
        fluency_data = data.get("fluency_data", {})
        speechpro_data = data.get("speechpro_data", {})

        if not text:
            return JSONResponse(status_code=400, content={"error": "text is required"})

        prompt = f"""
사용자가 발음한 한국어 문장에 대한 복합 피드백을 생성해주세요.

[사용자 발음 텍스트]
"{text}"

[FluencyPro 유창성 분석]
- 유창성 점수: {fluency_data.get("fluency_score", 0)}/100
- 발화 속도: {fluency_data.get("speech_rate", 0):.2f} 음절/초
- 조음 속도: {fluency_data.get("articulation_rate", 0):.2f} 음절/초
- 정확한 음절 비율: {fluency_data.get("correct_syllables_rate", 0):.1f}%
- 쉼표 개수: {fluency_data.get("pause_count", 0)}개

[SpeechPro 정확도 분석]
- 발음 정확도 점수: {speechpro_data.get("score", 0)}/100
- 발음 상세 피드백: {speechpro_data.get("feedback", "N/A")}

[생성 요청]
학습자에게 제공할 종합적인 피드백을 다음 형식으로 작성해주세요:

{{
  "overall_comment": "전체 평가를 한 문장으로 (50자 이내)",
  "strengths": ["강점 1", "강점 2"],
  "improvements": ["개선점 1", "개선점 2"],
  "tips": ["실습 팁 1", "실습 팁 2"],
  "encouragement": "격려 메시지 (한 문장)"
}}

음성과 발음이 모두 자연스러운 경우 칭찬하고, 특정 부분이 부자연스러운 경우 구체적으로 지적해주세요.
한국어 학습자이므로 친근하고 이해하기 쉬운 표현으로 작성하세요.
"""
        model_backend = getattr(request.app.state, "model_backend", "gemini")
        response_text = ""

        if model_backend == "gemini":
            gemini_client = request.app.state.gemini_client
            if not gemini_client:
                return JSONResponse(status_code=400, content={"error": "GEMINI_API_KEY not configured"})
            response = gemini_client.models.generate_content(
                model=request.app.state.gemini_model, contents=prompt
            )
            response_text = response.text
        elif model_backend == "ollama":
            ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
            ollama_model = request.app.state.ollama_model
            payload = {"model": ollama_model, "prompt": prompt}
            resp = requests.post(f"{ollama_url}/api/generate", json=payload, stream=True, timeout=60)
            for line in resp.iter_lines(decode_unicode=True):
                if not line: continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        response_text += obj.get("response", "") or obj.get("text", "")
                except Exception:
                    response_text += line
        else:
            return JSONResponse(status_code=501, content={"error": "Backend not configured"})

        from backend.utils import parse_model_output
        parsed_feedback = parse_model_output(response_text)

        if parsed_feedback:
            return JSONResponse(content=parsed_feedback)
        else:
            return JSONResponse(
                content={
                    "overall_comment": "좋은 연습이었습니다!",
                    "strengths": ["발음을 명확하게 했습니다"],
                    "improvements": ["더 자연스러운 속도로 연습해보세요"],
                    "tips": ["매일 꾸준히 연습하세요"],
                    "encouragement": "계속 화이팅!",
                }
            )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "combined-feedback failed", "details": str(e)})


@router.get("/api/fluencypro/metrics/{user_id}")
async def get_fluency_metrics(user_id: str, request: Request, user: dict = Depends(get_current_user)):
    """사용자 유창성 지표 조회"""
    try:
        db_path = getattr(request.app.state, "db_path", "data/users.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT id, nickname FROM users WHERE nickname = ? OR id = ?", (user_id, user_id))
        user_row = cursor.fetchone()

        if not user_row:
            conn.close()
            return JSONResponse(status_code=404, content={"error": f"User {user_id} not found"})

        actual_user_id = user_row[0]

        cursor.execute(
            """
            SELECT 
                COUNT(*) as total_practices,
                AVG(CAST(pronunciation_avg_score AS FLOAT)) as avg_fluency_score,
                MAX(CAST(pronunciation_avg_score AS FLOAT)) as best_fluency_score,
                MIN(CAST(pronunciation_avg_score AS FLOAT)) as worst_fluency_score
            FROM user_learning_progress
            WHERE user_id = ?
            """,
            (actual_user_id,),
        )
        metrics_row = cursor.fetchone()
        conn.close()

        total = metrics_row[0] or 0
        avg_score = round(metrics_row[1] or 0, 1)
        best_score = round(metrics_row[2] or 0, 1)
        worst_score = round(metrics_row[3] or 0, 1)

        if avg_score >= 90: grade = "A+ (매우 좋음)"
        elif avg_score >= 80: grade = "A (좋음)"
        elif avg_score >= 70: grade = "B (보통)"
        elif avg_score >= 60: grade = "C (개선필요)"
        else: grade = "D (많은 개선필요)"

        fluency_metrics = {
            "user_id": user_id,
            "total_practices": total,
            "average_fluency_score": avg_score,
            "best_fluency_score": best_score,
            "worst_fluency_score": worst_score,
            "fluency_grade": grade,
            "practice_frequency": "매일" if total >= 7 else "주 3-4회" if total >= 3 else "불규칙",
            "improvement_trend": "상승" if total >= 3 else "데이터 부족",
            "speech_rate_average": round(4.5 + (avg_score / 100), 2),
            "articulation_rate_average": round(4.2 + (avg_score / 120), 2),
            "accuracy_score": round(avg_score, 1),
            "last_practice": datetime.now().isoformat(),
        }
        return JSONResponse(content=fluency_metrics)

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

from backend.services.dalle_service import translate_korean_to_english_prompt

@router.post("/api/generate-image")
async def generate_image(request: Request, user: dict = Depends(get_current_user)):
    """AI 이미지 생성 API (OpenAI DALL-E 3)"""
    db_path = getattr(request.app.state, "db_path", "data/users.db")
    credit_costs = getattr(request.app.state, "credit_costs", {"image": 10})
    daily_credits = int(os.getenv("DAILY_CREDITS", "100"))
    
    _credit = check_and_consume_credits(db_path, user["id"], credit_costs.get("image", 10), daily_credits)
    if not _credit["ok"]:
        return JSONResponse(status_code=429, content={"success": False, "message": f"오늘의 크레딧이 부족합니다. 자정에 리셋됩니다. (남은 크레딧: {_credit['remaining']})", "remaining": _credit["remaining"]})

    try:
        data = await request.json()
        situation = data.get("situation", "").strip()
        style = data.get("style", "illustration")
        quality = data.get("quality", "standard")

        if not situation:
            return JSONResponse(status_code=400, content={"success": False, "message": "상황 설명을 입력해주세요."})

        logger.info(f"Image generation request - situation: {situation}, style: {style}, quality: {quality}")

        english_situation = await translate_korean_to_english_prompt(situation)
        enhanced_prompt = enhance_prompt_for_korean_learning(english_situation, style)

        result = await generate_image_dall_e(
            prompt=enhanced_prompt,
            size=os.getenv("DALLE_IMAGE_SIZE", "1024x1024"),
            quality=quality,
            style=os.getenv("DALLE_STYLE", "vivid"),
            save_locally=True,
        )

        if result["success"]:
            logger.info(f"Image generated successfully: {result.get('local_path', result.get('image_url'))}")
            return JSONResponse(
                {
                    "success": True,
                    "image_url": result.get("image_url"),
                    "local_path": result.get("local_path"),
                    "revised_prompt": result.get("revised_prompt", enhanced_prompt),
                    "prompt": enhanced_prompt,
                }
            )
        else:
            logger.error(f"Image generation failed: {result.get('error')}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": f"이미지 생성 실패: {result.get('error', 'Unknown error')}"},
            )
    except Exception as e:
        logger.error(f"Error generating image: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"success": False, "message": f"이미지 생성 중 오류 발생: {str(e)}"})

@router.post("/api/generate-music")
async def generate_music(request: Request, user: dict = Depends(get_current_user)):
    """AI 음악 생성 API (Placeholder)"""
    try:
        data = await request.json()
        mood = data.get("mood", "calm")
        duration = data.get("duration", 30)

        return JSONResponse(
            {
                "success": True,
                "music_url": "/static/placeholder-music.mp3",
                "description": f"{mood} 분위기의 {duration}초 배경음악",
                "message": "음악 생성 기능은 개발 중입니다. AI 음악 생성 API 연동이 필요합니다.",
            }
        )
    except Exception as e:
        logger.error(f"Error generating music: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"success": False, "message": f"음악 생성 중 오류 발생: {str(e)}"})
