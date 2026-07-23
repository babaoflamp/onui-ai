#!/usr/bin/env python3
"""
Gemini API를 사용하여 ko.json 파일을 기반으로 다국어 JSON 파일들을 자동 번역합니다.
"""

import os
import json
import time
from pathlib import Path
import requests
from dotenv import load_dotenv

# 환경 변수 로드 (.env 파일에서 GEMINI_API_KEY 가져오기)
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("❌ 오류: .env 파일에 GEMINI_API_KEY가 설정되어 있지 않습니다.")
    exit(1)

SOURCE_FILE = Path("data/locales/en.json")
OUT_DIR = Path("data/locales")

# 번역할 언어 목록 (언어 코드: 영어로 된 언어명)
TARGET_LANGS = {
    "ja": "Japanese",
    "zh": "Simplified Chinese",
    "vi": "Vietnamese",
    "ne": "Nepali",
    "id": "Indonesian (Bahasa Indonesia)",
    "mn": "Mongolian (Cyrillic script)",
    "lo": "Lao (Lao script)",
}


def translate_with_gemini(source_data, target_lang_name):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    prompt = f"""
    You are an expert app localizer. Translate the values of the following JSON from English to {target_lang_name}.
    - Keep the keys exactly the same.
    - The context is a Korean language learning app (ONUI).
    - Keep any HTML tags (like <span>) or placeholders (like {{nickname}}) intact.
    """

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                        + f"\n\nSource JSON:\n{json.dumps(source_data, ensure_ascii=False)}"
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "response_mime_type": "application/json",
        },
    }

    response = requests.post(url, json=payload)
    response.raise_for_status()

    result = response.json()
    translated_text = result["candidates"][0]["content"]["parts"][0]["text"]

    return json.loads(translated_text)


def main():
    if not SOURCE_FILE.exists():
        print(f"❌ 오류: 원본 파일 {SOURCE_FILE} 이(가) 존재하지 않습니다.")
        return

    print("📖 원본 영어 파일(en.json)을 읽어옵니다...")
    with open(SOURCE_FILE, "r", encoding="utf-8") as f:
        source_data = json.load(f)

    total_keys = len(source_data)
    print(f"총 {total_keys}개의 번역 키가 확인되었습니다.\n")

    for lang_code, lang_name in TARGET_LANGS.items():
        out_file = OUT_DIR / f"{lang_code}.json"

        print(f"🔄 [{lang_code}] {lang_name} 번역 중...")
        try:
            translated_data = translate_with_gemini(source_data, lang_name)

            # API가 누락한 키가 있는지 확인하여 한국어 원본으로 채움 (안전장치)
            for k, v in source_data.items():
                if k not in translated_data:
                    translated_data[k] = v

            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(translated_data, f, ensure_ascii=False, indent=2)

            print(f"  ✅ {out_file.name} 저장 완료!")

            # Rate Limit(분당 요청 횟수 제한) 방지를 위한 3초 대기
            time.sleep(3)

        except Exception as e:
            print(f"  ❌ {lang_name} 번역 실패: {e}")

    print("\n🎉 모든 번역 작업이 완료되었습니다!")


if __name__ == "__main__":
    main()
