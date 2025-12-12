# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**오누이 한국어 (Onui Korean)** - A Korean language learning web application featuring AI-powered content generation, professional pronunciation evaluation (SpeechPro), fluency analysis (FluencyPro), interactive learning games, and progress tracking.

**Stack**: FastAPI backend (Python 3.8+), Jinja2 templates, vanilla JavaScript frontend, SQLite database

**Current Status**: Active development with production deployment via systemd service and ngrok tunneling.

## Quick Start

### Development Setup

```bash
# 1. Virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Optional: Korean romanizer for pronunciation
pip install korean-romanizer

# 4. Start development server
uvicorn main:app --host 0.0.0.0 --port 9000 --reload
# Or: python main.py
```

**Access**: `http://localhost:9000`

### Production Deployment

```bash
# Start all services (FastAPI + ngrok)
./start-service.sh

# Stop all services
./stop-service.sh

# View logs
tail -f logs/uvicorn.log
tail -f logs/ngrok.log
```

**Production URLs**:
- Local: `http://localhost:9000`
- Public: `https://brainlessly-unequestrian-ember.ngrok-free.dev`
- ngrok Dashboard: `http://localhost:4040`

## Architecture Overview

### Single-File FastAPI Application

**Core**: `main.py` (~2900 lines) - All routes and business logic in one file for rapid development
- Rapid prototyping favored over modular structure
- Easy navigation without import complexity
- All routes visible in one place

**Services** (modular business logic):
- `backend/services/speechpro_service.py` - SpeechPro API integration (GTP → Model → Score workflow)
- `backend/services/learning_progress_service.py` - Learning progress tracking and character popup system

**Database**: SQLite (`data/users.db`) for user auth and learning progress

**Templates**: Jinja2 HTML in `templates/` with component-based structure

**Static Assets**: CSS/JS in `static/` (vanilla JavaScript with IIFE pattern)

**Learning Content**: JSON files in `data/` (sentences, expressions, vocabulary, pronunciation words)

### Key External Integrations

**SpeechPro API** (`http://112.220.79.222:33005/speechpro`):
- **GTP (Grapheme-to-Phoneme)**: `/gtp` - Convert Korean text to phonemes
- **Model**: `/model` - Generate FST pronunciation model
- **Score**: `/scorejson` - Evaluate pronunciation against model
- **Three-step workflow**: Text → GTP → Model → Audio + Model → Score
- **Critical**: Use `normalize_spaces(text)` before sending to API (removes NBSP, tabs, special Unicode spaces)

**FluencyPro API** (`ws://112.220.79.218:33043/ws`):
- WebSocket-based real-time fluency evaluation
- Analyzes speaking speed, syllable accuracy, pronunciation flow
- Returns recognized text with error tags

**MzTTS API** (`http://112.220.79.218:56014`):
- Professional Korean TTS with multiple speakers (0-7)
- Emotion control: neutral, pleasure, anger, sadness
- Output formats: WAV file, PCM base64, server path
- Parameters: `_TEXT`, `_SPEAKER`, `_EMOTION`, tempo/pitch/gain controls

**AI Model Backends** (configurable via `MODEL_BACKEND` env var):
- **Ollama** (default): Local EXAONE models (`exaone3.5:7.8b`, `exaone3.5:2.4b`)
- **Gemini**: Google Gemini API (`gemini-2.5-flash` or configurable)
- **OpenAI**: Disabled by default (import commented out)

### Database Schema

**SQLite** (`data/users.db`) with 3 main tables:

**users** - Authentication and profiles:
```sql
id, username, email, password (hashed SHA-256), name_ko, name_en,
birth_date, nationality, korean_level (초급/중급/고급),
learning_goal, session_token, last_login, created_at, updated_at
```

**user_learning_progress** - Daily learning statistics:
```sql
user_id, date, total_learning_time, pronunciation_practice_count,
pronunciation_avg_score, words_learned, sentences_learned, content_generated,
consecutive_days, achievement_level, total_points, badges (JSON),
last_popup_type, last_popup_date, popup_shown_count
```

**popup_history** - Character popup tracking:
```sql
user_id, popup_type (greeting/achievement/warning/encouragement/praise),
character (oppa/tiger/sister), message, trigger_reason, shown_at, user_action
```

## Environment Configuration

**Required Variables** (`.env` file):

```bash
# AI Backend Selection
MODEL_BACKEND=ollama  # Options: 'ollama', 'gemini', 'openai'

# Ollama Configuration (if MODEL_BACKEND=ollama)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=exaone3.5:2.4b  # Or blank for auto-selection

# Gemini Configuration (if MODEL_BACKEND=gemini)
GEMINI_API_KEY=your-api-key-here
GEMINI_MODEL=gemini-2.5-flash

# SpeechPro API (pronunciation evaluation)
SPEECHPRO_TARGET=http://112.220.79.222:33005/speechpro

# MzTTS API (Korean TTS)
MZTTS_API_URL=http://112.220.79.218:56014

# Korean Romanization Mode
ROMANIZE_MODE=force  # Options: 'force' (always romanize), 'prefer' (keep model output if valid)

# Local STT (optional)
LOCAL_STT=vosk  # Set to 'vosk' to enable
VOSK_MODEL_PATH=/path/to/vosk-model-ko
```

**Important Notes**:
- `.env` file exists in repository for development convenience
- Sensitive keys should be managed securely in production
- Ollama requires local installation: `ollama pull exaone3.5:7.8b`
- ffmpeg required for audio processing: `apt-get install ffmpeg`
- VOSK requires model download from https://alphacephei.com/vosk/models

## Key Implementation Details

### Authentication System

**Session-based authentication** using SQLite and in-memory token storage:

1. **Login** (`POST /api/login`):
   - Verifies email and password (SHA-256 hash)
   - Generates session token (HMAC-SHA256)
   - Stores token in `active_sessions` dict (in-memory)
   - Returns `{"success": true, "session_token": "...", "user": {...}}`

2. **Authorization**:
   - Client sends `Authorization: Bearer <session_token>` header
   - Server validates via `get_current_user()` helper
   - Protected routes return 401 if invalid/missing

**Security Notes**:
- Passwords hashed with SHA-256 (consider bcrypt/argon2 for production)
- Session tokens stored in-memory (lost on restart)
- No token expiration currently implemented

### SpeechPro Integration Workflow

**Three-step pronunciation evaluation** (`backend/services/speechpro_service.py`):

1. **GTP** (`call_speechpro_gtp(text)`):
   - **Critical**: Call `normalize_spaces(text)` first to remove special Unicode spaces
   - Sends `{"id": "...", "text": "안녕하세요"}` to `/gtp`
   - Returns `GTPResult` with `syll_ltrs`, `syll_phns`, `error_code`

2. **Model** (`call_speechpro_model(gtp_result)`):
   - Sends GTP output to `/model`
   - Returns `ModelResult` with FST model data

3. **Score** (`call_speechpro_score(model_result, audio_data)`):
   - Converts audio to base64
   - Sends model + audio to `/scorejson`
   - Returns `ScoreResult` with pronunciation score and details

**Full workflow** (`speechpro_full_workflow(text, audio_bytes)`):
- Combines all three steps automatically
- Handles errors at each stage
- Used by `POST /api/speechpro/evaluate` endpoint

### Learning Progress & Character Popup System

**Class**: `LearningProgressService` (`backend/services/learning_progress_service.py`)

**Key Methods**:
- `record_pronunciation_practice(user_id, score)` - Update daily pronunciation stats
- `should_show_popup(user_id)` - Determine if popup should appear based on triggers
- `record_popup_shown(user_id, popup_type, character, message)` - Log popup display
- `get_user_stats(user_id)` - Get learning statistics and coverage percentages
- `get_today_progress(user_id)` - Get today's learning activity

**Character System** (AI agent-like learning management):
- **Oppa (남동생)**: Current status updates and general guidance
- **Tiger**: Warnings and encouragement for inactivity
- **Sister (여동생)**: Praise and achievement congratulations
- **Triggers**: Consecutive days, achievement milestones, inactivity warnings
- **Throttling**: Max 1 popup per day per user

**Coverage Calculation**:
- Loads totals from `data/vocabulary.json` and `data/sentences.json`
- Tracks user progress vs. total available content
- Returns percentages for words, sentences, and generated content

### Korean Romanization System

**Purpose**: Ensure AI-generated content always has Latin pronunciation, even when LLM fails to provide it.

**Implementation**:
- Tries to import `korean-romanizer` package (optional dependency)
- Falls back to built-in syllable-based romanizer (Revised Romanization approximation)
- Built-in uses lookup tables: `L_TABLE` (초성), `V_TABLE` (중성), `T_TABLE` (종성)

**Modes** (controlled by `ROMANIZE_MODE` env var):
- `force` (default): Always replace `pronunciation` field with romanizer output
- `prefer`: Keep model-provided Latin if valid (ASCII-only, no Hangul); otherwise romanize

**Applied in**: `/api/generate-content` post-processing (normalizes whitespace, ensures Latin-only pronunciation)

### AI Model Output Parsing

**Function**: `_parse_model_output(text)` in `main.py`

**Strategy**:
1. Extract JSON from markdown code fences: ````json ... ````
2. Fallback: Regex search for first `{...}` object in text
3. Returns parsed dict or `None` if both fail

**Retry Logic** (in `/api/generate-content`):
- If parsing fails, sends strict re-prompt requesting JSON-only response
- Retries once with clearer instructions
- Used across all AI content generation endpoints

## Route Structure

### Main Page Routes (Jinja2 Templates)

**발음 학습 (Pronunciation)**:
- `GET /pronunciation-practice` - ELSA-style word practice with native TTS
- `GET /pronunciation-stages` - Level-based pronunciation guide
- `GET /pronunciation-rules` - Korean phoneme rules with interactive exercises (tabs: rules ↔ practice)
- `GET /speechpro-practice` - SpeechPro sentence evaluation
- `GET /fluency-practice` - FluencyPro fluency analysis

**AI 학습 (AI Learning)**:
- `GET /learning` - AI learning tools with feedback
- `GET /content-generation` - Custom dialogue + vocabulary generation
- `GET /fluency-test` - Writing fluency test with scoring
- `GET /essay-test` - Essay evaluation
- `GET /media-generation` - Situational content generation

**활동하기 (Activities)**:
- `GET /word-puzzle` - Drag-and-drop sentence ordering game
- `GET /vocab-garden` - Vocabulary learning with emoji visuals
- `GET /daily-expression` - Daily rotating expressions (changes each day)

**사용자 (User)**:
- `GET /` - Homepage dashboard
- `GET /login` - User authentication
- `GET /mypage` - User profile
- `GET /learning-progress` - Progress tracking dashboard with character popups
- `GET /change-password` - Password management

**기타 (Utilities)**:
- `GET /api-test` - API testing interface
- `GET /sitemap` - Site navigation map
- `GET /chatbot` - AI chatbot interface

### API Routes

**User Authentication** (`/api/*`):
- `POST /api/signup` - User registration
- `POST /api/login` - User login (returns session token)
- `POST /api/logout` - User logout
- `GET /api/user/profile` - Get user profile (requires auth)
- `POST /api/user/profile/update` - Update profile (requires auth)
- `POST /api/user/password/change` - Change password (requires auth)

**SpeechPro APIs** (`/api/speechpro/*`):
- `POST /api/speechpro/gtp` - Grapheme-to-Phoneme conversion
- `POST /api/speechpro/model` - Generate pronunciation model
- `POST /api/speechpro/score` - Calculate pronunciation score
- `POST /api/speechpro/evaluate` - Full evaluation workflow (GTP → Model → Score)
- `GET /api/speechpro/sentences` - Get all practice sentences
- `GET /api/speechpro/sentences/{id}` - Get specific sentence
- `GET /api/speechpro/sentences/level/{level}` - Get sentences by level

**FluencyPro APIs** (`/api/fluencypro/*`):
- `POST /api/fluencypro/analyze` - Analyze speech fluency
- `POST /api/fluencypro/combined-feedback` - SpeechPro + FluencyPro combined feedback
- `GET /api/fluencypro/metrics/{user_id}` - Get user fluency metrics

**AI Content Generation** (`/api/*`):
- `POST /api/generate-content` - Generate dialogue + vocabulary (topic/level-based)
- `POST /api/situational-content` - Generate situational expressions
- `POST /api/fluency-check` - Evaluate written Korean
- `POST /api/chat/test` - Chatbot message (Ollama)
- `POST /api/chatbot` - Chatbot conversation
- `GET /api/ollama/models` - List available Ollama models
- `POST /api/ollama/test` - Test Ollama model with custom prompt

**Learning Content** (`/api/*`):
- `GET /api/puzzle/sentences[?level=A1]` - Word puzzle sentences
- `GET /api/expressions[?level=A1]` - Daily expressions
- `GET /api/expressions/today` - Today's expression (rotates daily)
- `GET /api/vocabulary[?level=A1]` - Vocabulary words
- `GET /api/pronunciation-words[?level=A1]` - Pronunciation practice words

**MzTTS APIs** (`/api/tts/*`):
- `GET /api/tts/info` - MzTTS server information
- `POST /api/tts/generate` - Generate TTS audio

**Learning Progress** (`/api/learning/*`):
- `POST /api/learning/pronunciation-completed` - Record pronunciation practice
- `POST /api/learning/popup-shown` - Record popup display
- `GET /api/learning/user-stats/{user_id}` - Get user learning statistics
- `GET /api/learning/today-progress/{user_id}` - Get today's progress
- `POST /api/learning/check-popup/{user_id}` - Check if popup should be shown

## Data Files Structure

**JSON Learning Content** (`data/`):

1. **`sentences.json`** - Word puzzle sentences
   - Schema: `{id, text, words[], translation, level, category}`
   - Used by: `/api/puzzle/sentences`

2. **`expressions.json`** - Daily expressions
   - Schema: `{id, korean, romanization, english, explanation, culturalNote, level, category, examples[], relatedExpressions[]}`
   - Used by: `/api/expressions`, `/api/expressions/today`

3. **`vocabulary.json`** - Vocabulary words
   - Schema: `{id, word, emoji, meaning, romanization, level, example, category}`
   - Used by: `/api/vocabulary`

4. **`pronunciation-words.json`** - Pronunciation practice words
   - Schema: `{id, word, roman, meaningKo, meaningEn, level, phonemes[], tips}`
   - Used by: `/api/pronunciation-words`

5. **`speechpro-sentences.json`** - SpeechPro practice sentences
   - Schema: `{id, text, level, category, difficulty, ...}`
   - Used by: `/api/speechpro/sentences`

**Loading Pattern**:
```python
def load_json_data(filename):
    with open(f"data/{filename}", "r", encoding="utf-8") as f:
        return json.load(f)
```

## Frontend Architecture

**Template-first approach** (not SPA):
- Server-rendered HTML with Jinja2
- Progressive enhancement with vanilla JavaScript
- No build step or bundling required
- Fast initial page loads, SEO-friendly

**JavaScript Patterns**:
- IIFE modules to avoid global scope pollution
- Async/await for all API calls
- DOM element caching at module init
- Event delegation for dynamic content

**Styling**:
- Tailwind CSS via CDN (utility-first)
- Page-specific CSS files for custom animations/components
- Pretendard font for Korean text
- Responsive design with mobile-first approach

## Common Development Tasks

### Adding a New API Endpoint

1. **Add route in `main.py`**:
```python
@app.get("/api/new-feature/data")
async def get_new_feature_data(level: str = None):
    try:
        data = load_json_data("new-feature.json")
        if level:
            data = [item for item in data if item.get("level") == level.upper()]
        return JSONResponse(content={"data": data})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
```

2. **Create data file** (if needed): `data/new-feature.json`

3. **Add page route** (if UI needed):
```python
@app.get("/new-feature")
async def new_feature_page(request: Request):
    return templates.TemplateResponse("new-feature.html", {"request": request})
```

4. **Create template**: `templates/new-feature.html` extending `base.html`

5. **Create frontend assets**:
   - `static/css/new-feature.css` - Styles
   - `static/js/new-feature.js` - Logic (IIFE pattern)

### Testing External APIs

**SpeechPro**:
```bash
# Test GTP endpoint
curl -X POST http://112.220.79.222:33005/speechpro/gtp \
  -H "Content-Type: application/json" \
  -d '{"id":"test","text":"안녕하세요"}'
```

**MzTTS**:
```bash
# Test TTS generation
curl -X POST http://112.220.79.218:56014 \
  -H "Content-Type: application/json" \
  -d '{"output_type":"path","_TEXT":"안녕하세요","_SPEAKER":0}'
```

**Ollama**:
```bash
# List models
curl http://localhost:11434/api/tags

# Test generation
curl -X POST http://localhost:11434/api/generate \
  -d '{"model":"exaone3.5:2.4b","prompt":"Hello"}'
```

### Implementing Protected Routes

**Pattern**:
```python
@app.get("/api/protected-route")
async def protected_route(request: Request):
    user = await get_current_user(request)
    if not user:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    # Route logic here
    return JSONResponse(content={"user_id": user["id"]})
```

**Helper Function** (`get_current_user()`):
- Extracts `Authorization: Bearer <token>` header
- Validates token against `active_sessions` dict
- Returns user dict or `None`

### Working with Learning Progress

**Recording Activity**:
```python
from backend.services.learning_progress_service import LearningProgressService

progress_service = LearningProgressService()

# Record pronunciation practice
await progress_service.record_pronunciation_practice(
    user_id="user123",
    score=85
)

# Check if popup should be shown
should_show, popup_data = await progress_service.should_show_popup("user123")
if should_show:
    # Display popup to user
    pass
```

## Troubleshooting

### Common Issues

**Ollama connection failure**:
```bash
# Verify Ollama is running
curl http://localhost:11434/api/tags

# Pull model if missing
ollama pull exaone3.5:7.8b
```

**SpeechPro API errors**:
- Always use `normalize_spaces(text)` before sending text to API
- Check API accessibility: `curl http://112.220.79.222:33005/speechpro/gtp`
- Verify JSON format matches spec in `docs/api/SPEECHPRO_API_Interface.md`

**Audio processing failures**:
- Verify ffmpeg is installed: `ffmpeg -version`
- Ensure audio format is supported: WAV, MP3, WebM, OGG, MP4, M4A
- Check VOSK model path if using local STT

**Database errors**:
```bash
# Check database exists
ls -la data/users.db

# Verify schema
sqlite3 data/users.db ".schema"

# Reinitialize if corrupted
rm data/users.db  # Server will recreate on restart
```

### Checking Logs

**Development**:
```bash
# Server runs in foreground with --reload
uvicorn main:app --host 0.0.0.0 --port 9000 --reload
```

**Production**:
```bash
# uvicorn logs
tail -f logs/uvicorn.log

# ngrok logs
tail -f logs/ngrok.log
```

## Production Deployment

### Using Deployment Script

```bash
# Start all services (FastAPI + ngrok)
./start-service.sh

# Stop all services
./stop-service.sh
```

### Manual Systemd Service (Alternative)

```bash
# Install service
sudo cp onui-ai.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable onui-ai
sudo systemctl start onui-ai

# Check status
sudo systemctl status onui-ai

# View logs
sudo journalctl -u onui-ai -f
```

### Ngrok Tunnel

**Fixed domain** configured in `start-service.sh`:
- Domain: `brainlessly-unequestrian-ember.ngrok-free.dev`
- Requires paid ngrok account for fixed domains
- Free accounts get random URLs that change on restart

## Important Notes

### Architecture Philosophy

- **Single-file design** (`main.py` ~2900 lines) for rapid prototyping
- Consider refactoring when exceeding 3000 lines
- Extract routers when code becomes unwieldy: `routers/auth.py`, `routers/speechpro.py`, etc.

### Security Considerations

**Current State** (Development-friendly):
- Session tokens in-memory (lost on restart)
- SHA-256 password hashing (not salted)
- No rate limiting
- CORS allows all origins

**Production Recommendations**:
1. Implement persistent session storage (Redis or database)
2. Upgrade to bcrypt/argon2 password hashing
3. Add rate limiting (e.g., `slowapi` middleware)
4. Implement CORS whitelist
5. Add session expiration (e.g., 24 hours)
6. Add CSRF protection

### Critical Functions

- **`normalize_spaces(text)`**: MUST be called before sending text to SpeechPro API
- **`romanize_korean(text)`**: Ensures pronunciation fields always have Latin script
- **`_parse_model_output(text)`**: Extracts JSON from LLM responses (handles markdown wrappers)
- **`get_current_user(request)`**: Authentication helper for protected routes

## Related Documentation

- `docs/guide/SPEECHPRO_API_WORKFLOW.md` - SpeechPro integration workflow
- `docs/guide/SPEECHPRO_IMPLEMENTATION.md` - Implementation guide
- `docs/api/SPEECHPRO_API_Interface.md` - SpeechPro API specification
- `docs/api/FLUENCY_PRO_API_SPEC.md` - FluencyPro API specification
- `docs/api/TTS_API_Interface.md` - MzTTS API specification
- `docs/requirements/REQ01-2025-12-09.md` - Product requirements
- `database_schema_learning_progress.sql` - Database schema
- `README.md` - User-facing documentation (Korean)
