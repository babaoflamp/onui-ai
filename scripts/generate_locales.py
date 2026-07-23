#!/usr/bin/env python3
"""
HTML 파일에 하드코딩되어 있던 GLOBAL_I18N 및 PAGE_I18N 딕셔너리를 추출하여
data/locales 폴더 아래에 개별 JSON 파일(ko.json, en.json 등)로 분리해주는 유틸리티 스크립트입니다.
"""

import re
import json
import os
import subprocess
from pathlib import Path

# 번역 데이터가 포함되어 있던 타겟 HTML 파일들
FILES_TO_PARSE = [
    "templates/base.html",
    "templates/dashboard.html",
    "templates/landing.html",
    "templates/speechpro-practice.html",
]

# 기존에 지원하던 언어 및 새로 추가할 확장 언어
EXISTING_LANGS = ["en", "ja", "zh", "vi"]
NEW_LANGS = []


def get_file_content(filepath):
    """
    파일 내용을 읽어옵니다.
    만약 이미 HTML이 수정되어 번역 데이터가 사라졌다면,
    git HEAD를 참조해 수정 전 원본 데이터를 안전하게 가져옵니다.
    """
    try:
        # git으로 가장 최근 커밋의 파일 내용 불러오기 시도
        result = subprocess.run(
            ["git", "show", f"HEAD:{filepath}"], capture_output=True, text=True
        )
        if result.returncode == 0 and (
            "GLOBAL_I18N" in result.stdout or "PAGE_I18N" in result.stdout
        ):
            return result.stdout
    except Exception:
        pass

    # 로컬 파일 직접 읽기 (Fall-back)
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def extract_i18n():
    locales = {lang: {} for lang in EXISTING_LANGS}

    print("🔍 HTML 파일에서 번역 데이터 추출을 시작합니다...")

    for filepath in FILES_TO_PARSE:
        content = get_file_content(filepath)
        if not content:
            print(
                f"  [건너뜀] {filepath} (파일을 읽을 수 없거나 I18N 데이터가 없습니다)"
            )
            continue

        # GLOBAL_I18N 또는 PAGE_I18N 블록 찾기
        blocks = re.findall(
            r"(?:GLOBAL_I18N|PAGE_I18N)\s*=\s*{(.*?)};", content, re.DOTALL
        )

        for block in blocks:
            for lang in EXISTING_LANGS:
                # 언어별 블록 (예: ko: { ... }) 추출
                lang_pattern = rf"{lang}\s*:\s*{{(.*?)(?=\n\s*(?:ko|ja|zh|en)\s*:|\Z)"
                lang_match = re.search(lang_pattern, block, re.DOTALL)

                if lang_match:
                    lang_content = lang_match.group(1)
                    # "key": "value" 형식 추출 정규식
                    kv_pattern = r'([a-zA-Z0-9_.-]+|"[^"]+")\s*:\s*("(?:\\"|[^"])*"|\'(?:\\\'|[^\'])*\')'

                    for kv in re.finditer(kv_pattern, lang_content):
                        key = kv.group(1).strip("\"'")
                        val = kv.group(2)

                        # 감싸진 따옴표 제거 및 이스케이프 해제
                        if val.startswith('"') and val.endswith('"'):
                            val = val[1:-1].replace('\\"', '"')
                        elif val.startswith("'") and val.endswith("'"):
                            val = val[1:-1].replace("\\'", "'")

                        locales[lang][key] = val

    out_dir = Path("data/locales")
    out_dir.mkdir(parents=True, exist_ok=True)

    total_extracted = len(locales["en"]) if "en" in locales else 0
    if total_extracted == 0:
        print("\n❌ 추출된 텍스트가 없습니다. HTML 파일이나 Git 상태를 확인해주세요.")
        return

    print(f"\n총 {total_extracted}개의 번역 키를 성공적으로 추출했습니다!\n")

    # 기존 언어 저장
    for lang in EXISTING_LANGS:
        if lang in locales and locales[lang]:
            file_path = out_dir / f"{lang}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(locales[lang], f, ensure_ascii=False, indent=2)
            print(f"✅ {file_path} 파일 생성 완료 ({len(locales[lang])} keys)")

    # 새로운 국어 생성 (영어 데이터를 기준으로 기본 생성)
    if "en" in locales:
        fallback_data = locales["en"]
        for lang in NEW_LANGS:
            file_path = out_dir / f"{lang}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(fallback_data, f, ensure_ascii=False, indent=2)
            print(f"✅ {file_path} 파일 생성 완료 (영어 Fallback 복사)")


if __name__ == "__main__":
    extract_i18n()
