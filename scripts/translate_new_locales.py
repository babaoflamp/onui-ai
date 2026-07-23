#!/usr/bin/env python3
"""Translate en.json into new locale files using Gemini (batched)."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("❌ GEMINI_API_KEY is not set")
    sys.exit(1)

SOURCE_FILE = Path("data/locales/en.json")
OUT_DIR = Path("data/locales")
BATCH_SIZE = 80
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Target languages to generate (code -> English name for the prompt)
TARGET_LANGS = {
    "id": "Indonesian (Bahasa Indonesia)",
    "mn": "Mongolian (Cyrillic script)",
    "lo": "Lao (Lao script)",
}


def translate_batch(batch: dict[str, str], target_lang_name: str) -> dict[str, str]:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    prompt = f"""You are an expert app localizer for ONUI, a Korean language learning app.
Translate the JSON string values from English to {target_lang_name}.
Rules:
- Keep every key exactly the same.
- Keep HTML tags (e.g. <span class="...">), placeholders like {{nickname}}, and brand names (ONUI, OnuiTube, SpeechPro) intact.
- Use natural, modern UI phrasing for learners.
- Return ONLY a JSON object mapping the same keys to translated strings.
"""
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                        + "\n\nSource JSON:\n"
                        + json.dumps(batch, ensure_ascii=False)
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "response_mime_type": "application/json",
        },
    }
    response = requests.post(url, json=payload, timeout=180)
    response.raise_for_status()
    result = response.json()
    text = result["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object, got {type(data)}")
    return {str(k): str(v) for k, v in data.items()}


def translate_locale(source: dict[str, str], lang_code: str, lang_name: str) -> dict[str, str]:
    keys = list(source.keys())
    translated: dict[str, str] = {}
    total_batches = (len(keys) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(keys), BATCH_SIZE):
        batch_keys = keys[i : i + BATCH_SIZE]
        batch = {k: source[k] for k in batch_keys}
        batch_no = i // BATCH_SIZE + 1
        print(f"  [{lang_code}] batch {batch_no}/{total_batches} ({len(batch)} keys)...")
        for attempt in range(3):
            try:
                part = translate_batch(batch, lang_name)
                for k in batch_keys:
                    translated[k] = part.get(k, source[k])
                break
            except Exception as exc:
                if attempt == 2:
                    print(f"  ⚠ batch failed after retries ({exc}); falling back to English")
                    for k in batch_keys:
                        translated[k] = source[k]
                else:
                    wait = 2 ** (attempt + 1)
                    print(f"  ↻ retry in {wait}s: {exc}")
                    time.sleep(wait)
        time.sleep(1.2)

    # Preserve source key order
    return {k: translated.get(k, source[k]) for k in source}


def main() -> None:
    if not SOURCE_FILE.exists():
        print(f"❌ Missing {SOURCE_FILE}")
        sys.exit(1)

    with SOURCE_FILE.open(encoding="utf-8") as f:
        source = json.load(f)

    print(f"Source keys: {len(source)}\n")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for code, name in TARGET_LANGS.items():
        out = OUT_DIR / f"{code}.json"
        print(f"🔄 Translating → {code} ({name})")
        data = translate_locale(source, code, name)
        with out.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"  ✅ wrote {out} ({len(data)} keys)\n")

    print("🎉 Done")


if __name__ == "__main__":
    main()
