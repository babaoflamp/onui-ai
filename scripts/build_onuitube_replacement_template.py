#!/usr/bin/env python3
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.services.onui_tube_catalog import annotate_tube_videos


def main() -> int:
    catalog_path = ROOT / "data/onui-tube.json"
    transcripts_path = ROOT / "data/onui-tube-transcripts.json"
    output_path = ROOT / "data/onui-tube-replacements.template.json"

    videos = json.loads(catalog_path.read_text(encoding="utf-8"))
    transcripts = json.loads(transcripts_path.read_text(encoding="utf-8"))
    annotated = annotate_tube_videos(videos, transcripts)

    template = []
    for video in annotated:
        if video["catalog_status"] == "ready":
            continue
        template.append(
            {
                "current_video": {
                    "id": video["id"],
                    "title": video["title"],
                    "catalog_status": video["catalog_status"],
                    "catalog_status_reason": video["catalog_status_reason"],
                    "transcript_coverage": video["transcript_coverage"],
                },
                "replacement_video": {
                    "id": "",
                    "title": "",
                    "description": "",
                    "level": video["level"],
                    "source_type": "youtube",
                    "video_url": "",
                    "poster_url": "",
                    "duration": 0,
                    "transcript_offset": 0,
                    "notes": "Transcript must match at least 70% of the runtime before publishing.",
                },
            }
        )

    output_path.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(template)} replacement slots to {output_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
