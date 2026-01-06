import os
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

import requests


KRDICT_API_URL = os.getenv("KRDICT_API_URL", "https://krdict.korean.go.kr/api/search")


def _get_text(node: ET.Element, tag: str) -> Optional[str]:
    child = node.find(tag)
    if child is None or child.text is None:
        return None
    text = child.text.strip()
    return text if text else None


def _parse_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_translations(sense_node: ET.Element) -> List[Dict[str, Optional[str]]]:
    translations = []
    for trans in sense_node.findall("translation"):
        translations.append(
            {
                "trans_lang": _get_text(trans, "trans_lang"),
                "trans_word": _get_text(trans, "trans_word"),
                "trans_dfn": _get_text(trans, "trans_dfn"),
            }
        )
    return translations


def _parse_senses(item_node: ET.Element) -> List[Dict[str, Any]]:
    senses = []
    for sense in item_node.findall("sense"):
        sense_data: Dict[str, Any] = {
            "sense_order": _parse_int(_get_text(sense, "sense_order")),
            "definition": _get_text(sense, "definition"),
        }
        translations = _parse_translations(sense)
        if translations:
            sense_data["translations"] = translations
        senses.append(sense_data)
    return senses


def parse_krdict_response(xml_text: str) -> Dict[str, Any]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML response: {exc}") from exc

    if root.tag == "error":
        return {
            "error": {
                "code": _get_text(root, "error_code"),
                "message": _get_text(root, "message"),
            }
        }

    channel = root if root.tag == "channel" else root.find("channel")
    if channel is None:
        return {
            "error": {
                "code": "invalid_response",
                "message": "Missing channel element",
            }
        }

    header = {
        "title": _get_text(channel, "title"),
        "link": _get_text(channel, "link"),
        "description": _get_text(channel, "description"),
        "lastBuildDate": _get_text(channel, "lastBuildDate"),
        "total": _parse_int(_get_text(channel, "total")),
        "start": _parse_int(_get_text(channel, "start")),
        "num": _parse_int(_get_text(channel, "num")),
    }

    items = []
    for item in channel.findall("item"):
        entry: Dict[str, Any] = {
            "target_code": _parse_int(_get_text(item, "target_code")),
            "word": _get_text(item, "word"),
            "sup_no": _parse_int(_get_text(item, "sup_no")),
            "origin": _get_text(item, "origin"),
            "pronunciation": _get_text(item, "pronunciation"),
            "word_grade": _get_text(item, "word_grade"),
            "pos": _get_text(item, "pos"),
            "link": _get_text(item, "link"),
            "example": _get_text(item, "example"),
        }

        senses = _parse_senses(item)
        if senses:
            entry["senses"] = senses

        items.append(entry)

    return {"channel": header, "items": items}


def search_krdict(
    api_key: str,
    q: str,
    start: int = 1,
    num: int = 10,
    sort: Optional[str] = None,
    part: Optional[str] = None,
    translated: Optional[str] = None,
    trans_lang: Optional[str] = None,
    advanced: Optional[str] = None,
    target: Optional[int] = None,
    lang: Optional[int] = None,
    method: Optional[str] = None,
    type1: Optional[str] = None,
    type2: Optional[str] = None,
    level: Optional[str] = None,
    pos: Optional[str] = None,
    multimedia: Optional[str] = None,
    letter_s: Optional[int] = None,
    letter_e: Optional[int] = None,
    sense_cat: Optional[str] = None,
    subject_cat: Optional[str] = None,
) -> Dict[str, Any]:
    if not api_key:
        raise RuntimeError("KRDICT_API_KEY is not set")
    if not q or not q.strip():
        raise ValueError("q is required")

    params: Dict[str, Any] = {
        "key": api_key,
        "q": q,
        "start": start,
        "num": num,
    }

    optional_params = {
        "sort": sort,
        "part": part,
        "translated": translated,
        "trans_lang": trans_lang,
        "advanced": advanced,
        "target": target,
        "lang": lang,
        "method": method,
        "type1": type1,
        "type2": type2,
        "level": level,
        "pos": pos,
        "multimedia": multimedia,
        "letter_s": letter_s,
        "letter_e": letter_e,
        "sense_cat": sense_cat,
        "subject_cat": subject_cat,
    }

    for key, value in optional_params.items():
        if value is None:
            continue
        params[key] = value

    response = requests.get(KRDICT_API_URL, params=params, timeout=15)
    response.raise_for_status()
    return parse_krdict_response(response.text)
