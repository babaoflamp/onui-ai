import json
import requests
from backend.config import load_settings
from backend.services.speechpro_service import normalize_spaces

# Model Settings
settings = load_settings()
MODEL_BACKEND = settings.model_backend
OLLAMA_URL = settings.ollama_url
OLLAMA_MODEL = settings.ollama_model
GEMINI_API_KEY = settings.gemini_api_key
GEMINI_MODEL = settings.gemini_model
OPENAI_API_KEY = settings.openai_api_key
OPENAI_MODEL = settings.openai_model

# OpenAI Client
client = None
if OPENAI_API_KEY:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)

# Gemini Client
gemini_client = None
if GEMINI_API_KEY:
    try:
        from google import genai
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    except ImportError:
        pass


async def generate_pronunciation_feedback(text: str, score_result, ui_lang: str = "en") -> str:
    text = normalize_spaces(text or "")
    if not text:
        raise ValueError("text is required")
    if score_result is None:
        raise ValueError("score_result is required")

    score_value = round(float(getattr(score_result, "score", 0) or 0))
    details = getattr(score_result, "details", {}) or {}
    detail_json = json.dumps(details, ensure_ascii=False)

    prompt = f"""
You are a kind Korean teacher giving pronunciation feedback to a foreign learner.
Explain the pronunciation result in clear, natural English, as if you are tutoring the learner one-on-one.

Response rules:
- Write in English only, regardless of the UI language.
- Keep it to 3 short sentences maximum.
- Sound like a supportive Korean teacher: warm, clear, and practical.
- In the first sentence, give a brief overall evaluation of the learner's pronunciation.
- In the next sentence, explain the 1 or 2 most important pronunciation issues in simple English.
- In the final sentence, give one concrete practice tip the learner can try immediately.
- If helpful, mention a Korean syllable or sound pattern, but explain it in easy English.
- Do not list raw scores or JSON fields directly.
- Avoid emojis, exaggerated praise, and generic filler.

Sentence:
{text}

Score:
{score_value}

Detailed result (JSON):
{detail_json}
""".strip()

    backend = (MODEL_BACKEND or "").strip().lower()

    if backend == "gemini":
        if not gemini_client:
            raise RuntimeError("Gemini client not initialized")
        resp = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        out = (getattr(resp, "text", None) or "").strip()
    elif backend == "openai":
        if not client:
            raise RuntimeError("OpenAI client not initialized")
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
        )
        out = (resp.choices[0].message.content or "").strip()
    elif backend == "ollama":
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.4},
        }
        resp = requests.post(
            f"{OLLAMA_URL.rstrip('/')}/api/generate",
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        out = (resp.json().get("response") or "").strip()
    else:
        raise RuntimeError(f"Unsupported model backend: {MODEL_BACKEND}")

    if not out:
        raise RuntimeError("AI feedback response was empty")
    return out

