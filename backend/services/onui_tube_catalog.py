from __future__ import annotations

from typing import Any


MIN_TRANSCRIPT_COVERAGE = 0.7
REQUIRED_VIDEO_FIELDS = ("id", "title", "description", "level", "duration", "poster_url")
COMPUTED_VIDEO_FIELDS = (
    "has_transcript",
    "transcript_line_count",
    "transcript_coverage",
    "is_learning_ready",
    "replacement_required",
    "catalog_status",
    "catalog_status_reason",
)
VALID_SOURCE_TYPES = {"youtube", "local"}


def annotate_tube_videos(
    videos: list[dict[str, Any]],
    transcripts: dict[str, list[dict[str, Any]]] | None = None,
    min_coverage: float = MIN_TRANSCRIPT_COVERAGE,
) -> list[dict[str, Any]]:
    transcript_map = transcripts or {}

    for video in videos:
        transcript_lines = transcript_map.get(video.get("id"), [])
        coverage_end = max((float(line.get("end", 0) or 0) for line in transcript_lines), default=0.0)
        duration = float(video.get("duration") or 0)
        coverage = min(coverage_end / duration, 1.0) if duration > 0 else 0.0
        has_transcript = bool(transcript_lines)
        is_learning_ready = has_transcript and coverage >= min_coverage

        if not has_transcript:
            status = "transcript_missing"
            status_reason = "missing_transcript"
        elif not is_learning_ready:
            status = "replacement_required"
            status_reason = "insufficient_transcript_coverage"
        else:
            status = "ready"
            status_reason = ""

        video.setdefault("transcript_offset", 0)
        video["has_transcript"] = has_transcript
        video["transcript_line_count"] = len(transcript_lines)
        video["transcript_coverage"] = round(coverage, 3)
        video["is_learning_ready"] = is_learning_ready
        video["replacement_required"] = status == "replacement_required"
        video["catalog_status"] = status
        video["catalog_status_reason"] = status_reason

    return videos


def build_tube_catalog_summary(videos: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        "total": len(videos),
        "ready": 0,
        "replacement_required": 0,
        "transcript_missing": 0,
    }

    for video in videos:
        status = video.get("catalog_status")
        if status in summary:
            summary[status] += 1

    return summary


def strip_computed_tube_fields(videos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = []
    for video in videos:
        cleaned.append({k: v for k, v in video.items() if k not in COMPUTED_VIDEO_FIELDS})
    return cleaned


def validate_tube_video_catalog(
    videos: Any,
    transcripts: dict[str, list[dict[str, Any]]] | None = None,
    min_coverage: float = MIN_TRANSCRIPT_COVERAGE,
    allow_unready: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []

    if not isinstance(videos, list):
        return {
            "valid": False,
            "errors": ["Catalog payload must be a list of video objects."],
            "summary": {"total": 0, "ready": 0, "replacement_required": 0, "transcript_missing": 0},
            "videos": [],
        }

    for idx, video in enumerate(videos):
        if not isinstance(video, dict):
            errors.append(f"videos[{idx}] must be an object.")
            continue

        missing_fields = [field for field in REQUIRED_VIDEO_FIELDS if not str(video.get(field, "") or "").strip()]
        if missing_fields:
            errors.append(f"videos[{idx}] missing required fields: {', '.join(missing_fields)}")

        source_type = str(video.get("source_type", "youtube") or "youtube").strip().lower()
        if source_type not in VALID_SOURCE_TYPES:
            errors.append(f"videos[{idx}] has invalid source_type '{source_type}'.")
        elif source_type == "youtube" and not str(video.get("video_url", "") or "").strip():
            errors.append(f"videos[{idx}] requires video_url for source_type 'youtube'.")
        elif source_type == "local" and not str(video.get("local_video_url", "") or "").strip():
            errors.append(f"videos[{idx}] requires local_video_url for source_type 'local'.")

        try:
            duration = float(video.get("duration") or 0)
            if duration <= 0:
                errors.append(f"videos[{idx}] must have a positive duration.")
        except (TypeError, ValueError):
            errors.append(f"videos[{idx}] has an invalid duration.")

    annotated = annotate_tube_videos(videos, transcripts, min_coverage=min_coverage)
    summary = build_tube_catalog_summary(annotated)

    if not allow_unready:
        for video in annotated:
            if video.get("catalog_status") != "ready":
                errors.append(
                    f"{video.get('id')} is not ready for publishing "
                    f"({video.get('catalog_status')}, coverage={round(video.get('transcript_coverage', 0) * 100)}%)."
                )

    return {
        "valid": not errors,
        "errors": errors,
        "summary": summary,
        "videos": annotated,
    }
