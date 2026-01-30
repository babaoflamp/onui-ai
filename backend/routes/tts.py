import hashlib
import logging
import time
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel


router = APIRouter()


class TTSRequest(BaseModel):
    text: str
    speaker: int = 0
    tempo: float = 1.0
    pitch: float = 1.0
    gain: float = 1.0
    language_code: Optional[str] = None
    voice: Optional[str] = None


def _get_state(request: Request, name: str):
    return getattr(request.app.state, name, None)


@router.get("/api/tts/info")
async def get_tts_info(request: Request):
    """Get TTS server information"""
    tts_backend = _get_state(request, "tts_backend")
    if tts_backend == "openai":
        return JSONResponse(
            content={
                "backend": "openai",
                "model": _get_state(request, "openai_tts_model"),
                "voice": _get_state(request, "openai_tts_voice"),
                "format": _get_state(request, "openai_tts_format"),
            }
        )
    if tts_backend == "gemini":
        return JSONResponse(
            content={
                "backend": "gemini",
                "model": _get_state(request, "gemini_tts_model"),
                "format": _get_state(request, "gemini_tts_mime"),
            }
        )
    if tts_backend == "google":
        return JSONResponse(
            content={
                "backend": "google",
                "language": _get_state(request, "google_tts_language"),
                "voice": _get_state(request, "google_tts_voice"),
                "encoding": _get_state(request, "google_tts_audio_encoding"),
            }
        )

    get_mztts_server_info = _get_state(request, "get_mztts_server_info")
    if not callable(get_mztts_server_info):
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to get TTS server info", "details": "MzTTS info not configured"},
        )
    try:
        info = get_mztts_server_info()
        info["backend"] = "mztts"
        return JSONResponse(content=info)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to get TTS server info", "details": str(e)},
        )


@router.post("/api/tts/generate")
async def generate_tts(request: Request, payload: TTSRequest):
    """
    Generate Korean speech using selected TTS backend.
    Returns an audio file response (wav/mp3 depending on backend).
    """
    logger = _get_state(request, "logger") or logging.getLogger(__name__)
    logger.info(f"[API_CALL] endpoint={request.url.path} method={request.method} params={{'text': payload.text, 'speaker': payload.speaker, 'tempo': payload.tempo, 'pitch': payload.pitch, 'gain': payload.gain, 'language_code': payload.language_code, 'voice': payload.voice}}")
    tts_backend = _get_state(request, "tts_backend")

    try:
        text = (payload.text or "").strip()
        if not text:
            return JSONResponse(status_code=400, content={"error": "Invalid parameters", "details": "text is required"})

        filename_hash = hashlib.md5(text.encode("utf-8")).hexdigest()[:8]

        if tts_backend == "openai":
            client = _get_state(request, "openai_client")
            openai_api_key = _get_state(request, "openai_api_key")
            openai_model = _get_state(request, "openai_tts_model")
            openai_voice = _get_state(request, "openai_tts_voice")
            openai_format = _get_state(request, "openai_tts_format")
            if client is None or not openai_api_key:
                raise RuntimeError("OpenAI TTS not configured")
            response = client.audio.speech.create(
                model=openai_model,
                voice=openai_voice,
                input=text,
                response_format=openai_format,
            )
            audio_bytes = getattr(response, "content", None)
            if audio_bytes is None:
                audio_bytes = response.read() if hasattr(response, "read") else None
            if not audio_bytes:
                raise RuntimeError("No audio data received from OpenAI TTS")
            media_type = (
                "audio/wav"
                if openai_format == "wav"
                else "audio/mpeg"
                if openai_format == "mp3"
                else "application/octet-stream"
            )
            return Response(
                content=audio_bytes,
                media_type=media_type,
                headers={
                    "Content-Disposition": f'attachment; filename="tts_{filename_hash}.{openai_format}"'
                },
            )

        if tts_backend == "google":
            call_google = _get_state(request, "call_google_tts_api")
            google_lang = payload.language_code or _get_state(request, "google_tts_language")
            google_voice = payload.voice or _get_state(request, "google_tts_voice")
            if not callable(call_google):
                raise RuntimeError("Google TTS is not configured")

            result = call_google(
                text=text,
                language_code=google_lang,
                voice_name=google_voice,
                speaking_rate=payload.tempo,
                pitch=payload.pitch,
            )

            content_type = result.get("content_type") or "application/octet-stream"
            ext = "mp3" if content_type == "audio/mpeg" else "wav"
            return Response(
                content=result["audio_data"],
                media_type=content_type,
                headers={"Content-Disposition": f'attachment; filename="tts_{filename_hash}.{ext}"'},
            )

        if tts_backend == "gemini":
            gemini_model = _get_state(request, "gemini_tts_model")
            cache_key_fn = _get_state(request, "tts_cache_key")
            get_cache = _get_state(request, "get_tts_cache")
            set_cache = _get_state(request, "set_tts_cache")
            call_gemini = _get_state(request, "call_gemini_tts_api")
            amplify_pcm16 = _get_state(request, "amplify_pcm16")
            pcm16_to_wav = _get_state(request, "pcm16_to_wav")

            if not callable(cache_key_fn) or not callable(get_cache) or not callable(set_cache) or not callable(call_gemini):
                raise RuntimeError("Gemini TTS is not configured")

            start_total = time.perf_counter()
            cache_key = cache_key_fn(text, gemini_model, "gemini")
            cached = get_cache(cache_key)
            if cached:
                logger.info("[TTS] cache=hit text_len=%s", len(text))
                content_type = cached["content_type"]
                audio_data = cached["audio_data"]
                ext = "wav" if content_type in ("audio/wav", "audio/x-wav") else "bin"
                return Response(
                    content=audio_data,
                    media_type=content_type,
                    headers={
                        "Content-Disposition": f'attachment; filename="tts_{filename_hash}.{ext}"'
                    },
                )

            start_call = time.perf_counter()
            result = call_gemini(text=text)
            logger.info("[TTS] gemini_call_ms=%.1f", (time.perf_counter() - start_call) * 1000)

            content_type = result.get("content_type") or "application/octet-stream"
            audio_data = result["audio_data"]
            if content_type.startswith("audio/L16"):
                if callable(amplify_pcm16):
                    audio_data = amplify_pcm16(audio_data)
                if callable(pcm16_to_wav):
                    audio_data = pcm16_to_wav(audio_data, sample_rate=24000, channels=1)
                    content_type = "audio/wav"

            if content_type in ("audio/wav", "audio/x-wav"):
                ext = "wav"
            elif content_type in ("audio/mpeg", "audio/mp3"):
                ext = "mp3"
            else:
                ext = "bin"

            set_cache(cache_key, content_type, audio_data)
            logger.info(
                "[TTS] total_ms=%.1f cached=no bytes=%s",
                (time.perf_counter() - start_total) * 1000,
                len(audio_data),
            )
            return Response(
                content=audio_data,
                media_type=content_type,
                headers={
                    "Content-Disposition": f'attachment; filename="tts_{filename_hash}.{ext}"'
                },
            )

        # Default: MzTTS
        call_mztts = _get_state(request, "call_mztts_api")
        if not callable(call_mztts):
            raise RuntimeError("MzTTS is not configured")

        result = call_mztts(
            text=text,
            output_type="file",
            speaker=payload.speaker,
            tempo=payload.tempo,
            pitch=payload.pitch,
            gain=payload.gain,
        )
        return Response(
            content=result["audio_data"],
            media_type=result["content_type"],
            headers={"Content-Disposition": f'attachment; filename="tts_{filename_hash}.wav"'},
        )

    except Exception as e:
        logger.exception("TTS generation failed")
        return JSONResponse(
            status_code=500,
            content={"error": "TTS generation failed", "details": str(e)},
        )

