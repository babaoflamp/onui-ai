#!/usr/bin/env python3
"""
Regenerate TTS cache for specific expressions.
Deletes old cache files and calls Gemini TTS with improved prompt/voice.
Usage: python3 scripts/regen_tts.py
"""
import os, sys, json, hashlib, base64, struct
from pathlib import Path

# Load .env from project root
project_root = Path(__file__).parent.parent
env_path = project_root / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

import requests

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
GEMINI_TTS_VOICE = os.getenv("GEMINI_TTS_VOICE", "Aoede")
TTS_CACHE_DIR = project_root / "data" / "tts_cache"

SENTENCES = [
    "벚꽃길을 같이 걸어요.",
    "이번 주말에 봄꽃 보러 갈까요?",
    "새해에도 건강하세요.",
    "따뜻한 봄이 기다려져요.",
    "가을 하늘이 참 맑아요.",
]


def cache_key(text: str) -> str:
    raw = f"gemini:{GEMINI_TTS_MODEL}:{GEMINI_TTS_VOICE}:{text}".encode("utf-8")
    return hashlib.md5(raw).hexdigest()


def pcm16_to_wav(pcm_data: bytes, sample_rate=24000, channels=1) -> bytes:
    bits = 16
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    data_size = len(pcm_data)
    header = (
        b"RIFF" + struct.pack("<I", 36 + data_size) +
        b"WAVE" + b"fmt " + struct.pack("<I", 16) +
        struct.pack("<HHIIHH", 1, channels, sample_rate, byte_rate, block_align, bits) +
        b"data" + struct.pack("<I", data_size)
    )
    return header + pcm_data


def amplify_pcm16(pcm_data: bytes, target_peak: float = 1.0) -> bytes:
    if not pcm_data:
        return pcm_data
    count = len(pcm_data) // 2
    samples = struct.unpack("<" + "h" * count, pcm_data)
    peak = max((abs(s) for s in samples), default=0)
    if peak == 0:
        return pcm_data
    gain = min(int(32767 * target_peak) / peak, 1.0)  # don't amplify if already loud
    if gain >= 1.0:
        return pcm_data
    # Only clamp down if over-peak; for regeneration just return as-is
    return pcm_data


def call_gemini_tts(text: str) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_TTS_MODEL}:generateContent?key={GEMINI_API_KEY}"

    # Match the app's default Gemini TTS voice so pre-generated files hit the same cache.
    payload = {
        "contents": [{"role": "user", "parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": GEMINI_TTS_VOICE}
                }
            }
        }
    }
    resp = requests.post(url, json=payload, timeout=60)
    if not resp.ok:
        raise RuntimeError(f"Gemini API {resp.status_code}: {resp.text[:500]}")

    result = resp.json()
    for cand in result.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data") or {}
            data = inline.get("data")
            mime = inline.get("mimeType") or inline.get("mime_type")
            if data:
                return {"audio_data": base64.b64decode(data), "content_type": mime or "audio/wav"}
    raise RuntimeError("No audio data in Gemini response")


def regen(text: str):
    key = cache_key(text)
    bin_path = TTS_CACHE_DIR / f"{key}.bin"
    json_path = TTS_CACHE_DIR / f"{key}.json"

    # Delete old cache
    for p in (bin_path, json_path):
        if p.exists():
            p.unlink()
            print(f"  deleted: {p.name}")

    # Generate new TTS
    print(f"  calling Gemini TTS...")
    result = call_gemini_tts(text)
    audio = result["audio_data"]
    content_type = result["content_type"]

    # Convert PCM16 → WAV if needed
    content_type_lower = content_type.lower()
    if content_type_lower.startswith("audio/l16") or content_type_lower.startswith("audio/pcm"):
        audio = pcm16_to_wav(audio)
        content_type = "audio/wav"

    # Save new cache
    TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    bin_path.write_bytes(audio)
    json_path.write_text(json.dumps({"content_type": content_type}), encoding="utf-8")
    print(f"  saved: {key}.bin ({len(audio)} bytes, {content_type})")


if __name__ == "__main__":
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    print(f"Model: {GEMINI_TTS_MODEL}\n")
    for sentence in SENTENCES:
        print(f"[{sentence}]")
        try:
            regen(sentence)
        except Exception as e:
            print(f"  ERROR: {e}")
        print()
    print("Done. Restart PM2 to clear in-memory TTS cache:")
    print("  pm2 restart onui-ai")
