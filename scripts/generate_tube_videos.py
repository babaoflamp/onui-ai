#!/usr/bin/env python3
"""
OnuiTube 영상 생성 스크립트
poster 이미지 + TTS 음성 → 자막과 완전히 동기화된 9:16 mp4 생성
"""
import os
import json
import subprocess
import tempfile
import sys
import argparse
import base64
import re
import struct
import time
from pathlib import Path

import requests

# 경로 설정 (스크립트 위치와 무관하게 프로젝트 루트 기준)
ROOT = Path(__file__).parent.parent
TRANSCRIPT_FILE = ROOT / "data/onui-tube-transcripts.json"
TUBE_JSON_FILE  = ROOT / "data/onui-tube.json"
POSTER_DIR      = ROOT / "static/images/tube"
VIDEO_DIR       = ROOT / "static/video"

DEFAULT_VIDEOS_TO_GENERATE = [
    "self_introduction",
    "cafe_ordering_basic",
    "asking_directions_intl",
    "korean_culture_adv",
    "convenience_store_basic",
    "daily_routines_basic",
    "hospital_visit_intl",
    "shopping_clothes_intl",
    "traditional_market_adv",
    "business_meeting_adv",
]


def load_catalog() -> dict:
    with open(TUBE_JSON_FILE, encoding="utf-8") as f:
        return {video["id"]: video for video in json.load(f)}


def load_catalog_list() -> list[dict]:
    with open(TUBE_JSON_FILE, encoding="utf-8") as f:
        return json.load(f)


def resolve_poster(video_id: str, video_meta: dict | None = None) -> Path:
    poster_url = (video_meta or {}).get("poster_url", "")
    if poster_url.startswith("/static/"):
        poster = ROOT / poster_url.split("?", 1)[0].lstrip("/")
        if poster.exists():
            return poster

    jpg = POSTER_DIR / f"{video_id}.jpg"
    if jpg.exists():
        return jpg
    return POSTER_DIR / f"{video_id}.png"


def get_korean_sentence(line: dict) -> str:
    return " ".join(w["label"] for w in line["words"])


def run(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if result.returncode != 0:
        print(f"  [ERROR] {' '.join(str(c) for c in cmd[:4])}")
        print(result.stderr[-400:] if result.stderr else "")
        raise RuntimeError(f"Command failed: {cmd[0]}")
    return result


def get_audio_duration(path: Path) -> float:
    r = run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)])
    return float(r.stdout.strip())


def round_time(value: float) -> float:
    return round(value + 1e-9, 2)


def read_env_value(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value

    env_file = ROOT / ".env"
    if not env_file.exists():
        return None

    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        if key.strip() == name:
            return raw_value.strip().strip('"').strip("'")
    return None


def pcm16_to_wav(pcm_data: bytes, sample_rate: int = 24000, channels: int = 1) -> bytes:
    bits_per_sample = 16
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    data_size = len(pcm_data)

    return b"".join(
        [
            b"RIFF",
            struct.pack("<I", 36 + data_size),
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
    ) + pcm_data


def extract_gemini_audio(response_json: dict) -> tuple[bytes, str]:
    for candidate in response_json.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data") or {}
            data = inline.get("data")
            if not data:
                continue
            mime_type = inline.get("mimeType") or inline.get("mime_type") or "audio/wav"
            return base64.b64decode(data), mime_type
    raise RuntimeError("Gemini TTS response did not include audio data")


def get_retry_delay_seconds(error_text: str, fallback: float = 50.0) -> float:
    match = re.search(r"retry in ([0-9.]+)s", error_text, flags=re.IGNORECASE)
    if not match:
        return fallback
    return max(1.0, float(match.group(1)) + 2.0)


def generate_openai_tts_clip(
    text: str,
    output_path: Path,
    client,
    tts_model: str,
    tts_voice: str,
    tts_instructions: str | None,
) -> None:
    speech_kwargs = {
        "model": tts_model,
        "voice": tts_voice,
        "input": text,
    }
    if tts_model == "gpt-4o-mini-tts" and tts_instructions:
        speech_kwargs["instructions"] = tts_instructions

    with client.audio.speech.with_streaming_response.create(**speech_kwargs) as resp:
        resp.stream_to_file(str(output_path))


def generate_gemini_tts_clip(
    text: str,
    output_path: Path,
    api_key: str,
    gemini_tts_model: str,
    tts_voice: str,
    tts_instructions: str | None,
    max_retries: int = 4,
) -> None:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_tts_model}:generateContent?key={api_key}"
    style = tts_instructions or (
        "Speak in Korean with a bright, warm, cute, youthful feminine voice. "
        "Keep pronunciation clear for Korean learners. Read the text exactly once."
    )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            f"{style}\n"
                            "Output audio only. Do not add any words before or after the transcript.\n"
                            f"Transcript: {text}"
                        )
                    }
                ],
            }
        ],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": tts_voice}
                }
            },
        },
    }

    response = None
    for attempt in range(max_retries + 1):
        response = requests.post(url, json=payload, timeout=60)
        if response.ok:
            break
        if response.status_code != 429 or attempt >= max_retries:
            raise RuntimeError(f"Gemini TTS API {response.status_code}: {response.text[:500]}")

        delay = get_retry_delay_seconds(response.text)
        print(f"    Gemini quota 대기: {delay:.1f}s 후 재시도 ({attempt + 1}/{max_retries})")
        time.sleep(delay)

    if response is None or not response.ok:
        raise RuntimeError("Gemini TTS API failed without a response")

    audio_data, content_type = extract_gemini_audio(response.json())
    if content_type.startswith("audio/L16") or content_type.startswith("audio/pcm"):
        audio_data = pcm16_to_wav(audio_data)

    output_path.write_bytes(audio_data)


def generate_video(
    video_id: str,
    lines: list,
    client,
    tmpdir: str,
    video_meta: dict | None = None,
    tts_backend: str = "openai",
    tts_model: str = "tts-1",
    tts_voice: str = "nova",
    tts_instructions: str | None = None,
    gemini_api_key: str | None = None,
    gemini_tts_model: str = "gemini-2.5-flash-preview-tts",
    retime_from_audio: bool = False,
    sentence_gap: float = 0.75,
    tail_padding: float = 0.25,
    gemini_max_retries: int = 4,
) -> bool:
    poster = resolve_poster(video_id, video_meta)
    output = VIDEO_DIR / f"{video_id}.mp4"
    tmp = Path(tmpdir)

    print(f"\n{'─'*55}")
    print(f"▶  {video_id}  ({len(lines)} lines)")

    if not poster.exists():
        print(f"  ✗ poster 없음: {poster}")
        return False

    # ── 1. 각 라인 TTS 생성 ──────────────────────────────
    clips = []  # (audio_path, start_sec, end_sec)
    for i, line in enumerate(lines):
        text = get_korean_sentence(line)
        clip = tmp / f"{video_id}_{i:02d}.{'wav' if tts_backend == 'gemini' else 'mp3'}"
        print(f"  TTS {i+1}/{len(lines)}: {text[:45]}...")

        if tts_backend == "gemini":
            if not gemini_api_key:
                raise RuntimeError("GEMINI_API_KEY 또는 GOOGLE_API_KEY를 찾을 수 없습니다.")
            generate_gemini_tts_clip(
                text,
                clip,
                gemini_api_key,
                gemini_tts_model,
                tts_voice,
                tts_instructions,
                gemini_max_retries,
            )
        else:
            generate_openai_tts_clip(
                text,
                clip,
                client,
                tts_model,
                tts_voice,
                tts_instructions,
            )

        clips.append((clip, line["start"], line["end"]))

    if retime_from_audio:
        cursor = float(lines[0].get("start", 0.5) or 0.5)
        retimed_clips = []
        for line, (clip, _old_start, _old_end) in zip(lines, clips):
            clip_duration = get_audio_duration(clip)
            start = round_time(cursor)
            end = round_time(start + clip_duration + tail_padding)
            line["start"] = start
            line["end"] = end
            retimed_clips.append((clip, start, end))
            cursor = end + sentence_gap
        clips = retimed_clips
        print("  자막 타이밍 재계산 완료:")
        for line in lines:
            print(f"    {line['start']:.2f}s → {line['end']:.2f}s")

    # ── 2. 전체 길이 = 마지막 라인 end + 2초 여유 ────────
    total_duration = lines[-1]["end"] + 2.0

    # ── 3. 무음 베이스 트랙 ───────────────────────────────
    silence = tmp / f"{video_id}_silence.wav"
    run(["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"anullsrc=r=44100:cl=stereo",
         "-t", str(total_duration),
         str(silence)])

    # ── 4. 각 클립을 지정 시간에 배치 (adelay) ────────────
    inputs = ["-i", str(silence)]
    filter_parts = []
    mix_tags = ["[0:a]"]

    for i, (mp3, start, _end) in enumerate(clips):
        inputs += ["-i", str(mp3)]
        delay_ms = int(start * 1000)
        tag = f"a{i+1}"
        filter_parts.append(
            f"[{i+1}:a]adelay={delay_ms}|{delay_ms}[{tag}]"
        )
        mix_tags.append(f"[{tag}]")

    n = len(mix_tags)
    fc = "; ".join(filter_parts)
    fc += f"; {''.join(mix_tags)}amix=inputs={n}:duration=first:normalize=0[aout]"

    combined = tmp / f"{video_id}_audio.wav"
    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", fc,
        "-map", "[aout]",
        str(combined),
    ]
    run(cmd)
    print(f"  오디오 조합 완료: {get_audio_duration(combined):.1f}s")

    # ── 5. poster + audio → mp4 (9:16, 720×1280) ─────────
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(poster),
        "-i", str(combined),
        "-vf", (
            "scale=720:1280:force_original_aspect_ratio=increase,"
            "crop=720:1280"
        ),
        "-c:v", "libx264", "-tune", "stillimage", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        str(output),
    ]
    run(cmd)
    dur = get_audio_duration(output)
    size_kb = output.stat().st_size // 1024
    print(f"  ✓ {output.name}  {dur:.1f}s  {size_kb}KB")
    return True


def update_catalog(video_ids: list[str], cache_version: str | None = None):
    """onui-tube.json의 duration 및 optional cache version을 갱신."""
    videos = load_catalog_list()
    updated = False
    for v in videos:
        vid_id = v["id"]
        if vid_id not in video_ids:
            continue
        mp4 = VIDEO_DIR / f"{vid_id}.mp4"
        if mp4.exists():
            dur = int(get_audio_duration(mp4))
            if v.get("duration") != dur:
                v["duration"] = dur
                updated = True
        if cache_version and v.get("local_video_url"):
            new_url = f"/static/video/{vid_id}.mp4?v={cache_version}"
            if v.get("local_video_url") != new_url:
                v["local_video_url"] = new_url
                updated = True

    if updated:
        with open(TUBE_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(videos, f, ensure_ascii=False, indent=2)
        print("\n  onui-tube.json 업데이트 완료")


def parse_args():
    parser = argparse.ArgumentParser(description="Generate OnuiTube videos from poster images and transcript TTS.")
    parser.add_argument(
        "--ids",
        nargs="+",
        default=DEFAULT_VIDEOS_TO_GENERATE,
        help="Video IDs to generate. Defaults to the original OnuiTube set.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate every video ID in data/onui-tube.json.",
    )
    parser.add_argument(
        "--tts-backend",
        choices=["openai", "gemini"],
        default="openai",
        help="TTS backend to use for video narration.",
    )
    parser.add_argument(
        "--tts-model",
        default="tts-1",
        help="OpenAI TTS model. Use gpt-4o-mini-tts for instruction-controlled tone.",
    )
    parser.add_argument(
        "--tts-voice",
        default="nova",
        help="OpenAI TTS voice.",
    )
    parser.add_argument(
        "--tts-instructions",
        default=None,
        help="Voice style instructions. Applied to Gemini, and to OpenAI when --tts-model is gpt-4o-mini-tts.",
    )
    parser.add_argument(
        "--gemini-tts-model",
        default="gemini-2.5-flash-preview-tts",
        help="Gemini TTS model used when --tts-backend gemini.",
    )
    parser.add_argument(
        "--retime-from-audio",
        action="store_true",
        help="Recalculate transcript start/end times from generated TTS clip durations.",
    )
    parser.add_argument(
        "--sentence-gap",
        type=float,
        default=0.75,
        help="Gap in seconds between retimed sentences.",
    )
    parser.add_argument(
        "--tail-padding",
        type=float,
        default=0.25,
        help="Extra seconds added after each TTS clip before auto-pause should fire.",
    )
    parser.add_argument(
        "--cache-version",
        default=None,
        help="Optional query-string version to apply to generated local_video_url entries.",
    )
    parser.add_argument(
        "--gemini-max-retries",
        type=int,
        default=4,
        help="Number of retries for Gemini TTS 429 quota responses.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    catalog_list = load_catalog_list()
    video_ids = [video["id"] for video in catalog_list] if args.all else args.ids

    client = None
    gemini_api_key = None
    if args.tts_backend == "openai":
        api_key = read_env_value("OPENAI_API_KEY")
        if not api_key:
            print("ERROR: OPENAI_API_KEY를 찾을 수 없습니다.")
            sys.exit(1)

        from openai import OpenAI
        client = OpenAI(api_key=api_key)
    else:
        gemini_api_key = read_env_value("GEMINI_API_KEY") or read_env_value("GOOGLE_API_KEY")
        if not gemini_api_key:
            print("ERROR: GEMINI_API_KEY 또는 GOOGLE_API_KEY를 찾을 수 없습니다.")
            sys.exit(1)

    with open(TRANSCRIPT_FILE) as f:
        transcripts = json.load(f)
    catalog = {video["id"]: video for video in catalog_list}

    print("OnuiTube 영상 생성 시작")
    print(f"대상: {', '.join(video_ids)}")

    successful_ids = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for video_id in video_ids:
            lines = transcripts.get(video_id)
            if not lines:
                print(f"\n✗ {video_id}: transcript 없음")
                continue
            try:
                success = generate_video(
                    video_id,
                    lines,
                    client,
                    tmpdir,
                    catalog.get(video_id),
                    args.tts_backend,
                    args.tts_model,
                    args.tts_voice,
                    args.tts_instructions,
                    gemini_api_key,
                    args.gemini_tts_model,
                    args.retime_from_audio,
                    args.sentence_gap,
                    args.tail_padding,
                    args.gemini_max_retries,
                )
                if success:
                    successful_ids.append(video_id)
            except Exception as e:
                print(f"\n✗ {video_id} 생성 실패: {e}")

    if args.retime_from_audio and successful_ids:
        with open(TRANSCRIPT_FILE, "w", encoding="utf-8") as f:
            json.dump(transcripts, f, ensure_ascii=False, indent=2)
        print("\n  onui-tube-transcripts.json 타이밍 업데이트 완료")

    update_catalog(successful_ids, args.cache_version)
    print("\n✅ 완료!")


if __name__ == "__main__":
    main()
