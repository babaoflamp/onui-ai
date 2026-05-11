#!/usr/bin/env python3
"""
Pre-generate GTP + FST phonetic data for all sentences in data/speechpro-sentences.json.
Run once (or after adding new sentences), then restart the app to apply.

Usage:
  python scripts/precompute_speechpro_sentences.py
  python scripts/precompute_speechpro_sentences.py --force    # overwrite existing data
  python scripts/precompute_speechpro_sentences.py --dry-run  # preview only, no writes
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Run from project root so backend imports work
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from backend.services.speechpro_service import call_speechpro_gtp, call_speechpro_model, SPEECHPRO_URL

DATA_FILE = ROOT / "data" / "speechpro-sentences.json"


def main():
    parser = argparse.ArgumentParser(description="Pre-compute SpeechPro phonetic data for curated sentences")
    parser.add_argument("--force", action="store_true", help="Regenerate even if fst already exists")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, do not write")
    args = parser.parse_args()

    print(f"SpeechPro API: {SPEECHPRO_URL}")
    print(f"Data file    : {DATA_FILE}")
    if args.dry_run:
        print("[DRY RUN] No changes will be written.\n")

    sentences = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    total = len(sentences)

    # Check connectivity first
    try:
        import requests
        requests.post(
            f"{SPEECHPRO_URL.rstrip('/')}/gtp",
            json={"id": "ping", "text": "네"},
            timeout=10
        ).raise_for_status()
    except Exception as e:
        print(f"\n[ERROR] SpeechPro API is not reachable: {e}")
        print("Make sure the server is running and SPEECHPRO_TARGET is set correctly.")
        sys.exit(1)

    ok = skipped = failed = 0

    for i, s in enumerate(sentences, 1):
        sentence_kr = s.get("sentenceKr", "")
        level = s.get("level", "?")
        sid = s.get("id", i)
        prefix = f"[{i:3d}/{total}] {level} - {sentence_kr[:28]}"

        if not args.force and s.get("fst"):
            print(f"{prefix:<52} SKIP (already done)")
            skipped += 1
            continue

        if args.dry_run:
            print(f"{prefix:<52} (would generate)")
            continue

        # --- GTP ---
        try:
            gtp = call_speechpro_gtp(sentence_kr, request_id=f"pre_{sid}")
        except Exception as e:
            print(f"{prefix:<52} FAIL GTP: {e}")
            failed += 1
            continue

        if gtp.error_code != 0:
            print(f"{prefix:<52} FAIL GTP error_code={gtp.error_code}")
            failed += 1
            continue

        # --- Model ---
        try:
            mdl = call_speechpro_model(sentence_kr, gtp.syll_ltrs, gtp.syll_phns, request_id=f"pre_{sid}")
        except Exception as e:
            print(f"{prefix:<52} FAIL Model: {e}")
            failed += 1
            continue

        if mdl.error_code != 0:
            print(f"{prefix:<52} FAIL Model error_code={mdl.error_code}")
            failed += 1
            continue

        s["syll_ltrs"] = mdl.syll_ltrs
        s["syll_phns"] = mdl.syll_phns
        s["fst"] = mdl.fst
        print(f"{prefix:<52} OK")
        ok += 1

        # Brief pause to avoid hammering the API
        time.sleep(0.05)

    if not args.dry_run:
        DATA_FILE.write_text(
            json.dumps(sentences, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Done: {ok} OK, {skipped} skipped, {failed} failed / {total} total")
    if not args.dry_run and ok > 0:
        print("Restart the app to reload the updated cache: pm2 restart onui-ai")


if __name__ == "__main__":
    main()
