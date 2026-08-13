from backend.routes.tts import _gemini_voice_candidates


def test_invalid_requested_voice_uses_valid_default_before_api_call():
    assert _gemini_voice_candidates("default", "Aoede") == ["Aoede", None]


def test_invalid_requested_and_default_use_known_good_voice():
    assert _gemini_voice_candidates("not-a-gemini-voice", "stale-default") == [
        "Aoede",
        None,
    ]


def test_supported_voice_is_preserved_case_insensitively():
    assert _gemini_voice_candidates(" lEdA ", "Aoede") == ["Leda", "Aoede", None]


def test_gender_aliases_keep_existing_fallback_order():
    assert _gemini_voice_candidates("female", "invalid") == [
        "Aoede",
        "Kore",
        "Leda",
        "Zephyr",
        None,
    ]
