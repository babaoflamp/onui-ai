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
from pathlib import Path

# 경로 설정 (스크립트 위치와 무관하게 프로젝트 루트 기준)
ROOT = Path(__file__).parent.parent
TRANSCRIPT_FILE = ROOT / "data/onui-tube-transcripts.json"
TUBE_JSON_FILE  = ROOT / "data/onui-tube.json"
POSTER_DIR      = ROOT / "static/images/tube"
VIDEO_DIR       = ROOT / "static/video"

# 파일이 있는 5개 영상만 생성
VIDEOS_TO_GENERATE = [
    "restaurant_ordering",
    "essential_verbs",
    "want_to_korean",
    "bts_dna_lyrics",
    "seoul_living_vlog",
]


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


def generate_video(video_id: str, lines: list, client, tmpdir: str):
    poster = POSTER_DIR / f"{video_id}.jpg"
    output = VIDEO_DIR / f"{video_id}.mp4"
    tmp = Path(tmpdir)

    print(f"\n{'─'*55}")
    print(f"▶  {video_id}  ({len(lines)} lines)")

    if not poster.exists():
        print(f"  ✗ poster 없음: {poster}")
        return

    # ── 1. 각 라인 TTS 생성 ──────────────────────────────
    clips = []  # (mp3_path, start_sec, end_sec)
    for i, line in enumerate(lines):
        text = get_korean_sentence(line)
        mp3 = tmp / f"{video_id}_{i:02d}.mp3"
        print(f"  TTS {i+1}/{len(lines)}: {text[:45]}...")
        resp = client.audio.speech.create(
            model="tts-1",
            voice="nova",
            input=text,
        )
        resp.stream_to_file(str(mp3))
        clips.append((mp3, line["start"], line["end"]))

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


def update_durations(transcripts: dict):
    """onui-tube.json의 duration 필드를 실제 생성된 영상 길이로 갱신."""
    with open(TUBE_JSON_FILE) as f:
        videos = json.load(f)

    updated = False
    for v in videos:
        vid_id = v["id"]
        if vid_id not in VIDEOS_TO_GENERATE:
            continue
        mp4 = VIDEO_DIR / f"{vid_id}.mp4"
        if mp4.exists():
            dur = int(get_audio_duration(mp4))
            if v.get("duration") != dur:
                v["duration"] = dur
                updated = True

    if updated:
        with open(TUBE_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(videos, f, ensure_ascii=False, indent=2)
        print("\n  onui-tube.json duration 업데이트 완료")


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # .env 파일에서 직접 읽기
        env_file = ROOT / ".env"
        for line in env_file.read_text().splitlines():
            if line.startswith("OPENAI_API_KEY="):
                api_key = line.split("=", 1)[1].strip()
                break

    if not api_key:
        print("ERROR: OPENAI_API_KEY를 찾을 수 없습니다.")
        sys.exit(1)

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    with open(TRANSCRIPT_FILE) as f:
        transcripts = json.load(f)

    print("OnuiTube 영상 생성 시작")
    print(f"대상: {', '.join(VIDEOS_TO_GENERATE)}")

    with tempfile.TemporaryDirectory() as tmpdir:
        for video_id in VIDEOS_TO_GENERATE:
            lines = transcripts.get(video_id)
            if not lines:
                print(f"\n✗ {video_id}: transcript 없음")
                continue
            try:
                generate_video(video_id, lines, client, tmpdir)
            except Exception as e:
                print(f"\n✗ {video_id} 생성 실패: {e}")

    update_durations(transcripts)
    print("\n✅ 완료!")


if __name__ == "__main__":
    main()
