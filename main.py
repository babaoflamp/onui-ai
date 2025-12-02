import os
import shutil
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
# from openai import OpenAI
from dotenv import load_dotenv
from difflib import SequenceMatcher
import requests
import json
import re
import uvicorn
import subprocess
import wave

# ==========================================
# 설정: 환경변수에서 OpenAI API 키 로드
# ==========================================
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# OpenAI integration disabled/commented out by user request.
# If you want to re-enable OpenAI, uncomment the import at the top and
# restore `client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None`.
client = None

# Backend selection: set MODEL_BACKEND=ollama to use local Ollama server
MODEL_BACKEND = os.getenv("MODEL_BACKEND", "openai")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "exaone")


def _list_ollama_models():
    """Return list of models from local Ollama server or raise."""
    try:
        resp = requests.get(f"{OLLAMA_URL}/v1/models", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
    except Exception as e:
        raise RuntimeError(f"Failed to list Ollama models: {e}")


def _auto_select_ollama_model(preferred=None):
    """If OLLAMA_MODEL is unset or default, try to pick a preferred exaone model from the server."""
    global OLLAMA_MODEL
    try:
        models = _list_ollama_models()
    except Exception:
        return

    # Flatten ids
    ids = [m.get("id") for m in models if isinstance(m, dict) and m.get("id")]
    # If user already set a non-default model, keep it
    if OLLAMA_MODEL and OLLAMA_MODEL != "exaone":
        return

    # Preferred order
    prefer = preferred or [
        "exaone3.5:7.8b",
        "exaone3.5:2.4b",
        "exaone-deep:7.8b",
        "hf.co/LGAI-EXAONE/EXAONE-4.0-1.2B-GGUF:Q4_K_M",
        "exaone",
    ]

    for p in prefer:
        for mid in ids:
            if mid and mid.startswith(p):
                OLLAMA_MODEL = mid
                print(f"Auto-selected Ollama model: {OLLAMA_MODEL}")
                return


def _parse_model_output(text: str):
    """Try to extract JSON from model output.
    - First look for ```json ... ``` or ``` ... ``` code fences and parse the inside.
    - Then look for a JSON object substring and parse it.
    Returns parsed object or None.
    """
    if not text or not isinstance(text, str):
        return None

    # look for fenced code blocks
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    candidate = None
    if fence_match:
        candidate = fence_match.group(1).strip()
        try:
            return json.loads(candidate)
        except Exception:
            # continue to other heuristics
            pass

    # fallback: find first {...} JSON-like substring
    brace_match = re.search(r"(\{[\s\S]*\})", text)
    if brace_match:
        candidate = brace_match.group(1)
        try:
            return json.loads(candidate)
        except Exception:
            pass

    return None


def _ensure_wav_16k_mono(src_path: str, dst_path: str):
    """Use ffmpeg (must be installed) to convert audio to 16k mono WAV for VOSK."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        src_path,
        "-ar",
        "16000",
        "-ac",
        "1",
        dst_path,
    ]
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _transcribe_with_vosk(wav_path: str, model_path: str) -> str:
    try:
        from vosk import Model, KaldiRecognizer
    except Exception as e:
        raise RuntimeError("VOSK package not available: " + str(e))

    if not os.path.exists(model_path):
        raise RuntimeError(f"VOSK model path not found: {model_path}")

    wf = wave.open(wav_path, "rb")
    if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 16000:
        raise RuntimeError("WAV file not in required format (16k mono 16-bit)")

    model = Model(model_path)
    rec = KaldiRecognizer(model, wf.getframerate())
    rec.SetWords(True)

    results = []
    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            j = json.loads(rec.Result())
            results.append(j.get("text", ""))
    # final
    j = json.loads(rec.FinalResult())
    results.append(j.get("text", ""))
    wf.close()
    return " ".join([r for r in results if r])


app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
def startup_event():
    # If using Ollama, try to auto-select a suitable model when app starts
    if MODEL_BACKEND == "ollama":
        try:
            _auto_select_ollama_model()
        except Exception as e:
            print(f"Ollama auto-select failed: {e}")

# ==========================================
# 학습 데이터 로드 헬퍼 함수
# ==========================================
def load_json_data(filename):
    """Load JSON data from data/ directory"""
    try:
        with open(f"data/{filename}", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return []

# ==========================================
# 페이지 라우트 (Routes)
# ==========================================
@app.get("/")
def home_dashboard(request: Request):
    """대시보드 홈페이지"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/learning")
def learning_page(request: Request):
    """기존 AI 학습 도구 (콘텐츠 생성, 발음 교정, 작문 테스트)"""
    return templates.TemplateResponse("learning.html", {"request": request})

@app.get("/word-puzzle")
def word_puzzle_page(request: Request):
    """단어 순서 맞추기 게임"""
    return templates.TemplateResponse("word-puzzle.html", {"request": request})

@app.get("/daily-expression")
def daily_expression_page(request: Request):
    """오늘의 한국어 표현 카드 슬라이더"""
    return templates.TemplateResponse("daily-expression.html", {"request": request})

@app.get("/vocab-garden")
def vocab_garden_page(request: Request):
    """단어 꽃밭 (Vocabulary Garden)"""
    return templates.TemplateResponse("vocab-garden.html", {"request": request})

@app.get("/pronunciation-practice")
def pronunciation_practice_page(request: Request):
    """발음 연습 (ELSA Speak 스타일 2-Step: Listen → Speak)"""
    return templates.TemplateResponse("pronunciation-practice.html", {"request": request})

# ==========================================
# 2. AI 학습 콘텐츠 자동 생성 API
# ==========================================
@app.post("/api/generate-content")
async def generate_content(topic: str = Form(...), level: str = Form(...), model: str = Form(None)):
    prompt = f"""
    한국어 선생님입니다.
    주제: '{topic}'
    레벨: '{level}'
    
    위 조건에 맞는 짧은 한국어 대화문(3~4마디)과 주요 단어 3개를 JSON 형식으로 만들어주세요.
    형식:
    {{
        "dialogue": [
            {{"speaker": "A", "text": "한국어 문장", "pronunciation": "발음 표기"}},
            {{"speaker": "B", "text": "한국어 문장", "pronunciation": "발음 표기"}}
        ],
        "vocabulary": ["단어1", "단어2", "단어3"]
    }}
    """
    
    # Use Ollama local backend if configured
    if MODEL_BACKEND == "ollama":
        try:
            use_model = model or OLLAMA_MODEL
            payload = {"model": use_model, "prompt": prompt}
            resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, stream=True, timeout=30)
            if resp.status_code != 200:
                return JSONResponse(status_code=500, content={"error": "ollama generate failed", "status": resp.status_code, "body": resp.text})

            out = ""
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        out += obj.get("response", "") or obj.get("text", "")
                    else:
                        out += str(obj)
                except Exception:
                    out += line

            parsed = _parse_model_output(out)
            if parsed is not None:
                return JSONResponse(content=parsed)
            return JSONResponse(content={"text": out})
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": "generate-content (ollama) failed", "details": str(e)})

    # Fallback / default: OpenAI (disabled)
    return JSONResponse(status_code=501, content={"error": "OpenAI integration is disabled in this deployment"})


@app.get("/api/ollama/models")
def get_ollama_models():
    """Proxy endpoint to list Ollama models available on the local server."""
    try:
        models = _list_ollama_models()
        return JSONResponse(content={"models": models})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "failed to list ollama models", "details": str(e)})


@app.post("/api/ollama/test")
async def ollama_test(prompt: str = Form(...), model: str = Form(None)):
    """Send a quick test prompt to the selected Ollama model and return the raw text."""
    if MODEL_BACKEND != "ollama":
        return JSONResponse(status_code=400, content={"error": "MODEL_BACKEND is not set to 'ollama'"})

    use_model = model or OLLAMA_MODEL
    try:
        payload = {"model": use_model, "prompt": prompt}
        resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, stream=True, timeout=30)
        if resp.status_code != 200:
            return JSONResponse(status_code=500, content={"error": "ollama generate failed", "status": resp.status_code, "body": resp.text})

        out = ""
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    out += obj.get("response", "") or obj.get("text", "")
                else:
                    out += str(obj)
            except Exception:
                out += line

        parsed = _parse_model_output(out)
        if parsed is not None:
            return JSONResponse(content={"model": use_model, "parsed": parsed})
        return JSONResponse(content={"model": use_model, "text": out})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "ollama test failed", "details": str(e)})

# ==========================================
# 3. 유창성 테스트 (작문 교정) API
# ==========================================
@app.post("/api/fluency-check")
async def fluency_check(user_text: str = Form(...)):
    prompt = f"""
    사용자가 쓴 한국어 문장입니다: "{user_text}"
    
    이 문장의 자연스러움을 100점 만점으로 평가하고, 
    교정된 문장과 피드백을 한국어로 짧게 주세요.
    JSON 형식: {{"score": 85, "corrected": "...", "feedback": "..."}}
    """
    
    # Use Ollama backend if configured
    if MODEL_BACKEND == "ollama":
        try:
            payload = {"model": OLLAMA_MODEL, "prompt": prompt}
            resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, stream=True, timeout=30)
            if resp.status_code != 200:
                return JSONResponse(status_code=500, content={"error": "ollama generate failed", "status": resp.status_code, "body": resp.text})

            out = ""
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        out += obj.get("response", "") or obj.get("text", "")
                    else:
                        out += str(obj)
                except Exception:
                    out += line

            parsed = _parse_model_output(out)
            if parsed is not None:
                return JSONResponse(content=parsed)
            return JSONResponse(content={"text": out})
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": "fluency-check (ollama) failed", "details": str(e)})

    # Fallback / default: OpenAI (disabled)
    return JSONResponse(status_code=501, content={"error": "OpenAI integration is disabled in this deployment"})

# ==========================================
# 4. 발음 교정 API (음성 업로드 -> STT -> 비교)
# ==========================================
@app.post("/api/pronunciation-check")
async def pronunciation_check(target_text: str = Form(...), file: UploadFile = File(...)):
    # 파일 업로드 검증 및 저장 (MVP 수준)
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
    ALLOWED_TYPES = {
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/webm",
        "audio/ogg",
        "audio/mp4",
        "audio/x-m4a",
    }

    if file.content_type not in ALLOWED_TYPES:
        return JSONResponse(status_code=415, content={"error": "Unsupported media type"})

    # OpenAI-based Whisper STT is disabled when OpenAI integration is commented out.
    if client is None:
        # Try local STT if configured
        local_stt = os.getenv("LOCAL_STT", "").lower()
        if local_stt == "vosk":
            vosk_model_path = os.getenv("VOSK_MODEL_PATH")
            if not vosk_model_path:
                return JSONResponse(status_code=501, content={"error": "VOSK model path not configured (VOSK_MODEL_PATH)"})

            # convert uploaded file to 16k mono wav for VOSK
            converted = file_location + ".vsk.wav"
            try:
                _ensure_wav_16k_mono(file_location, converted)
                transcript_text = _transcribe_with_vosk(converted, vosk_model_path)
                try:
                    os.remove(converted)
                except Exception:
                    pass

                user_said = transcript_text
            except Exception as e:
                try:
                    if os.path.exists(file_location):
                        os.remove(file_location)
                except Exception:
                    pass
                return JSONResponse(status_code=500, content={"error": "local STT failed", "details": str(e)})
        else:
            return JSONResponse(status_code=501, content={"error": "OpenAI Whisper STT is disabled in this deployment"})

    file_location = f"temp_{file.filename}"
    size = 0
    try:
        # stream-write to disk with size limit
        with open(file_location, "wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    await file.close()
                    buffer.close()
                    try:
                        os.remove(file_location)
                    except Exception:
                        pass
                    return JSONResponse(status_code=413, content={"error": "File too large"})
                buffer.write(chunk)

        # 2. OpenAI Whisper로 음성 -> 텍스트 변환 (STT)
        audio_file = open(file_location, "rb")
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="ko"
        )
        user_said = getattr(transcript, "text", None) or transcript.get("text") if isinstance(transcript, dict) else None
        if user_said is None:
            user_said = ""

        # 3. 유사도 검사 (간단한 MVP용 알고리즘)
        matcher = SequenceMatcher(None, target_text.replace(" ", ""), user_said.replace(" ", ""))
        similarity = matcher.ratio() * 100  # 0~100점

        return {
            "user_said": user_said,
            "target_text": target_text,
            "score": round(similarity, 1),
            "feedback": "완벽해요!" if similarity > 90 else "조금 더 또박또박 말해보세요."
        }

    except Exception as e:
        try:
            if os.path.exists(file_location):
                os.remove(file_location)
        except Exception:
            pass
        return JSONResponse(status_code=500, content={"error": "pronunciation processing failed", "details": str(e)})
    finally:
        try:
            await file.close()
        except Exception:
            pass
        try:
            audio_file.close()
        except Exception:
            pass
        try:
            if os.path.exists(file_location):
                os.remove(file_location)
        except Exception:
            pass

# ==========================================
# 학습 게임 API 엔드포인트
# ==========================================

# Word Puzzle APIs
@app.get("/api/puzzle/sentences")
async def get_puzzle_sentences(level: str = None):
    """Get word puzzle sentences, optionally filtered by CEFR level"""
    try:
        sentences = load_json_data("sentences.json")
        if level:
            sentences = [s for s in sentences if s.get("level") == level.upper()]
        return JSONResponse(content={"sentences": sentences})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to load sentences", "details": str(e)})

@app.get("/api/puzzle/sentences/{sentence_id}")
async def get_puzzle_sentence(sentence_id: int):
    """Get a specific sentence by ID"""
    try:
        sentences = load_json_data("sentences.json")
        sentence = next((s for s in sentences if s.get("id") == sentence_id), None)
        if sentence:
            return JSONResponse(content=sentence)
        return JSONResponse(status_code=404, content={"error": "Sentence not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to load sentence", "details": str(e)})

# Daily Expression APIs
@app.get("/api/expressions")
async def get_expressions(level: str = None):
    """Get all expressions, optionally filtered by CEFR level"""
    try:
        expressions = load_json_data("expressions.json")
        if level:
            expressions = [e for e in expressions if e.get("level") == level.upper()]
        return JSONResponse(content={"expressions": expressions})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to load expressions", "details": str(e)})

@app.get("/api/expressions/today")
async def get_today_expression():
    """Get today's expression (cycles through available expressions)"""
    try:
        import datetime
        expressions = load_json_data("expressions.json")
        if not expressions:
            return JSONResponse(status_code=404, content={"error": "No expressions available"})

        # Use day of year to cycle through expressions
        day_of_year = datetime.datetime.now().timetuple().tm_yday
        index = day_of_year % len(expressions)
        return JSONResponse(content=expressions[index])
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to get today's expression", "details": str(e)})

# Vocabulary Garden APIs
@app.get("/api/vocabulary")
async def get_vocabulary(level: str = None):
    """Get all vocabulary words, optionally filtered by CEFR level"""
    try:
        vocabulary = load_json_data("vocabulary.json")
        if level:
            vocabulary = [v for v in vocabulary if v.get("level") == level.upper()]
        return JSONResponse(content={"vocabulary": vocabulary})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to load vocabulary", "details": str(e)})

@app.get("/api/vocabulary/{word_id}")
async def get_vocabulary_word(word_id: str):
    """Get a specific vocabulary word by ID"""
    try:
        vocabulary = load_json_data("vocabulary.json")
        word = next((v for v in vocabulary if v.get("id") == word_id), None)
        if word:
            return JSONResponse(content=word)
        return JSONResponse(status_code=404, content={"error": "Word not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to load vocabulary word", "details": str(e)})

# Pronunciation Practice APIs
@app.get("/api/pronunciation-words")
async def get_pronunciation_words(level: str = None):
    """Get pronunciation practice words, optionally filtered by CEFR level"""
    try:
        words = load_json_data("pronunciation-words.json")
        if level:
            words = [w for w in words if w.get("level") == level.upper()]
        return JSONResponse(content={"words": words})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to load pronunciation words", "details": str(e)})

@app.get("/api/pronunciation-words/{word_id}")
async def get_pronunciation_word(word_id: str):
    """Get a specific pronunciation word by ID"""
    try:
        words = load_json_data("pronunciation-words.json")
        word = next((w for w in words if w.get("id") == word_id), None)
        if word:
            return JSONResponse(content=word)
        return JSONResponse(status_code=404, content={"error": "Word not found"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to load pronunciation word", "details": str(e)})

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=9000, reload=True)