from backend.services.onui_tube_catalog import (
    annotate_tube_videos,
    build_tube_catalog_summary,
    strip_computed_tube_fields,
    validate_tube_video_catalog,
)


def test_annotate_tube_videos_marks_replacement_and_missing_cases():
    videos = [
        {"id": "ready-video", "duration": 10},
        {"id": "short-transcript", "duration": 20},
        {"id": "missing-transcript", "duration": 20},
    ]
    transcripts = {
        "ready-video": [{"start": 0, "end": 9}],
        "short-transcript": [{"start": 0, "end": 5}],
    }

    annotated = annotate_tube_videos(videos, transcripts)

    assert annotated[0]["catalog_status"] == "ready"
    assert annotated[0]["is_learning_ready"] is True
    assert annotated[1]["catalog_status"] == "replacement_required"
    assert annotated[1]["replacement_required"] is True
    assert annotated[2]["catalog_status"] == "transcript_missing"
    assert annotated[2]["has_transcript"] is False

    summary = build_tube_catalog_summary(annotated)
    assert summary == {
        "total": 3,
        "ready": 1,
        "replacement_required": 1,
        "transcript_missing": 1,
    }


def test_validate_tube_video_catalog_blocks_unready_publish_by_default():
    videos = [
        {
            "id": "short-transcript",
            "title": "Short Transcript",
            "description": "Example",
            "level": "1",
            "duration": 20,
            "poster_url": "/poster.jpg",
            "video_url": "https://www.youtube.com/embed/example",
        }
    ]
    transcripts = {"short-transcript": [{"start": 0, "end": 5}]}

    result = validate_tube_video_catalog(videos, transcripts)

    assert result["valid"] is False
    assert result["summary"]["replacement_required"] == 1
    assert "not ready for publishing" in result["errors"][0]


def test_validate_tube_video_catalog_allows_draft_save_with_flag():
    videos = [
        {
            "id": "draft-video",
            "title": "Draft Video",
            "description": "Example",
            "level": "2",
            "duration": 20,
            "poster_url": "/poster.jpg",
            "video_url": "https://www.youtube.com/embed/example",
        }
    ]
    transcripts = {"draft-video": [{"start": 0, "end": 5}]}

    result = validate_tube_video_catalog(videos, transcripts, allow_unready=True)

    assert result["valid"] is True
    cleaned = strip_computed_tube_fields(result["videos"])
    assert "catalog_status" not in cleaned[0]
    assert cleaned[0]["id"] == "draft-video"
