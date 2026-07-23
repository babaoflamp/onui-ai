from backend.services.dalle_service import enhance_prompt_for_korean_learning


def test_enhance_prompt_for_korean_learning_targets_textbook_content():
    prompt = enhance_prompt_for_korean_learning(
        "A student ordering food at a Korean restaurant",
        "illustration",
    )

    assert "Korean language textbook content" in prompt
    assert "classroom learning materials" in prompt
    assert "one clear everyday scene" in prompt
    assert "no speech bubbles" in prompt
    assert "no logos" in prompt


def test_enhance_prompt_for_korean_learning_keeps_photo_style_educational():
    prompt = enhance_prompt_for_korean_learning(
        "A family buying vegetables at a market",
        "photorealistic",
    )

    assert "realistic educational textbook photo style" in prompt
    assert "8k resolution" not in prompt
    assert "cinematic" not in prompt
