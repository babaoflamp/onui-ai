import os
import tempfile
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.services.speechpro_service import (
    ScoreResult,
    call_speechpro_gtp,
    call_speechpro_model,
    call_speechpro_score,
    get_speechpro_url,
    set_speechpro_url,
    speechpro_full_workflow,
)


router = APIRouter()


class SpeechProFeedbackRequest(BaseModel):
    text: str
    score: dict


def _get_state(request: Request, name: str):
    return getattr(request.app.state, name, None)


@router.get("/speechpro-practice")
def speechpro_practice_page(request: Request):
    """SpeechPro 발음 정확도 평가"""
    templates = _get_state(request, "templates")
    if templates is None:
        return JSONResponse(status_code=500, content={"error": "Templates not configured"})
    return templates.TemplateResponse("speechpro-practice.html", {"request": request})


# ==========================================
# SpeechPro Evaluation Sentences
# ==========================================


@router.get("/api/speechpro/sentences")
async def get_speechpro_sentences(request: Request):
    """Get all SpeechPro evaluation sentences"""
    load_precomputed = _get_state(request, "load_speechpro_precomputed_sentences")
    if not callable(load_precomputed):
        return JSONResponse(status_code=500, content={"error": "SpeechPro sentences loader not configured"})
    try:
        precomputed = load_precomputed()
        return JSONResponse(content=precomputed)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to load speechpro sentences", "details": str(e)},
        )


@router.get("/api/speechpro/sentences/{sentence_id}")
async def get_speechpro_sentence(request: Request, sentence_id: int):
    """Get a specific SpeechPro evaluation sentence by ID"""
    load_precomputed = _get_state(request, "load_speechpro_precomputed_sentences")
    if not callable(load_precomputed):
        return JSONResponse(status_code=500, content={"error": "SpeechPro sentences loader not configured"})
    try:
        sentences = load_precomputed()
        sentence = next((s for s in sentences if s.get("id") == sentence_id), None)
        if sentence:
            return JSONResponse(content=sentence)
        return JSONResponse(status_code=404, content={"error": "Sentence not found"})
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to load speechpro sentence", "details": str(e)},
        )


@router.get("/api/speechpro/sentences/level/{level}")
async def get_speechpro_sentences_by_level(request: Request, level: str):
    """Get SpeechPro evaluation sentences by level (A1, A2, B1, etc.)"""
    load_precomputed = _get_state(request, "load_speechpro_precomputed_sentences")
    if not callable(load_precomputed):
        return JSONResponse(status_code=500, content={"error": "SpeechPro sentences loader not configured"})
    try:
        sentences = load_precomputed()
        filtered = [s for s in sentences if s.get("level") == level.upper()]
        return JSONResponse(content=filtered)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to load speechpro sentences", "details": str(e)},
        )


# ==========================================
# SpeechPro API
# ==========================================


@router.get("/api/speechpro/config")
async def speechpro_config():
    """SpeechPro API 설정 조회"""
    return JSONResponse(content={"url": get_speechpro_url(), "status": "configured"})


@router.post("/api/speechpro/config")
async def set_speechpro_config(data: dict = None):
    """SpeechPro API URL 설정"""
    try:
        if data is None:
            data = {}

        url = data.get("url", "").strip()
        if not url:
            return JSONResponse(status_code=400, content={"error": "url is required"})

        set_speechpro_url(url)
        return JSONResponse(content={"url": get_speechpro_url(), "status": "updated"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/api/speechpro/gtp")
async def speechpro_gtp(data: dict = None):
    """
    GTP (Grapheme-to-Phoneme) API
    한국어 텍스트를 음소로 변환합니다.

    Request: {"text": "안녕하세요"}
    Response: {"id": "...", "text": "...", "syll_ltrs": "...", "syll_phns": "..."}
    """
    try:
        if data is None:
            data = {}

        text = data.get("text", "").strip()
        if not text:
            return JSONResponse(status_code=400, content={"error": "text is required"})

        result = call_speechpro_gtp(text)
        return JSONResponse(content=result.to_dict())
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"GTP processing failed: {str(e)}"})


@router.post("/api/speechpro/model")
async def speechpro_model(data: dict = None):
    """
    Model API - FST 발음 모델 생성
    GTP 결과를 바탕으로 발음 평가 모델을 생성합니다.
    """
    try:
        if data is None:
            data = {}

        text = data.get("text", "").strip()
        syll_ltrs = data.get("syll_ltrs", "").strip()
        syll_phns = data.get("syll_phns", "").strip()

        if not all([text, syll_ltrs, syll_phns]):
            return JSONResponse(status_code=400, content={"error": "text, syll_ltrs, syll_phns are required"})

        result = call_speechpro_model(text, syll_ltrs, syll_phns)
        return JSONResponse(content=result.to_dict())
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Model processing failed: {str(e)}"})


@router.post("/api/speechpro/score")
async def speechpro_score(
    request: Request,
    text: str = Form(...),
    syll_ltrs: str = Form(...),
    syll_phns: str = Form(...),
    fst: str = Form(...),
    audio: UploadFile = File(...),
):
    """
    Score JSON API - 발음 평가
    사용자의 음성 데이터를 전송하여 발음 정확도를 평가합니다.
    """
    try:
        audio_content_raw = await audio.read()
        if not audio_content_raw:
            return JSONResponse(status_code=400, content={"error": "audio file is required"})

        convert_audio = _get_state(request, "convert_audio_bytes_to_wav16")
        if not callable(convert_audio):
            return JSONResponse(status_code=500, content={"error": "audio convert not configured"})

        try:
            audio_content = convert_audio(audio_content_raw)
        except Exception as conv_err:
            return JSONResponse(status_code=400, content={"error": f"audio convert failed: {conv_err}"})

        text = text.strip()
        if not all([text, syll_ltrs, syll_phns, fst]):
            return JSONResponse(
                status_code=400,
                content={"error": "text, syll_ltrs, syll_phns, fst are required"},
            )

        result = call_speechpro_score(text, syll_ltrs, syll_phns, fst, audio_content)
        return JSONResponse(content=result.to_dict())
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Score processing failed: {str(e)}"})


@router.post("/api/speechpro/evaluate")
async def speechpro_evaluate(
    request: Request,
    text: str = Form(...),
    audio: UploadFile = File(...),
    syll_ltrs: str = Form(None),
    syll_phns: str = Form(None),
    fst: str = Form(None),
    include_ai: str = Form("true"),
):
    """통합 발음 평가 API (프리셋 우선 + full workflow fallback)."""
    start_time = time.time()

    def _parse_bool(value: str, default: bool = True) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "y", "on")

    include_ai_feedback = _parse_bool(include_ai, True)

    logger = _get_state(request, "logger")
    if logger is None:
        import logging

        logger = logging.getLogger(__name__)

    model_backend = _get_state(request, "model_backend")
    ollama_model = _get_state(request, "ollama_model")
    gemini_model = _get_state(request, "gemini_model")
    openai_model = _get_state(request, "openai_model")
    stt_backend = _get_state(request, "stt_backend")
    stt_client = _get_state(request, "openai_client")
    app_tmp_dir = _get_state(request, "app_tmp_dir")

    convert_audio = _get_state(request, "convert_audio_bytes_to_wav16")
    find_preset = _get_state(request, "find_precomputed_sentence")
    generate_feedback = _get_state(request, "generate_pronunciation_feedback")

    if not callable(convert_audio) or not callable(find_preset) or not callable(generate_feedback):
        return JSONResponse(status_code=500, content={"error": "SpeechPro helpers not configured", "success": False})

    try:
        audio_content_raw = await audio.read()
        text = text.strip()

        if not text:
            return JSONResponse(status_code=400, content={"error": "text is required"})
        if not audio_content_raw:
            return JSONResponse(status_code=400, content={"error": "audio file is required"})

        try:
            audio_content = convert_audio(audio_content_raw)
        except Exception as conv_err:
            return JSONResponse(status_code=400, content={"error": f"audio convert failed: {conv_err}"})

        recognized_text = None
        if stt_backend == "openai" and stt_client:
            logger.info("[STT] backend=openai whisper-1 start")
            tmp_path = None
            try:
                tmp_dir = str(app_tmp_dir) if app_tmp_dir else None
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False, dir=tmp_dir) as tmp:
                    tmp.write(audio_content_raw)
                    tmp_path = tmp.name
                with open(tmp_path, "rb") as f:
                    transcript = stt_client.audio.transcriptions.create(
                        model="whisper-1",
                        file=f,
                        language="ko",
                    )
                recognized_text = (
                    getattr(transcript, "text", None)
                    or transcript.get("text")
                    if isinstance(transcript, dict)
                    else None
                )
                logger.info("[STT] backend=openai success=%s", bool(recognized_text))
            except Exception as stt_err:
                logger.warning("[STT] backend=openai failed: %s", stt_err)
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
        else:
            logger.info("[STT] skipped backend=%s client=%s", stt_backend, bool(stt_client))

        # 1) 요청에 사전 계산 정보가 함께 왔다면 그대로 사용
        pre_syll_ltrs = syll_ltrs.strip() if syll_ltrs else None
        pre_syll_phns = syll_phns.strip() if syll_phns else None
        pre_fst = fst.strip() if fst else None

        preset: Optional[Dict[str, Any]] = None
        if pre_syll_ltrs and pre_syll_phns and pre_fst:
            preset = {
                "sentenceKr": text,
                "syll_ltrs": pre_syll_ltrs,
                "syll_phns": pre_syll_phns,
                "fst": pre_fst,
                "source": "client-precomputed",
            }
        else:
            preset = find_preset(text)

        if preset and preset.get("fst"):
            # scorejson은 id 캐시 가능성이 있어 고정 id 반복 사용을 피함
            import uuid

            preset_id = str(preset.get("id") or "preset").strip() or "preset"
            request_id = f"preset_{preset_id}_{uuid.uuid4().hex[:8]}"

            gtp_dict = {
                "id": f"gtp_{request_id}",
                "text": text,
                "syll_ltrs": preset.get("syll_ltrs", ""),
                "syll_phns": preset.get("syll_phns", ""),
                "error_code": 0,
            }
            model_dict = {
                "id": f"model_{request_id}",
                "text": text,
                "syll_ltrs": preset.get("syll_ltrs", ""),
                "syll_phns": preset.get("syll_phns", ""),
                "fst": preset.get("fst", ""),
                "error_code": 0,
            }

            speechpro_start = time.time()
            score_result = call_speechpro_score(
                text=text,
                syll_ltrs=preset.get("syll_ltrs", ""),
                syll_phns=preset.get("syll_phns", ""),
                fst=preset.get("fst", ""),
                audio_data=audio_content,
                request_id=request_id,
            )
            speechpro_time = time.time() - speechpro_start

            if score_result.error_code != 0:
                raise RuntimeError(f"Score 오류: error_code={score_result.error_code}")

            ai_feedback = None
            ai_feedback_start = time.time()
            if include_ai_feedback and model_backend in ("ollama", "openai", "gemini"):
                try:
                    ai_feedback = await generate_feedback(text, score_result)
                except Exception as fb_err:
                    logger.warning("[Evaluate] AI feedback failed: %s", fb_err)
            ai_feedback_time = time.time() - ai_feedback_start

            elapsed_time = time.time() - start_time
            response_data = {
                "gtp": gtp_dict,
                "model": model_dict,
                "score": score_result.to_dict(),
                "overall_score": score_result.score,
                "success": True,
                "source": preset.get("source", "precomputed"),
                "evaluation_time": round(elapsed_time, 2),
                "speechpro_time": round(speechpro_time, 2),
                "ai_model": f"{model_backend}/{ollama_model if model_backend == 'ollama' else gemini_model if model_backend == 'gemini' else openai_model}",
                "ai_feedback_time": round(ai_feedback_time, 2) if ai_feedback else None,
            }
            if recognized_text:
                response_data["recognized_text"] = recognized_text
            if ai_feedback:
                response_data["ai_feedback"] = ai_feedback
            return JSONResponse(content=response_data)

        # 2) 프리셋이 없으면 기존 전체 워크플로우 수행
        result = speechpro_full_workflow(text, audio_content)
        if recognized_text:
            result["recognized_text"] = recognized_text
        if include_ai_feedback and result.get("success") and model_backend in ("ollama", "openai", "gemini"):
            try:
                score_dict = result.get("score") or {}
                score_result = ScoreResult(
                    score=float(score_dict.get("score", 0) or 0),
                    details=score_dict.get("details", {}),
                    error_code=int(score_dict.get("error_code", 0) or 0),
                )
                ai_feedback = await generate_feedback(text, score_result)
                if ai_feedback:
                    result["ai_feedback"] = ai_feedback
            except Exception as fb_err:
                logger.warning("[Evaluate] AI feedback failed (full workflow): %s", fb_err)

        return JSONResponse(content=result)

    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e), "success": False})
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e), "success": False})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Evaluation failed: {str(e)}", "success": False})


@router.post("/api/speechpro/feedback")
async def speechpro_feedback(request: Request, payload: SpeechProFeedbackRequest):
    """Generate AI feedback based on SpeechPro score result."""
    text = (payload.text or "").strip()
    score_dict = payload.score or {}
    if not text:
        return JSONResponse(status_code=400, content={"error": "text is required"})
    if not score_dict:
        return JSONResponse(status_code=400, content={"error": "score is required"})

    model_backend = _get_state(request, "model_backend")
    generate_feedback = _get_state(request, "generate_pronunciation_feedback")
    if not callable(generate_feedback):
        return JSONResponse(status_code=500, content={"error": "AI feedback generator not configured", "success": False})

    try:
        score_result = ScoreResult(
            score=float(score_dict.get("score", 0) or 0),
            details=score_dict.get("details", {}),
            error_code=int(score_dict.get("error_code", 0) or 0),
        )
        ai_feedback = None
        if model_backend in ("ollama", "openai", "gemini"):
            ai_feedback = await generate_feedback(text, score_result)
        return JSONResponse(content={"success": True, "ai_feedback": ai_feedback})
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"AI feedback failed: {str(e)}", "success": False},
        )

