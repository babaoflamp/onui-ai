# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**오누이 한국어 (Onui Korean)** - A comprehensive Korean language learning web application with AI-powered content generation, interactive learning games, and pronunciation practice. Uses local LLM models (Ollama with EXAONE) or OpenAI API for AI features.

**Stack**: FastAPI backend with Jinja2 templates, vanilla JavaScript frontend, Python 3.8+

**Project Roadmap** (see `docs/requirements/site_structure.png`):

The platform is designed with 4 major product lines:

1. **ONUI Korean (공통 영역)** - Core learning features ✅ *Partially Implemented*
   - Dashboard / Home
   - Today's Korean Expression (5번: 카드 슬라이더) ✅ `/daily-expression`
   - Vocabulary Flower Garden (3번: Vocabulary Flower Garden) ✅ `/vocab-garden`
   - Word Order Puzzle (4번: Word Order Puzzle) ✅ `/word-puzzle`

2. **ONUI Korean TOPIK (시험 대비 라인)** - TOPIK exam preparation 🚧 *Planned*
   - Mock exam creation/grading
   - Today's notes/explanations
   - Grammar/vocabulary weak point analysis
   - Writing review (AI scoring)

3. **ONUI Korean Pronunciation (발음 교정 라인)** - Pronunciation training 🚧 *Planned*
   - Sentence follow-along
   - Pronunciation feedback (pitch, rhythm)
   - Shadowing mode
   - Pronunciation report (improvement tracking)

4. **ONUI Family Korean (다문화·가족용 라인)** - Family/multicultural content 🚧 *Planned*
   - Child learning (drawing, story-based learning)
   - Parent mode (educational monitoring/progress tracking)
   - Family mission board
   - School life essential expression collection

**Currently Implemented Features** (Phase 1):
1. **AI Learning Tools** (`/learning`) - Custom content generation, pronunciation checking, fluency testing
2. **Word Puzzle** (`/word-puzzle`) - Drag-and-drop sentence ordering game with CEFR levels
3. **Daily Expression** (`/daily-expression`) - Rotating Korean expression cards with cultural context
4. **Vocabulary Garden** (`/vocab-garden`) - Emoji-based vocabulary learning with multiple CEFR levels
5. **Pronunciation Practice** (`/pronunciation-practice`) - ELSA Speak-style 2-step interface (Listen → Speak) with TTS and speech evaluation

## Quick Start

### First-time Setup

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) Korean romanizer for better Latin pronunciation
pip install korean-romanizer

# 4. Setup environment (or use existing .env)
# See Environment Configuration section below

# 5. Start the application
uvicorn main:app --host 0.0.0.0 --port 9000 --reload
# Or simply: python main.py
```

**Access**: `http://localhost:9000`

### Common Commands

```bash
# Development server with auto-reload
uvicorn main:app --host 0.0.0.0 --port 9000 --reload
python main.py  # Alternative (runs uvicorn internally)

# Background execution
python main.py &

# Stop the application
pkill -f uvicorn

# Activate virtual environment
source .venv/bin/activate

# Install new dependency
pip install <package>
pip freeze > requirements.txt  # Update requirements file
```

## Architecture

### Backend Structure (main.py)

**Single-file FastAPI application** with all backend logic in `main.py` (780 lines). All routes, business logic, and API integrations are in this file.

**Page Routes** (return Jinja2 templates):
- `GET /` - Dashboard homepage (`index.html`)
- `GET /learning` - AI learning tools (`learning.html`)
- `GET /word-puzzle` - Sentence ordering game (`word-puzzle.html`)
- `GET /daily-expression` - Expression cards (`daily-expression.html`)
- `GET /vocab-garden` - Vocabulary learning (`vocab-garden.html`)
- `GET /pronunciation-practice` - Pronunciation practice (`pronunciation-practice.html`)

**AI Learning APIs** (used by `/learning` page):
- `POST /api/generate-content` - Generate Korean dialogue + vocabulary JSON
  - Inputs: `topic` (str), `level` (초급/중급/고급), `model` (optional str)
  - Returns: `{"dialogue": [...], "vocabulary": [...]}`
  - Uses Ollama or OpenAI (disabled by default)
- `POST /api/pronunciation-check` - Evaluate speech recording
  - Inputs: `target_text` (str), `file` (audio upload, max 5MB)
  - Uses Whisper API or VOSK (local)
  - Returns: `{"user_said": "...", "score": 85.3, "feedback": "..."}`
- `POST /api/fluency-check` - Evaluate written Korean
  - Inputs: `user_text` (str)
  - Returns: `{"score": 85, "corrected": "...", "feedback": "..."}`

**Learning Game APIs** (load JSON data from `data/` directory):
- `GET /api/puzzle/sentences[?level=A1]` - Word puzzle sentences
- `GET /api/puzzle/sentences/{id}` - Specific sentence
- `GET /api/expressions[?level=A1]` - All expressions
- `GET /api/expressions/today` - Today's expression (cycles by day of year)
- `GET /api/vocabulary[?level=A1]` - Vocabulary words
- `GET /api/vocabulary/{word_id}` - Specific word
- `GET /api/pronunciation-words[?level=A1]` - Pronunciation practice words
- `GET /api/pronunciation-words/{word_id}` - Specific pronunciation word

**Ollama Helper APIs**:
- `GET /api/ollama/models` - List available Ollama models
- `POST /api/ollama/test` - Test model with custom prompt (debugging)

### Model Backend System

The application supports **dual backend modes** via `MODEL_BACKEND` environment variable:

**Ollama Backend** (`MODEL_BACKEND=ollama`, default):
- Uses local Ollama server at `OLLAMA_URL` (default: `http://localhost:11434`)
- **Auto-selects** best available EXAONE model at startup via `_auto_select_ollama_model()`:
  - Preferred order: `exaone3.5:7.8b` → `exaone3.5:2.4b` → `exaone-deep:7.8b` → others
- Streams responses as newline-delimited JSON: `{"response": "chunk", "done": false}`
- Concatenates all `response` fields and parses final JSON
- **Retry logic**: If initial parse fails, sends strict re-prompt requesting single JSON code block

**OpenAI Backend** (`MODEL_BACKEND=openai`):
- **Currently disabled** (import commented out, `client = None`)
- Would use OpenAI API if `OPENAI_API_KEY` is set
- Whisper STT for pronunciation checking (also disabled when client is None)
- To re-enable: uncomment `from openai import OpenAI` and restore `client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None`

### Korean Romanization System

**Purpose**: Ensure consistent Latin-script pronunciations in AI-generated dialogue, even when the LLM fails to provide proper romanization.

**Implementation** (main.py:17-76):
- First tries to import `korean_romanizer` package (optional dependency)
- Falls back to built-in syllable-based romanizer if package not available
- Built-in romanizer uses lookup tables for initial consonants, medial vowels, and final consonants (Revised Romanization approximation)

**Behavior controlled by `ROMANIZE_MODE` env var**:
- `ROMANIZE_MODE=force` (default) - Always replace `pronunciation` field with romanizer output for consistency
- `ROMANIZE_MODE=prefer` - Keep model-provided Latin pronunciation if valid (contains ASCII letters, no Hangul); otherwise romanize

**Applied in** `/api/generate-content` response post-processing (main.py:407-456):
- Checks each dialogue item's `pronunciation` field
- Normalizes whitespace (collapses newlines/tabs into single spaces)
- Ensures all pronunciations are Latin-only, no Hangul

### Model Output Parsing

**Key function**: `_parse_model_output(text)` (main.py:139-168)

**Parsing strategy** (in order):
1. Extract JSON from code fences: ````json ... ```` or ```` ``` ````
2. Fallback: regex search for first `{...}` JSON object in text
3. Returns parsed dict or `None` if both fail

**Why this is critical**: LLMs often prepend commentary or wrap JSON in markdown code blocks. The parser handles these variations robustly.

**Used by**:
- `/api/generate-content` (with fallback to dialogue-specific regex and retry logic)
- `/api/fluency-check`
- `/api/ollama/test`

### Audio Processing Pipeline

**For pronunciation checking** (`/api/pronunciation-check`, main.py:564-674):

1. **Upload validation**:
   - Max file size: 5MB
   - Allowed types: WAV, MP3, WebM, OGG, MP4, M4A
   - Saves to temporary file: `temp_{filename}`

2. **Speech-to-text**:
   - **If OpenAI enabled**: Uses Whisper API (`whisper-1` model, language=`ko`)
   - **If VOSK enabled** (`LOCAL_STT=vosk`):
     - Converts to 16kHz mono WAV via `_ensure_wav_16k_mono()` (uses ffmpeg)
     - Transcribes via `_transcribe_with_vosk()` (loads VOSK model, processes in 4000-frame chunks)

3. **Similarity evaluation**:
   - Uses `difflib.SequenceMatcher` to compare transcription to target text (spaces removed)
   - Calculates similarity ratio (0-1) and converts to 0-100 score
   - Provides binary feedback: "완벽해요!" if score > 90, else "조금 더 또박또박 말해보세요."

4. **Cleanup**:
   - All temporary files deleted in `finally` block (prevents disk bloat)

**Important**: File cleanup is critical - the endpoint creates temporary files that must be deleted on success, failure, or exception.

### Frontend Architecture

**Multi-page application** with shared base template (`templates/base.html`) and 5 feature pages.

**Base Template** (`base.html`, 164 lines):
- Tailwind CSS via CDN
- Pretendard font for Korean text
- Responsive navigation bar with active page highlighting
- Character icons: 남동생 (brother) 👦 and 여동생 (sister) 👧
- Shared CSS: `/static/css/{page}.css`
- Shared JS: `/static/js/{page}.js`

**Page-specific templates**:
1. **`index.html`** (234 lines) - Dashboard with hero section, feature cards, and grid layout
2. **`learning.html`** (970 lines) - AI learning tools with 3 sections (content generation, pronunciation, fluency)
3. **`word-puzzle.html`** (74 lines) - Drag-and-drop sentence ordering game
4. **`daily-expression.html`** (71 lines) - Expression card slider
5. **`vocab-garden.html`** (74 lines) - Vocabulary flashcards with emoji visual aids
6. **`pronunciation-practice.html`** (157 lines) - ELSA-style 2-step practice (Listen → Speak)

**JavaScript modules** (`/static/js/`):
- Each page has dedicated JS file (100-250 lines)
- **Common patterns**:
  - IIFE (Immediately Invoked Function Expression) to avoid global scope pollution
  - Async/await for all API calls
  - State management with module-scoped variables
  - DOM element caching at module initialization
- **Key features**:
  - `pronunciation-practice.js` - MediaRecorder API for audio recording, Web Speech API for TTS
  - `learning.html` (inline JS) - Ollama model selection, content generation, pronunciation/fluency checking
  - `word-puzzle.js`, `daily-expression.js`, `vocab-garden.js` - Data loading and interactive UI

**CSS modules** (`/static/css/`):
- Page-specific styling (not shared)
- Tailwind utility classes in templates, custom CSS for animations and complex layouts
- `pronunciation-practice.css` (208 lines) - ELSA-style interface with step indicators and bubble animations

### Data Files (`/data/`)

All learning content stored as JSON files loaded by API endpoints:

1. **`sentences.json`** (26 sentences) - Word puzzle content
   - Schema: `{id, text, words[], translation, level (A1/A2/B1), category}`
   - Example: `{"id": 1, "text": "나는 학생입니다", "words": ["나는", "학생입니다"], ...}`

2. **`expressions.json`** (15 expressions) - Daily expression cards
   - Schema: `{id, korean, romanization, english, explanation, culturalNote, level, category, examples[], relatedExpressions[]}`
   - Example: `{"korean": "밥 먹었어요?", "english": "Have you eaten?", ...}`

3. **`vocabulary.json`** (20 words) - Vocabulary garden words
   - Schema: `{id, word, emoji, meaning, romanization, level, example, category}`
   - Example: `{"id": "flower", "word": "꽃", "emoji": "🌸", "meaning": "Flower", ...}`

4. **`pronunciation-words.json`** (20 words) - Pronunciation practice words
   - Schema: `{id, word, roman, meaningKo, meaningEn, level (A1/A2), phonemes[], tips}`
   - Example: `{"id": "annyeong", "word": "안녕하세요", "roman": "an-nyeong-ha-se-yo", "phonemes": ["안", "녕", "하", "세", "요"], "tips": "'하세요'는 빠르게 연결해서 발음하세요.", ...}`

**Data loading pattern**:
```python
def load_json_data(filename):
    with open(f"data/{filename}", "r", encoding="utf-8") as f:
        return json.load(f)
```

Used by all learning game APIs to load data on demand (not cached).

## Environment Configuration

**`.env` file** (exists in repository):

```bash
# Backend selection: 'openai' or 'ollama'
MODEL_BACKEND=ollama

# Ollama settings (when MODEL_BACKEND=ollama)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=exaone3.5:2.4b  # Or leave blank for auto-selection

# OpenAI settings (when MODEL_BACKEND=openai, currently disabled)
OPENAI_API_KEY=

# Local STT with VOSK (alternative to Whisper)
LOCAL_STT=vosk  # Set to 'vosk' to enable
VOSK_MODEL_PATH=/path/to/vosk-model-ko  # Required if LOCAL_STT=vosk

# Korean romanization mode (for AI-generated content)
ROMANIZE_MODE=force  # Options: 'force' (default), 'prefer'
```

**Important notes**:
- `.env` file exists in repository but should not contain sensitive keys in production
- Ollama must be running locally if `MODEL_BACKEND=ollama`
- VOSK requires downloading Korean model separately (e.g., vosk-model-ko-0.22)
- ffmpeg must be installed for VOSK audio conversion
- `korean-romanizer` package is optional but recommended (`pip install korean-romanizer`)

## Dependencies

**Core packages** (`requirements.txt`):
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `python-multipart` - Form/file upload handling
- `openai==0.27.8` - OpenAI API (pinned to avoid `jiter` dependency issue)
- `python-dotenv` - Environment variable loading
- `requests` - HTTP client for Ollama API
- `jinja2` - Template rendering
- `vosk` - Local speech-to-text (optional)

**Optional packages** (install separately):
- `korean-romanizer` - For accurate Korean → Latin romanization (recommended)

**External requirements**:
- ffmpeg (system package) - Required for VOSK audio conversion
- Ollama server with EXAONE models - Required if using local backend

## Common Development Patterns

### Adding a New Learning Game Page

1. **Create data file** in `data/`:
```json
// data/new-game.json
[
  {"id": "item1", "content": "...", "level": "A1"},
  {"id": "item2", "content": "...", "level": "A2"}
]
```

2. **Add API endpoints** in `main.py`:
```python
@app.get("/new-game")
def new_game_page(request: Request):
    return templates.TemplateResponse("new-game.html", {"request": request})

@app.get("/api/new-game")
async def get_new_game_data(level: str = None):
    try:
        data = load_json_data("new-game.json")
        if level:
            data = [item for item in data if item.get("level") == level.upper()]
        return JSONResponse(content={"data": data})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "Failed to load data", "details": str(e)})
```

3. **Create template** in `templates/`:
```html
<!-- templates/new-game.html -->
{% extends "base.html" %}
{% block title %}New Game - 오누이 한국어{% endblock %}
{% block styles %}
<link rel="stylesheet" href="/static/css/new-game.css">
{% endblock %}
{% block content %}
<!-- Game UI here -->
{% endblock %}
{% block scripts %}
<script src="/static/js/new-game.js"></script>
{% endblock %}
```

4. **Create JavaScript** in `static/js/`:
```javascript
// static/js/new-game.js
(function() {
  'use strict';

  async function loadGameData() {
    const response = await fetch('/api/new-game');
    const data = await response.json();
    // Render UI
  }

  loadGameData();
})();
```

5. **Create CSS** in `static/css/`:
```css
/* static/css/new-game.css */
.game-container {
  /* Styles here */
}
```

6. **Update navigation** in `templates/base.html` to add menu link.

### Working with AI Content Generation

**Testing Ollama availability**:
```bash
# List models on Ollama server
curl http://localhost:11434/v1/models

# Test generation
curl -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model": "exaone3.5:7.8b", "prompt": "안녕하세요"}'
```

**Ollama response format** (newline-delimited JSON stream):
```json
{"response": "text chunk 1", "done": false}
{"response": "text chunk 2", "done": false}
{"response": "", "done": true}
```

**Parsing pattern** in code:
```python
out = ""
for line in resp.iter_lines(decode_unicode=True):
    if not line:
        continue
    obj = json.loads(line)
    out += obj.get("response", "")

parsed = _parse_model_output(out)  # Extract JSON from markdown
```

**Prompt engineering tips** (from `/api/generate-content` implementation):
- Always request JSON output in code fences: "응답은 반드시 마지막에 하나의 JSON 객체만 포함된 코드 블럭(```json ... ``` )으로 정확하게 반환하세요."
- Include level-specific guidance (초급/중급/고급) to tailor vocabulary and sentence complexity
- Request romanized pronunciation: "발음 표기는 한국어 발음을 이해하기 쉬운 영문 로마자(라틴 알파벳)로 표기해 주세요."
- Implement retry logic if parsing fails (see main.py:359-404)

### Audio Recording and Pronunciation Checking

**Frontend pattern** (MediaRecorder API):
```javascript
let mediaRecorder, audioChunks = [];

// Start recording
navigator.mediaDevices.getUserMedia({ audio: true })
  .then(stream => {
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
    mediaRecorder.onstop = async () => {
      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
      const formData = new FormData();
      formData.append('file', audioBlob, 'recording.webm');
      formData.append('target_text', targetText);

      const response = await fetch('/api/pronunciation-check', {
        method: 'POST',
        body: formData
      });
      const result = await response.json();
      // Display score and feedback
    };
    mediaRecorder.start();
  });

// Stop recording
mediaRecorder.stop();
```

**Backend validation** (main.py:564-674):
- Check `file.content_type` against `ALLOWED_TYPES` set
- Stream upload with size limit (5MB max)
- Always clean up temporary files in `finally` block

### Error Handling Pattern

All API endpoints follow this pattern:
```python
@app.post("/api/endpoint")
async def endpoint_handler(param: str = Form(...)):
    try:
        # Main logic
        result = process(param)
        return JSONResponse(content={"success": True, "data": result})
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": "description", "details": str(e)}
        )
```

Frontend displays error messages from `error` and `details` fields.

## Troubleshooting

### Ollama Connection Issues

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama (installation-dependent)
ollama serve

# Verify EXAONE model is installed
ollama list | grep exaone
ollama pull exaone3.5:7.8b  # If missing
ollama pull exaone3.5:2.4b  # Smaller alternative

# Test model response
curl -X POST http://localhost:11434/api/generate \
  -d '{"model": "exaone3.5:2.4b", "prompt": "Hello"}' \
  -H "Content-Type: application/json"
```

### VOSK Setup for Local STT

```bash
# Download Korean VOSK model
wget https://alphacephei.com/vosk/models/vosk-model-ko-0.22.zip
unzip vosk-model-ko-0.22.zip

# Set environment variable
export VOSK_MODEL_PATH=/path/to/vosk-model-ko-0.22
export LOCAL_STT=vosk

# Ensure ffmpeg is installed
ffmpeg -version
# Ubuntu/Debian: sudo apt-get install ffmpeg
# macOS: brew install ffmpeg
```

### Audio Recording Not Working

**Common issues**:
1. Browser requires HTTPS for `getUserMedia` (except localhost)
2. Microphone permissions blocked - check browser settings (chrome://settings/content/microphone)
3. MediaRecorder not supported - requires Chrome 49+, Firefox 25+, Safari 14+
4. File size limit exceeded - recordings limited to 5MB
5. CORS issues - ensure frontend and backend are same origin or CORS is configured

### Model Output Parsing Failures

If `_parse_model_output()` returns None:
1. **Check raw output**: Use `/api/ollama/test` endpoint to see model's actual response
2. **Inspect model behavior**: Model may not be following JSON format instruction
3. **Adjust prompt**: Make JSON request more explicit or add examples
4. **Try different model**: Some models handle structured output better than others
5. **Check for retry**: `/api/generate-content` has built-in retry logic (main.py:371-404)

### Virtual Environment Issues

```bash
# If you see "bad interpreter" error:
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# If specific package fails:
pip install --upgrade pip
pip install <package-name> --no-cache-dir
```

### Data Loading Errors

**If API returns "Failed to load data"**:
1. Verify JSON file exists in `data/` directory
2. Check JSON syntax: `python -m json.tool data/filename.json`
3. Ensure UTF-8 encoding (required for Korean text)
4. Check file permissions: `ls -la data/`

## Project Structure

```
onui-ai/
├── main.py                          # FastAPI app (all backend logic, 780 lines)
├── requirements.txt                 # Python dependencies
├── .env                             # Environment config (in repo, no secrets)
├── README.md                        # User-facing documentation (Korean)
├── CLAUDE.md                        # Developer documentation (this file)
│
├── templates/                       # Jinja2 HTML templates
│   ├── base.html                   # Shared layout (navigation, fonts, 164 lines)
│   ├── index.html                  # Dashboard homepage (234 lines)
│   ├── learning.html               # AI learning tools (970 lines)
│   ├── word-puzzle.html            # Sentence ordering game (74 lines)
│   ├── daily-expression.html       # Expression cards (71 lines)
│   ├── vocab-garden.html           # Vocabulary flashcards (74 lines)
│   └── pronunciation-practice.html # ELSA-style practice (157 lines)
│
├── static/                         # Static assets
│   ├── css/                        # Page-specific CSS
│   │   ├── word-puzzle.css         # (110 lines)
│   │   ├── daily-expression.css    # (77 lines)
│   │   ├── vocab-garden.css        # (104 lines)
│   │   └── pronunciation-practice.css  # (208 lines)
│   └── js/                         # Page-specific JavaScript
│       ├── word-puzzle.js          # (150 lines)
│       ├── daily-expression.js     # (100 lines)
│       ├── vocab-garden.js         # (180 lines)
│       └── pronunciation-practice.js  # (250 lines)
│
├── data/                           # JSON learning content
│   ├── sentences.json              # Word puzzle data (26 sentences)
│   ├── expressions.json            # Daily expressions (15 items)
│   ├── vocabulary.json             # Vocabulary words (20 items)
│   └── pronunciation-words.json    # Pronunciation practice (20 items)
│
├── docs/                           # Design mockups and requirements
│   ├── design/                     # HTML mockups
│   └── requirements/               # Project specs
│
├── .venv/                          # Python virtual environment
├── configs/                        # (empty, future use)
├── scripts/                        # (empty, future use)
└── tests/                          # (empty, future use)
```

**Note on architecture**: All backend logic is in single `main.py` file (780 lines). For future scaling, consider refactoring into:
- `routers/` - API route modules (e.g., `ai_routes.py`, `game_routes.py`)
- `services/` - Business logic (e.g., `ollama_service.py`, `stt_service.py`, `romanizer.py`)
- `utils/` - Helper functions (e.g., `parsers.py`, `audio_processing.py`)
- `models/` - Pydantic models for request/response validation

## OpenAI Integration (Currently Disabled)

The codebase has OpenAI support **commented out**:
- Import at top of `main.py` is commented: `# from openai import OpenAI` (line 7)
- Client initialization: `client = None` (line 86)
- Whisper STT for pronunciation checking is disabled (main.py:583-610)

**To re-enable OpenAI**:
1. Uncomment import: `from openai import OpenAI`
2. Restore client initialization: `client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None`
3. Set `MODEL_BACKEND=openai` in `.env`
4. Set `OPENAI_API_KEY` in `.env`

**Reason for disabling**: Project uses local Ollama backend by default to avoid API costs and enable offline operation. Only Whisper STT is still occasionally used if OpenAI client is enabled.
