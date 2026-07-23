import json
import base64
import hashlib
import struct
import tempfile
import os
import requests
from typing import Optional, Dict
from pathlib import Path

from backend.config import load_settings
from backend.utils import ensure_wav_16k_mono

settings = load_settings()

GEMINI_TTS_MIME = settings.gemini_tts_mime
TTS_CACHE_DIR = settings.tts_cache_dir
TTS_CACHE_MAX = settings.tts_cache_max
APP_TMP_DIR = settings.app_tmp_dir
TTS_CACHE: Dict[str, Dict] = {}

def extract_gemini_audio(result: dict) -> dict:
    candidates = result.get("candidates") or []
    for cand in candidates:
        parts = cand.get("content", {}).get("parts", []) or []
        for part in parts:
            inline = part.get("inlineData") or part.get("inline_data") or {}
            data = inline.get("data")
            mime = inline.get("mimeType") or inline.get("mime_type")
            if data:
                return {
                    "audio_data": base64.b64decode(data),
                    "content_type": mime or GEMINI_TTS_MIME,
                }
    raise RuntimeError("Gemini TTS response did not include audio data")

def get_tts_cache_key(text: str, model: str, backend: str = "gemini", voice: str = "") -> str:
    raw = f"{backend}:{model}:{voice}:{text}".encode("utf-8")
    return hashlib.md5(raw).hexdigest()

def get_tts_cache(key: str) -> Optional[Dict]:
    cached = TTS_CACHE.get(key)
    if cached:
        return cached
    meta_path = TTS_CACHE_DIR / f"{key}.json"
    audio_path = TTS_CACHE_DIR / f"{key}.bin"
    if not meta_path.exists() or not audio_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        audio_bytes = audio_path.read_bytes()
        cached = {
            "content_type": meta.get("content_type") or "application/octet-stream",
            "audio_data": audio_bytes,
        }
        TTS_CACHE[key] = cached
        return cached
    except Exception:
        return None

def set_tts_cache(key: str, content_type: str, audio_data: bytes) -> None:
    if len(TTS_CACHE) >= TTS_CACHE_MAX:
        TTS_CACHE.clear()
    try:
        TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (TTS_CACHE_DIR / f"{key}.json").write_text(
            json.dumps({"content_type": content_type}, ensure_ascii=True),
            encoding="utf-8",
        )
        (TTS_CACHE_DIR / f"{key}.bin").write_bytes(audio_data)
        TTS_CACHE[key] = {"content_type": content_type, "audio_data": audio_data}
    except Exception:
        pass

def amplify_pcm16(pcm_data: bytes, target_peak: float = 1.0, max_gain: float = None) -> bytes:
    if not pcm_data:
        return pcm_data

    sample_count = len(pcm_data) // 2
    if sample_count == 0:
        return pcm_data

    samples = struct.unpack("<" + "h" * sample_count, pcm_data)
    peak = max((abs(s) for s in samples), default=0)
    if peak == 0:
        return pcm_data

    target = int(32767 * target_peak)
    gain = target / peak
    if max_gain is not None:
        gain = min(gain, max_gain)
    if gain <= 1.0:
        return pcm_data

    amplified = [max(-32768, min(32767, int(s * gain))) for s in samples]
    return struct.pack("<" + "h" * sample_count, *amplified)

def pcm16_to_wav(pcm_data: bytes, sample_rate: int = 24000, channels: int = 1) -> bytes:
    bits_per_sample = 16
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    data_size = len(pcm_data)
    riff_size = 36 + data_size

    header = b"".join(
        [
            b"RIFF",
            struct.pack("<I", riff_size),
            b"WAVE",
            b"fmt ",
            struct.pack("<I", 16),
            struct.pack("<H", 1),
            struct.pack("<H", channels),
            struct.pack("<I", sample_rate),
            struct.pack("<I", byte_rate),
            struct.pack("<H", block_align),
            struct.pack("<H", bits_per_sample),
            b"data",
            struct.pack("<I", data_size),
        ]
    )
    return header + pcm_data

def convert_audio_bytes_to_wav16(audio_bytes: bytes) -> bytes:
    if not audio_bytes: raise ValueError("audio bytes empty")
    with tempfile.TemporaryDirectory(dir=str(APP_TMP_DIR)) as tmpdir:
        src, dst = os.path.join(tmpdir, "in.bin"), os.path.join(tmpdir, "out.wav")
        with open(src, "wb") as f: f.write(audio_bytes)
        try: ensure_wav_16k_mono(src, dst)
        except Exception: raise RuntimeError("ffmpeg failed")
        with open(dst, "rb") as f: return f.read()

