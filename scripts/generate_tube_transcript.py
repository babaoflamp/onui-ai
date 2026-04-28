#!/usr/bin/env python3
"""
OnuiTube 트랜스크립트 자동 생성기
=====================================
YouTube 영상 ID를 입력받아 자막을 추출하고 Gemini AI로 단어 분석 후
data/onui-tube-transcripts.json에 저장합니다.

사용법:
  python3 scripts/generate_tube_transcript.py <VIDEO_ID>
  python3 scripts/generate_tube_transcript.py v1ok2sWgiqA

옵션:
  --dry-run   저장하지 않고 결과만 출력
  --force     기존 트랜스크립트가 있어도 덮어쓰기
  --all       onui-tube.json의 모든 영상 처리
"""

import os
import sys
import json
import time
import argparse
import tempfile
import textwrap
from pathlib import Path

# ── 프로젝트 루트 설정 ──────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# .env 로드
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

import requests

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
TUBE_JSON = PROJECT_ROOT / "data" / "onui-tube.json"
TRANSCRIPTS_JSON = PROJECT_ROOT / "data" / "onui-tube-transcripts.json"

VALID_POS = {"Noun", "Verb", "Adjective", "Adverb", "Particle", "Expression", "Other"}


# ── yt-dlp 자막 추출 ───────────────────────────────────────────────────

def fetch_youtube_captions(video_id: str) -> list[dict]:
    """
    yt-dlp로 YouTube 자동 자막(영어 우선)을 추출해 세그먼트 목록으로 반환.
    반환: [{"start": float, "end": float, "text": str}, ...]
    """
    try:
        import yt_dlp
    except ImportError:
        print("ERROR: yt-dlp가 설치되지 않았습니다. pip install yt-dlp 실행 후 재시도하세요.")
        sys.exit(1)

    url = f"https://www.youtube.com/watch?v={video_id}"
    segments = []

    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            "skip_download": True,
            "writeautomaticsub": True,
            "writesubtitles": True,
            "subtitleslangs": ["en", "en-US", "en-GB"],
            "subtitlesformat": "json3",
            "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,  # 특정 언어 429 에러 무시
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                print(f"  WARNING: 영상 정보를 가져올 수 없습니다.")
                return []

        # json3 자막 파일 찾기 (영어 우선)
        subtitle_file = None
        for lang in ["en", "en-US", "en-GB", "ko"]:
            candidates = list(Path(tmpdir).glob(f"*.{lang}.json3"))
            if candidates:
                subtitle_file = candidates[0]
                print(f"  자막 언어: {lang} ({subtitle_file.name})")
                break

        if not subtitle_file:
            vtt_candidates = list(Path(tmpdir).glob("*.vtt"))
            if not vtt_candidates:
                print(f"  WARNING: '{video_id}' 영상에서 자막을 찾을 수 없습니다.")
                print("  → YouTube 자동 자막이 없는 영상입니다. --manual 모드를 사용하거나 자막을 직접 추가하세요.")
                return []
            # VTT 폴백 파싱
            return _parse_vtt(vtt_candidates[0])

        # json3 파싱
        return _parse_json3(subtitle_file)


def _parse_json3(path: Path) -> list[dict]:
    """YouTube json3 자막 형식 파싱"""
    data = json.loads(path.read_text(encoding="utf-8"))
    segments = []
    for event in data.get("events", []):
        segs = event.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs).strip()
        text = text.replace("\n", " ").strip()
        if not text or text == "​":
            continue
        start_ms = event.get("tStartMs", 0)
        dur_ms = event.get("dDurationMs", 2000)
        segments.append({
            "start": round(start_ms / 1000, 2),
            "end": round((start_ms + dur_ms) / 1000, 2),
            "text": text,
        })
    # 겹치는 세그먼트 병합 (YouTube 자막 특성상 중복이 많음)
    return _merge_overlapping(segments)


def _parse_vtt(path: Path) -> list[dict]:
    """WebVTT 자막 파싱 (폴백)"""
    import re
    content = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})\n(.*?)(?=\n\n|\Z)",
        re.DOTALL,
    )

    def ts_to_sec(ts):
        h, m, s = ts.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    segments = []
    for m in pattern.finditer(content):
        text = re.sub(r"<[^>]+>", "", m.group(3)).strip().replace("\n", " ")
        if text:
            segments.append({
                "start": round(ts_to_sec(m.group(1)), 2),
                "end": round(ts_to_sec(m.group(2)), 2),
                "text": text,
            })
    return _merge_overlapping(segments)


def _merge_overlapping(segments: list[dict], gap_threshold: float = 0.5) -> list[dict]:
    """너무 짧거나 겹치는 세그먼트를 병합"""
    if not segments:
        return []
    merged = [segments[0].copy()]
    for seg in segments[1:]:
        prev = merged[-1]
        # 이전 세그먼트와 거의 동일하거나 완전 포함이면 스킵
        if seg["text"] == prev["text"]:
            continue
        # 이전 end 이전에 시작하면 병합
        if seg["start"] < prev["end"] - 0.1:
            prev["end"] = max(prev["end"], seg["end"])
            if seg["text"] not in prev["text"]:
                prev["text"] = prev["text"] + " " + seg["text"]
        else:
            merged.append(seg.copy())
    return merged


# ── Gemini AI 단어 분석 ────────────────────────────────────────────────

def enrich_with_gemini(video_id: str, segments: list[dict], video_title: str = "") -> list[dict]:
    """
    Gemini로 각 세그먼트에 한국어 단어 + 의미 + 품사 추가.
    세그먼트를 배치로 묶어 API 호출 최소화.
    """
    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY가 설정되지 않았습니다.")
        sys.exit(1)

    BATCH_SIZE = 8  # 한 번에 Gemini에 보낼 세그먼트 수
    enriched = []

    for i in range(0, len(segments), BATCH_SIZE):
        batch = segments[i : i + BATCH_SIZE]
        print(f"  Gemini 분석 중... ({i+1}~{min(i+BATCH_SIZE, len(segments))}/{len(segments)})")

        result_batch = _call_gemini_enrich(batch, video_title)
        enriched.extend(result_batch)

        if i + BATCH_SIZE < len(segments):
            time.sleep(0.5)  # API rate limit 방지

    return enriched


def _call_gemini_enrich(batch: list[dict], video_title: str) -> list[dict]:
    """Gemini에 세그먼트 배치를 보내 단어 분석 결과를 받아옴"""

    segments_text = "\n".join(
        f"[{idx}] start={seg['start']} end={seg['end']} text=\"{seg['text']}\""
        for idx, seg in enumerate(batch)
    )

    prompt = textwrap.dedent(f"""
    You are a Korean language learning content analyst.
    The following are English subtitle segments from a Korean learning YouTube video titled: "{video_title}"

    For each segment, identify ALL Korean words or phrases that appear or are being taught in that segment.
    These are Korean learning videos, so segments often introduce Korean vocabulary even if the subtitle text is in English.

    Segments:
    {segments_text}

    Return a JSON array with one object per segment (same order, same count as input).
    Each object must have:
    - "start": number (copy from input)
    - "end": number (copy from input)
    - "trans": string (the English subtitle text, cleaned up)
    - "words": array of objects, each with:
      - "label": string (Korean word/phrase in Hangul, e.g. "딸기")
      - "mean": string (English meaning, concise, e.g. "strawberry")
      - "pos": string (one of: Noun, Verb, Adjective, Adverb, Particle, Expression, Other)

    Rules:
    - If a segment teaches or mentions a Korean word, include it in "words" even if written in romanization in the subtitle.
    - If no Korean words are relevant to the segment, return "words": []
    - Do NOT invent words that aren't related to the segment content.
    - Return ONLY the JSON array, no markdown, no explanation.
    """).strip()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
    }

    resp = requests.post(url, json=payload, timeout=60)
    if not resp.ok:
        print(f"  WARNING: Gemini API 오류 {resp.status_code} — 단어 없이 저장합니다.")
        return [
            {"start": s["start"], "end": s["end"], "trans": s["text"], "words": []}
            for s in batch
        ]

    try:
        raw = resp.json()
        text = raw["candidates"][0]["content"]["parts"][0]["text"]
        result = json.loads(text)
        if not isinstance(result, list) or len(result) != len(batch):
            raise ValueError("배열 길이 불일치")
        # words pos 검증
        for seg in result:
            seg["words"] = [
                w for w in seg.get("words", [])
                if w.get("label") and w.get("mean") and w.get("pos") in VALID_POS
            ]
        return result
    except Exception as e:
        print(f"  WARNING: Gemini 응답 파싱 실패 ({e}) — 단어 없이 저장합니다.")
        return [
            {"start": s["start"], "end": s["end"], "trans": s["text"], "words": []}
            for s in batch
        ]


# ── 저장 & 검증 ────────────────────────────────────────────────────────

def load_transcripts() -> dict:
    if TRANSCRIPTS_JSON.exists():
        return json.loads(TRANSCRIPTS_JSON.read_text(encoding="utf-8")) or {}
    return {}


def save_transcripts(data: dict) -> None:
    TRANSCRIPTS_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def compute_coverage(segments: list[dict], duration: float) -> float:
    if not segments or duration <= 0:
        return 0.0
    max_end = max(s.get("end", 0) for s in segments)
    return round(min(max_end / duration, 1.0), 3)


def get_video_info(video_id: str) -> dict | None:
    if not TUBE_JSON.exists():
        return None
    videos = json.loads(TUBE_JSON.read_text(encoding="utf-8"))
    return next((v for v in videos if v.get("id") == video_id), None)


# ── 메인 처리 ──────────────────────────────────────────────────────────

def process_video(video_id: str, dry_run: bool = False, force: bool = False) -> bool:
    print(f"\n{'='*55}")
    print(f"  Video ID: {video_id}")

    info = get_video_info(video_id)
    if info:
        print(f"  제목:     {info.get('title', '(unknown)')}")
        print(f"  레벨:     Lv.{info.get('level', '?')}")
        print(f"  길이:     {info.get('duration', 0)}초")
    else:
        print(f"  INFO: onui-tube.json에 없는 ID입니다. 트랜스크립트만 생성합니다.")

    transcripts = load_transcripts()
    if video_id in transcripts and not force:
        existing = transcripts[video_id]
        duration = info.get("duration", 0) if info else 0
        cov = compute_coverage(existing, duration)
        print(f"  기존 트랜스크립트 {len(existing)}개 세그먼트 (커버리지 {cov*100:.0f}%)")
        print(f"  → 이미 존재합니다. 덮어쓰려면 --force 옵션을 사용하세요.")
        return True

    # 1. 자막 추출
    print(f"\n  [1/3] YouTube 자막 추출 중...")
    segments = fetch_youtube_captions(video_id)
    if not segments:
        print(f"  SKIP: 자막 추출 실패.")
        return False
    print(f"  → {len(segments)}개 세그먼트 추출 완료")

    # 2. Gemini 단어 분석
    print(f"\n  [2/3] Gemini 단어 분석 중...")
    title = info.get("title", "") if info else ""
    enriched = enrich_with_gemini(video_id, segments, title)
    total_words = sum(len(s.get("words", [])) for s in enriched)
    segs_with_words = sum(1 for s in enriched if s.get("words"))
    print(f"  → 단어 있는 세그먼트: {segs_with_words}/{len(enriched)}, 총 단어: {total_words}개")

    # 3. 커버리지 계산 및 결과 출력
    duration = info.get("duration", 0) if info else 0
    coverage = compute_coverage(enriched, duration)
    status = "✅ READY" if coverage >= 0.7 else f"⚠️  {coverage*100:.0f}% (기준: 70%+)"
    print(f"\n  [3/3] 커버리지: {coverage*100:.0f}% {status}")

    if dry_run:
        print(f"\n  [DRY RUN] 저장 건너뜀. 결과 미리보기:")
        print(json.dumps(enriched[:3], ensure_ascii=False, indent=2))
        if len(enriched) > 3:
            print(f"  ... ({len(enriched)-3}개 더)")
        return True

    # 저장
    transcripts[video_id] = enriched
    save_transcripts(transcripts)
    print(f"  → 저장 완료: {TRANSCRIPTS_JSON}")
    return coverage >= 0.7


# ── CLI ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="OnuiTube 트랜스크립트 자동 생성기",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("video_id", nargs="?", help="YouTube Video ID")
    parser.add_argument("--all", action="store_true", help="onui-tube.json의 모든 영상 처리")
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않고 결과만 출력")
    parser.add_argument("--force", action="store_true", help="기존 트랜스크립트 덮어쓰기")
    args = parser.parse_args()

    if not args.video_id and not args.all:
        parser.print_help()
        sys.exit(1)

    video_ids = []
    if args.all:
        if not TUBE_JSON.exists():
            print(f"ERROR: {TUBE_JSON} 파일이 없습니다.")
            sys.exit(1)
        videos = json.loads(TUBE_JSON.read_text(encoding="utf-8"))
        video_ids = [v["id"] for v in videos if v.get("id")]
        print(f"onui-tube.json에서 {len(video_ids)}개 영상 처리 예정")
    else:
        video_ids = [args.video_id]

    results = {}
    for vid in video_ids:
        ok = process_video(vid, dry_run=args.dry_run, force=args.force)
        results[vid] = "ready" if ok else "failed"

    print(f"\n{'='*55}")
    print("처리 결과:")
    for vid, status in results.items():
        mark = "✅" if status == "ready" else "❌"
        print(f"  {mark} {vid}  →  {status}")

    if not args.dry_run:
        print(f"\n카탈로그 상태 확인:")
        print(f"  python3 scripts/audit_onuitube_catalog.py")


if __name__ == "__main__":
    main()
