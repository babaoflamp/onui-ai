import logging

logger = logging.getLogger(__name__)
import os
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, List
import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.utils import _get_state
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

AUDIO_UPLOAD_DIR = Path("uploads/audio")


def _ensure_audio_upload_dir() -> Path:
    AUDIO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return AUDIO_UPLOAD_DIR


def _cleanup_old_audio_uploads(upload_dir: Path, days: int = 30) -> None:
    """Delete audio/metadata files older than the retention window."""
    cutoff = time.time() - days * 86400
    for path in upload_dir.glob("*"):
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
        except Exception:
            continue


class SpeechProFeedbackRequest(BaseModel):
    text: str
    score: dict
    ui_lang: Optional[str] = "en"


def _redirect_if_unauthenticated(request: Request):
    redirect_func = getattr(request.app.state, "redirect_if_unauthenticated", None)
    if callable(redirect_func):
        return redirect_func(request)
    return None


@router.get("/speechpro-practice")
def speechpro_practice_page(request: Request):
    """SpeechPro 발음 정확도 평가"""
    logger.info(
        f"[API_CALL] endpoint={request.url.path} method={request.method} params={dict(request.query_params)}"
    )
    templates = _get_state(request, "templates")
    if templates is None:
        return JSONResponse(
            status_code=500, content={"error": "Templates not configured"}
        )
    return templates.TemplateResponse(request, "speechpro-practice.html")


# ==========================================
# SpeechPro Evaluation Sentences
# ==========================================


@router.get("/api/speechpro/sentences")
async def get_speechpro_sentences(
    request: Request, level: str = None, limit: int = None, offset: int = 0
):
    """Get SpeechPro evaluation sentences, optionally filtered by level (query param) and paginated."""
    load_precomputed = _get_state(request, "load_speechpro_precomputed_sentences")
    if not callable(load_precomputed):
        return JSONResponse(
            status_code=500,
            content={"error": "SpeechPro sentences loader not configured"},
        )
    try:
        precomputed = load_precomputed()
        if level and level.lower() != "all":
            # Support partial matching (e.g., "초급" matches "초급1", "초급2")
            precomputed = [s for s in precomputed if level in s.get("level", "")]

        total = len(precomputed)

        # Apply pagination if limit is specified
        if limit is not None:
            start = max(0, offset)
            end = start + max(1, limit)
            paginated_data = precomputed[start:end]
            return JSONResponse(
                content={
                    "data": paginated_data,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }
            )

        # Backwards compatibility: return list directly if no limit is specified
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
        return JSONResponse(
            status_code=500,
            content={"error": "SpeechPro sentences loader not configured"},
        )
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
        return JSONResponse(
            status_code=500,
            content={"error": "SpeechPro sentences loader not configured"},
        )
    try:
        sentences = load_precomputed()
        if level.lower() == "all":
            filtered = sentences
        else:
            # Support partial matching and case-insensitive/upper for level
            target = level.upper()
            filtered = [s for s in sentences if target in s.get("level", "").upper()]
        return JSONResponse(content=filtered)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to load speechpro sentences", "details": str(e)},
        )


@router.get("/api/speechpro/precomputed")
async def get_speechpro_precomputed(request: Request, text: str):
    """Return precomputed syllables/FST for a given sentence text."""
    get_or_build_precomputed = _get_state(
        request, "get_or_build_speechpro_precomputed_sentence"
    )
    if not callable(get_or_build_precomputed):
        return JSONResponse(
            status_code=500,
            content={"error": "Precomputed sentence finder not configured"},
        )
    target = (text or "").strip()
    if not target:
        return JSONResponse(status_code=400, content={"error": "text is required"})
    try:
        preset = get_or_build_precomputed(target)
        if not preset:
            return JSONResponse(content={"found": False, "text": target})
        return JSONResponse(
            content={
                "found": True,
                "text": target,
                "syll_ltrs": preset.get("syll_ltrs", ""),
                "syll_phns": preset.get("syll_phns", ""),
                "fst": preset.get("fst", ""),
                "source": preset.get("source", "precomputed"),
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to get precomputed sentence", "details": str(e)},
        )


# ==========================================
# SpeechPro API
# ==========================================


@router.get("/api/speechpro/config")
async def speechpro_config():
    """SpeechPro API 설정 조회"""
    return JSONResponse(content={"url": get_speechpro_url(), "status": "configured"})


@router.post("/api/speechpro/config")
async def set_speechpro_config(request: Request, data: dict = None):
    """SpeechPro API URL 설정 (관리자 전용)"""
    require_admin = _get_state(request, "require_admin")
    if callable(require_admin):
        try:
            require_admin(request)
        except Exception as e:
            return JSONResponse(status_code=403, content={"error": str(e)})
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
        return JSONResponse(
            status_code=500, content={"error": f"GTP processing failed: {str(e)}"}
        )


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
            return JSONResponse(
                status_code=400,
                content={"error": "text, syll_ltrs, syll_phns are required"},
            )

        result = call_speechpro_model(text, syll_ltrs, syll_phns)
        return JSONResponse(content=result.to_dict())
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except RuntimeError as e:
        return JSONResponse(status_code=503, content={"error": str(e)})
    except Exception as e:
        return JSONResponse(
            status_code=500, content={"error": f"Model processing failed: {str(e)}"}
        )


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
    logger.info(
        f"[API_CALL] endpoint={request.url.path} method={request.method} params={{'text': text, 'syll_ltrs': syll_ltrs, 'syll_phns': syll_phns, 'fst': fst, 'audio_filename': audio.filename}}"
    )
    try:
        audio_content_raw = await audio.read()
        if not audio_content_raw:
            return JSONResponse(
                status_code=400, content={"error": "audio file is required"}
            )

        convert_audio = _get_state(request, "convert_audio_bytes_to_wav16")
        if not callable(convert_audio):
            return JSONResponse(
                status_code=500, content={"error": "audio convert not configured"}
            )

        try:
            audio_content = convert_audio(audio_content_raw)
        except Exception as conv_err:
            return JSONResponse(
                status_code=400, content={"error": f"audio convert failed: {conv_err}"}
            )

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
        return JSONResponse(
            status_code=500, content={"error": f"Score processing failed: {str(e)}"}
        )


@router.post("/api/speechpro/evaluate")
async def speechpro_evaluate(
    request: Request,
    text: str = Form(...),
    audio: UploadFile = File(...),
    syll_ltrs: str = Form(None),
    syll_phns: str = Form(None),
    fst: str = Form(None),
    include_ai: str = Form("true"),
    fast_mode: str = Form("false"),
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
    fast_mode_enabled = _parse_bool(fast_mode, False)

    logger = _get_state(request, "logger")
    if logger is None:
        import logging

        logger = logging.getLogger(__name__)

    model_backend = _get_state(request, "model_backend")
    ollama_model = _get_state(request, "ollama_model")
    gemini_model = _get_state(request, "gemini_model")
    openai_model = _get_state(request, "openai_model")
    stt_client = _get_state(request, "openai_client")
    app_tmp_dir = _get_state(request, "app_tmp_dir")
    google_speech_available = _get_state(request, "google_speech_available")
    get_google_speech_client = _get_state(request, "get_google_speech_client")
    google_speech_module = _get_state(request, "google_speech_module")

    convert_audio = _get_state(request, "convert_audio_bytes_to_wav16")
    find_preset = _get_state(request, "find_precomputed_sentence")
    get_or_build_precomputed = _get_state(
        request, "get_or_build_speechpro_precomputed_sentence"
    )
    generate_feedback = _get_state(request, "generate_pronunciation_feedback")

    if not callable(convert_audio) or not callable(generate_feedback):
        return JSONResponse(
            status_code=500,
            content={"error": "SpeechPro helpers not configured", "success": False},
        )

    try:
        upload_dir = _ensure_audio_upload_dir()
        if not fast_mode_enabled:
            _cleanup_old_audio_uploads(upload_dir, days=30)

        audio_content_raw = await audio.read()
        text = text.strip()

        if not text:
            return JSONResponse(status_code=400, content={"error": "text is required"})
        if not audio_content_raw:
            return JSONResponse(
                status_code=400, content={"error": "audio file is required"}
            )

        saved_audio_path = None
        saved_meta_path = None
        if not fast_mode_enabled:
            try:
                ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
                ext = os.path.splitext(audio.filename or "")[1].lower()
                if not ext or len(ext) > 6 or not ext.startswith("."):
                    ext = ".wav"
                safe_name = f"{ts}_{uuid.uuid4().hex}{ext}"
                saved_audio_path = upload_dir / safe_name
                with open(saved_audio_path, "wb") as f:
                    f.write(audio_content_raw)
            except Exception as save_err:
                saved_audio_path = None
                saved_meta_path = None
                if logger:
                    logger.warning("[SpeechPro] failed to persist upload: %s", save_err)

        try:
            audio_content = convert_audio(audio_content_raw)
        except Exception as conv_err:
            return JSONResponse(
                status_code=400, content={"error": f"audio convert failed: {conv_err}"}
            )

        recognized_text = None

        # 1) OpenAI Whisper
        if stt_client and not fast_mode_enabled:
            logger.info("[STT] backend=openai whisper-1 start")
            tmp_path = None
            try:
                tmp_dir = str(app_tmp_dir) if app_tmp_dir else None
                with tempfile.NamedTemporaryFile(
                    suffix=".wav", delete=False, dir=tmp_dir
                ) as tmp:
                    tmp.write(audio_content_raw)
                    tmp_path = tmp.name
                with open(tmp_path, "rb") as f:
                    transcript = stt_client.audio.transcriptions.create(
                        model="whisper-1",
                        file=f,
                        language="ko",
                    )
                recognized_text = (
                    getattr(transcript, "text", None) or transcript.get("text")
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

        # 2) Google STT fallback
        if (
            recognized_text is None
            and not fast_mode_enabled
            and google_speech_available
            and callable(get_google_speech_client)
            and google_speech_module
        ):
            try:
                google_client = get_google_speech_client()
            except Exception as stt_err:
                logger.warning("[STT] backend=google client init failed: %s", stt_err)
                google_client = None

            if google_client:
                try:
                    audio = google_speech_module.RecognitionAudio(content=audio_content)
                    config = google_speech_module.RecognitionConfig(
                        encoding=google_speech_module.RecognitionConfig.AudioEncoding.LINEAR16,
                        sample_rate_hertz=16000,
                        language_code="ko-KR",
                        max_alternatives=1,
                    )
                    response = google_client.recognize(config=config, audio=audio)
                    for result in response.results:
                        if result.alternatives:
                            recognized_text = result.alternatives[0].transcript
                            break
                    logger.info(
                        "[STT] backend=google success=%s", bool(recognized_text)
                    )
                except Exception as stt_err:
                    logger.warning("[STT] backend=google failed: %s", stt_err)
            else:
                logger.info("[STT] backend=google skipped (no client)")

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
            if callable(get_or_build_precomputed):
                preset = get_or_build_precomputed(text)
            elif callable(find_preset):
                preset = find_preset(text)

        if preset and preset.get("fst"):
            # scorejson은 id 캐시 가능성이 있어 고정 id 반복 사용을 피함

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
            _score_text = text
            _score_syll_ltrs = preset.get("syll_ltrs", "")
            _score_syll_phns = preset.get("syll_phns", "")
            _score_fst = preset.get("fst", "")
            _score_audio = audio_content
            _score_rid = request_id
            score_result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: call_speechpro_score(
                    text=_score_text,
                    syll_ltrs=_score_syll_ltrs,
                    syll_phns=_score_syll_phns,
                    fst=_score_fst,
                    audio_data=_score_audio,
                    request_id=_score_rid,
                ),
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

            if not fast_mode_enabled:
                try:
                    if saved_audio_path:
                        saved_meta_path = saved_audio_path.with_suffix(".json")
                        meta = {
                            "created_at": datetime.utcnow().isoformat() + "Z",
                            "text": text,
                            "recognized_text": recognized_text,
                            "saved_audio": str(saved_audio_path),
                            "include_ai_feedback": include_ai_feedback,
                            "ai_feedback_present": bool(ai_feedback),
                            "overall_score": response_data.get("overall_score"),
                            "success": True,
                            "source": response_data.get("source"),
                            "request_id": response_data.get("model", {}).get("id"),
                        }
                        with open(saved_meta_path, "w", encoding="utf-8") as mf:
                            import json

                            json.dump(meta, mf, ensure_ascii=False, indent=2)
                    if saved_audio_path:
                        response_data["saved_audio_path"] = str(saved_audio_path)
                    if saved_meta_path:
                        response_data["metadata_path"] = str(saved_meta_path)
                except Exception as meta_err:
                    if logger:
                        logger.warning("[SpeechPro] failed to write metadata: %s", meta_err)

            # ------------------------------------------------------------------
            # LMS: 성적 자동 저장 (preset path) — 로그인 사용자만, 실패 무시
            # ------------------------------------------------------------------
            try:
                require_auth = _get_state(request, "require_authenticated_user")
                if callable(require_auth):
                    lms_user = require_auth(request)
                    db_path = _get_state(request, "db_path")
                    if lms_user and db_path:
                        import sqlite3 as _sqlite3
                        from datetime import datetime as _dt, timezone as _tz

                        _now = _dt.now(_tz.utc).strftime("%Y-%m-%d %H:%M:%S")
                        _score_val = float(response_data.get("overall_score") or 0)
                        _score_dict = response_data.get("score") or {}
                        _details = _score_dict.get("details") or {}
                        _fluency = _details.get("fluency") or {}
                        _accuracy = float(_score_dict.get("accuracy_percentage") or 0)
                        _completeness = float(
                            _score_dict.get("completeness_percentage") or 0
                        )
                        _fluency_acc = float(
                            _fluency.get("correct_syllable_count") or 0
                        )
                        _sentence_id = str(preset_id) if preset_id else "unknown"
                        _conn = _sqlite3.connect(db_path)
                        _cur = _conn.cursor()
                        _cur.execute(
                            "SELECT id, score_best, attempt_count FROM sentence_scores "
                            "WHERE user_id = ? AND sentence_id = ?",
                            (lms_user["id"], _sentence_id),
                        )
                        _row = _cur.fetchone()
                        if _row is None:
                            _cur.execute(
                                """
                                INSERT INTO sentence_scores (
                                    user_id, sentence_id, sentence_text, level,
                                    score_first, score_best, score_latest,
                                    accuracy_first, accuracy_best, accuracy_latest,
                                    completeness_latest, fluency_accuracy_latest,
                                    attempt_count, term_id,
                                    last_attempted_at, created_at
                                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,'2026-1',?,?)
                                """,
                                (
                                    lms_user["id"],
                                    _sentence_id,
                                    text,
                                    "",
                                    _score_val,
                                    _score_val,
                                    _score_val,
                                    _accuracy,
                                    _accuracy,
                                    _accuracy,
                                    _completeness,
                                    _fluency_acc,
                                    _now,
                                    _now,
                                ),
                            )
                        else:
                            _new_best = max(_row[1] or 0, _score_val)
                            _cur.execute(
                                """
                                UPDATE sentence_scores SET
                                    score_best = ?, score_latest = ?,
                                    accuracy_best = MAX(accuracy_best, ?),
                                    accuracy_latest = ?,
                                    completeness_latest = ?,
                                    fluency_accuracy_latest = ?,
                                    attempt_count = ?,
                                    last_attempted_at = ?
                                WHERE user_id = ? AND sentence_id = ?
                                """,
                                (
                                    _new_best,
                                    _score_val,
                                    _accuracy,
                                    _accuracy,
                                    _completeness,
                                    _fluency_acc,
                                    (_row[2] or 1) + 1,
                                    _now,
                                    lms_user["id"],
                                    _sentence_id,
                                ),
                            )
                        # 추가: 음성 녹음 기록 저장
                        _cur.execute(
                            "INSERT INTO user_voice_recordings (user_id, sentence_id, file_path, score) VALUES (?, ?, ?, ?)",
                            (
                                str(lms_user["id"]),
                                str(_sentence_id),
                                str(saved_audio_path) if saved_audio_path else "",
                                float(_score_val),
                            ),
                        )
                        _conn.commit()
                        _conn.close()
            except Exception:
                pass  # LMS 저장 실패는 평가 응답에 영향 없음
            # ------------------------------------------------------------------

            return JSONResponse(content=response_data)

        # 2) 프리셋이 없으면 기존 전체 워크플로우 수행
        result = speechpro_full_workflow(text, audio_content)
        if recognized_text:
            result["recognized_text"] = recognized_text
        if (
            include_ai_feedback
            and result.get("success")
            and model_backend in ("ollama", "openai", "gemini")
        ):
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
                logger.warning(
                    "[Evaluate] AI feedback failed (full workflow): %s", fb_err
                )

        if not fast_mode_enabled:
            try:
                if saved_audio_path:
                    saved_meta_path = saved_audio_path.with_suffix(".json")
                    meta = {
                        "created_at": datetime.utcnow().isoformat() + "Z",
                        "text": text,
                        "recognized_text": recognized_text,
                        "saved_audio": str(saved_audio_path),
                        "include_ai_feedback": include_ai_feedback,
                        "ai_feedback_present": bool(result.get("ai_feedback")),
                        "overall_score": result.get("overall_score"),
                        "success": bool(result.get("success")),
                        "source": result.get("source"),
                        "request_id": result.get("model", {}).get("id")
                        or result.get("score", {}).get("id"),
                    }
                    with open(saved_meta_path, "w", encoding="utf-8") as mf:
                        import json

                        json.dump(meta, mf, ensure_ascii=False, indent=2)
                if saved_audio_path:
                    result["saved_audio_path"] = str(saved_audio_path)
                if saved_meta_path:
                    result["metadata_path"] = str(saved_meta_path)
            except Exception as meta_err:
                if logger:
                    logger.warning("[SpeechPro] failed to write metadata: %s", meta_err)

        # ------------------------------------------------------------------
        # LMS: 성적 자동 저장 (full_workflow path) — 로그인 사용자만, 실패 무시
        # ------------------------------------------------------------------
        try:
            require_auth = _get_state(request, "require_authenticated_user")
            if (
                callable(require_auth)
                and result.get("success")
                and result.get("overall_score")
            ):
                lms_user = require_auth(request)
                db_path = _get_state(request, "db_path")
                if lms_user and db_path:
                    import sqlite3 as _sqlite3
                    from datetime import datetime as _dt, timezone as _tz

                    _now = _dt.now(_tz.utc).strftime("%Y-%m-%d %H:%M:%S")
                    _score_val = float(result.get("overall_score") or 0)
                    _score_dict = result.get("score") or {}
                    _details = _score_dict.get("details") or {}
                    _fluency = _details.get("fluency") or {}
                    _accuracy = float(_score_dict.get("accuracy_percentage") or 0)
                    _completeness = float(
                        _score_dict.get("completeness_percentage") or 0
                    )
                    _conn = _sqlite3.connect(db_path)
                    _cur = _conn.cursor()
                    _cur.execute(
                        "SELECT id, score_best, attempt_count FROM sentence_scores "
                        "WHERE user_id = ? AND sentence_id = 'full_workflow'",
                        (lms_user["id"],),
                    )
                    _row = _cur.fetchone()
                    if _row is None:
                        _cur.execute(
                            """
                            INSERT INTO sentence_scores (
                                user_id, sentence_id, sentence_text, level,
                                score_first, score_best, score_latest,
                                accuracy_first, accuracy_best, accuracy_latest,
                                completeness_latest, fluency_accuracy_latest,
                                attempt_count, term_id,
                                last_attempted_at, created_at
                            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,'2026-1',?,?)
                            """,
                            (
                                lms_user["id"],
                                "full_workflow",
                                text,
                                "",
                                _score_val,
                                _score_val,
                                _score_val,
                                _accuracy,
                                _accuracy,
                                _accuracy,
                                _completeness,
                                0,
                                _now,
                                _now,
                            ),
                        )
                    else:
                        _new_best = max(_row[1] or 0, _score_val)
                        _cur.execute(
                            """
                            UPDATE sentence_scores SET
                                score_best = ?, score_latest = ?,
                                accuracy_best = MAX(accuracy_best, ?),
                                accuracy_latest = ?,
                                completeness_latest = ?,
                                attempt_count = ?,
                                last_attempted_at = ?
                            WHERE user_id = ? AND sentence_id = 'full_workflow'
                            """,
                            (
                                _new_best,
                                _score_val,
                                _accuracy,
                                _accuracy,
                                _completeness,
                                (_row[2] or 1) + 1,
                                _now,
                                lms_user["id"],
                            ),
                        )
                    # 추가: 음성 녹음 기록 저장
                    _cur.execute(
                        "INSERT INTO user_voice_recordings (user_id, sentence_id, file_path, score) VALUES (?, ?, ?, ?)",
                        (
                            str(lms_user["id"]),
                            "full_workflow",
                            str(saved_audio_path) if saved_audio_path else "",
                            float(_score_val),
                        ),
                    )
                    _conn.commit()
                    _conn.close()
        except Exception:
            pass  # LMS 저장 실패는 평가 응답에 영향 없음
        # ------------------------------------------------------------------

        return JSONResponse(content=result)

    except ValueError as e:
        return JSONResponse(
            status_code=400, content={"error": str(e), "success": False}
        )
    except RuntimeError as e:
        return JSONResponse(
            status_code=503, content={"error": str(e), "success": False}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Evaluation failed: {str(e)}", "success": False},
        )


@router.post("/api/speechpro/feedback")
async def speechpro_feedback(request: Request, payload: SpeechProFeedbackRequest):
    """Generate AI feedback based on SpeechPro score result."""
    text = (payload.text or "").strip()
    score_dict = payload.score or {}
    ui_lang = payload.ui_lang or "en"
    if not text:
        return JSONResponse(status_code=400, content={"error": "text is required"})
    if not score_dict:
        return JSONResponse(status_code=400, content={"error": "score is required"})

    model_backend = _get_state(request, "model_backend")
    generate_feedback = _get_state(request, "generate_pronunciation_feedback")
    if not callable(generate_feedback):
        return JSONResponse(
            status_code=500,
            content={"error": "AI feedback generator not configured", "success": False},
        )

    try:
        score_result = ScoreResult(
            score=float(score_dict.get("score", 0) or 0),
            details=score_dict.get("details", {}),
            error_code=int(score_dict.get("error_code", 0) or 0),
        )
        ai_feedback = None
        if model_backend in ("ollama", "openai", "gemini"):
            ai_feedback = await generate_feedback(text, score_result, ui_lang=ui_lang)
        return JSONResponse(content={"success": True, "ai_feedback": ai_feedback})
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"AI feedback failed: {str(e)}", "success": False},
        )


@router.post("/api/speechpro/batch-evaluate")
async def speechpro_batch_evaluate(
    request: Request,
    files: List[UploadFile] = File(...),
    text_map: str = Form(""),
    include_ai_feedback: bool = Form(False),
):
    """다량의 음성 파일을 배치로 평가"""

    def _parse_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}

    include_ai_feedback_flag = _parse_bool(include_ai_feedback, False)

    # 텍스트 매핑 파싱
    # text_map 확장: 파일별 text, syll_ltrs, syll_phns, fst 지원
    preset_lookup: Dict[str, Dict[str, str]] = {}
    if text_map:
        try:
            import json

            parsed = json.loads(text_map)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        fname = (item.get("filename") or "").strip()
                        txt = (item.get("text") or "").strip()
                        syll_ltrs = (item.get("syll_ltrs") or "").strip()
                        syll_phns = (item.get("syll_phns") or "").strip()
                        fst = (item.get("fst") or "").strip()
                        if fname and txt:
                            preset_lookup[fname] = {
                                "text": txt,
                                "syll_ltrs": syll_ltrs,
                                "syll_phns": syll_phns,
                                "fst": fst,
                            }
            elif isinstance(parsed, dict):
                for fname, val in parsed.items():
                    if fname and val:
                        if isinstance(val, dict):
                            preset_lookup[str(fname)] = {
                                "text": val.get("text", ""),
                                "syll_ltrs": val.get("syll_ltrs", ""),
                                "syll_phns": val.get("syll_phns", ""),
                                "fst": val.get("fst", ""),
                            }
                        else:
                            preset_lookup[str(fname)] = {
                                "text": str(val),
                                "syll_ltrs": "",
                                "syll_phns": "",
                                "fst": "",
                            }
        except Exception:
            return JSONResponse(
                status_code=400, content={"error": "text_map must be valid JSON"}
            )

    if not files:
        return JSONResponse(status_code=400, content={"error": "files are required"})

    max_files = 3
    if len(files) > max_files:
        return JSONResponse(
            status_code=400,
            content={"error": f"too many files (demo limit {max_files})"},
        )

    max_size_bytes = 5 * 1024 * 1024  # 5MB per file
    max_total_bytes = 50 * 1024 * 1024  # 50MB overall guard
    total_bytes = 0
    allowed_mimes = {
        "audio/wav",
        "audio/webm",
        "audio/mpeg",
        "audio/mp3",
        "audio/ogg",
        "audio/x-wav",
    }
    allowed_exts = {".wav", ".webm", ".mp3", ".ogg", ".mpeg"}
    results = []
    success_count = 0

    generate_feedback = _get_state(request, "generate_pronunciation_feedback")
    model_backend = _get_state(request, "model_backend")

    import logging

    logger = logging.getLogger("batch-evaluate")
    for upload in files:
        filename = upload.filename or "unnamed"
        entry: Dict[str, Any] = {"filename": filename}

        try:
            audio_bytes = await upload.read()
            logger.info(
                f"[BATCH] 파일 업로드: {filename}, 크기: {len(audio_bytes) if audio_bytes else 0} bytes"
            )
            if not audio_bytes:
                entry.update({"success": False, "error": "empty file"})
                logger.error(f"[BATCH] 파일 비어있음: {filename}")
                results.append(entry)
                continue

            if len(audio_bytes) > max_size_bytes:
                entry.update({"success": False, "error": "file too large (max 5MB)"})
                logger.error(f"[BATCH] 파일 용량 초과: {filename}")
                results.append(entry)
                continue

            total_bytes += len(audio_bytes)
            if total_bytes > max_total_bytes:
                entry.update(
                    {"success": False, "error": "total upload size exceeds 50MB"}
                )
                logger.error(f"[BATCH] 전체 업로드 용량 초과: {filename}")
                results.append(entry)
                continue

            mime_ok = (upload.content_type or "").split(";")[0].strip() in allowed_mimes
            ext_ok = any(filename.lower().endswith(ext) for ext in allowed_exts)
            if not (mime_ok or ext_ok):
                entry.update({"success": False, "error": "unsupported audio format"})
                logger.error(
                    f"[BATCH] 지원하지 않는 포맷: {filename}, content_type={upload.content_type}"
                )
                results.append(entry)
                continue

            # 파일별 프리셋 정보 추출
            preset_info = preset_lookup.get(filename, {})
            text = preset_info.get("text", "").strip()
            syll_ltrs = preset_info.get("syll_ltrs", "").strip()
            syll_phns = preset_info.get("syll_phns", "").strip()
            fst = preset_info.get("fst", "").strip()
            logger.info(
                f"[BATCH] 평가 문장: {text} (파일: {filename}), syll_ltrs: {syll_ltrs}, syll_phns: {syll_phns}, fst: {fst}"
            )
            if not text:
                entry.update(
                    {"success": False, "error": "text is required for each file"}
                )
                logger.error(f"[BATCH] 문장 미입력: {filename}")
                results.append(entry)
                continue

            # 프리셋 정보가 모두 있으면 call_speechpro_score 사용, 아니면 전체 워크플로우
            loop = asyncio.get_event_loop()
            if syll_ltrs and syll_phns and fst:
                from backend.services.speechpro_service import call_speechpro_score

                def run_score():
                    return call_speechpro_score(
                        text=text,
                        syll_ltrs=syll_ltrs,
                        syll_phns=syll_phns,
                        fst=fst,
                        audio_data=audio_bytes,
                        request_id=None,
                    ).to_dict()

                with ThreadPoolExecutor() as executor:
                    workflow_result = await loop.run_in_executor(executor, run_score)
                logger.info(
                    f"[BATCH] call_speechpro_score 결과: {filename}, 결과: {workflow_result}"
                )
            else:
                with ThreadPoolExecutor() as executor:
                    workflow_result = await loop.run_in_executor(
                        executor, speechpro_full_workflow, text, audio_bytes
                    )
                logger.info(
                    f"[BATCH] 워크플로우 결과: {filename}, 결과: {workflow_result}"
                )
            entry.update(
                {
                    "success": bool(workflow_result.get("success", True)),
                    "overall_score": workflow_result.get("overall_score", 0),
                    "score": workflow_result.get("score", {}),
                    "text": text,
                    "syll_ltrs": syll_ltrs,
                    "syll_phns": syll_phns,
                    "fst": fst,
                }
            )

            if (
                include_ai_feedback_flag
                and entry["success"]
                and callable(generate_feedback)
                and model_backend in ("ollama", "openai", "gemini")
            ):
                try:
                    score_dict = entry.get("score") or {}
                    score_result = ScoreResult(
                        score=float(score_dict.get("score", 0) or 0),
                        details=score_dict.get("details", {}),
                        error_code=int(score_dict.get("error_code", 0) or 0),
                    )
                    ai_feedback = await generate_feedback(text, score_result)
                    if ai_feedback:
                        entry["ai_feedback"] = ai_feedback
                    logger.info(f"[BATCH] AI 피드백 생성 성공: {filename}")
                except Exception as fb_err:
                    entry["ai_feedback_error"] = str(fb_err)
                    logger.error(
                        f"[BATCH] AI 피드백 생성 실패: {filename}, 에러: {fb_err}"
                    )

            success_count += 1 if entry.get("success") else 0

        except ValueError as ve:
            entry.update({"success": False, "error": f"Invalid input: {str(ve)}"})
            logger.error(f"[BATCH] 입력 값 오류: {filename}, 에러: {ve}")
        except RuntimeError as re:
            entry.update({"success": False, "error": f"API call failed: {str(re)}"})
            logger.error(f"[BATCH] API 호출 실패: {filename}, 에러: {re}")
        except Exception as e:
            import traceback

            error_detail = f"{str(e)}\n{traceback.format_exc()}"
            print(f"[BATCH_ERROR] File: {filename}, Error: {error_detail}")
            logger.error(f"[BATCH] 처리 실패: {filename}, 에러: {error_detail}")
            entry.update({"success": False, "error": f"Processing failed: {str(e)}"})

        results.append(entry)

    return JSONResponse(
        content={
            "items": results,
            "success": success_count == len(results),
            "processed": len(results),
            "succeeded": success_count,
            "failed": len(results) - success_count,
        }
    )
