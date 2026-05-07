#!/usr/bin/env python3
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.services.onui_tube_catalog import annotate_tube_videos, build_tube_catalog_summary


def main() -> int:
    videos = json.loads((ROOT / "data/onui-tube.json").read_text(encoding="utf-8"))
    transcripts = json.loads((ROOT / "data/onui-tube-transcripts.json").read_text(encoding="utf-8"))
    annotated = annotate_tube_videos(videos, transcripts)
    summary = build_tube_catalog_summary(annotated)

    print("OnuiTube catalog audit")
    print(f"total={summary['total']} ready={summary['ready']} replacement_required={summary['replacement_required']} transcript_missing={summary['transcript_missing']}")

    for video in annotated:
        if video["catalog_status"] == "ready":
            continue
        coverage_pct = round(video["transcript_coverage"] * 100)
        print(
            f"- {video['id']} | {video['title']} | status={video['catalog_status']} | "
            f"coverage={coverage_pct}% | lines={video['transcript_line_count']}"
        )

    return 0 if summary["ready"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
