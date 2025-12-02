# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Onui K-talk AI** - A Korean language learning web application with AI-powered features including content generation, pronunciation checking, and fluency testing. The application uses local LLM models (Ollama with EXAONE) or OpenAI API for generating educational content and providing feedback.

**Stack**: FastAPI backend with Jinja2 templates, vanilla JavaScript frontend, Python 3.8+

**Key Features**:
1. Custom educational content generation (dialogue + vocabulary)
2. AI-powered pronunciation checking via speech-to-text
3. Writing fluency evaluation and correction

## Quick Start

### First-time Setup

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Setup environment variables
cp .env.example .env
# Edit .env to configure MODEL_BACKEND and API settings

# 4. Start the application
uvicorn main:app --host 0.0.0.0 --port 9000 --reload
```

**Access**: `http://localhost:9000`

### Common Commands

```bash
# Development server with auto-reload
uvicorn main:app --host 0.0.0.0 --port 9000 --reload

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

**FastAPI application** with three main API endpoints:

1. **`POST /api/generate-content`** - Content generation
   - Inputs: `topic` (str), `level` (str), `model` (optional str)
   - Generates Korean dialogue + vocabulary in JSON format
   - Uses either Ollama (local) or OpenAI (disabled by default)
   - Returns: `{"dialogue": [...], "vocabulary": [...]}`

2. **`POST /api/pronunciation-check`** - Speech evaluation
   - Inputs: `target_text` (str), `file` (audio upload)
   - Converts speech to text using Whisper API or VOSK (local)
   - Compares transcribed text to target using SequenceMatcher
   - Returns: `{"user_said": "...", "score": 85.3, "feedback": "..."}`

3. **`POST /api/fluency-check`** - Writing evaluation
   - Inputs: `user_text` (str)
   - Evaluates naturalness and provides corrections
   - Returns: `{"score": 85, "corrected": "...", "feedback": "..."}`

**Helper endpoints**:
- `GET /api/ollama/models` - List available Ollama models
- `POST /api/ollama/test` - Test Ollama model with custom prompt

### Model Backend System

The application supports **dual backend modes** (configured via `MODEL_BACKEND` environment variable):

**Ollama Backend** (`MODEL_BACKEND=ollama`):
- Uses local Ollama server (default: `http://localhost:11434`)
- Auto-selects EXAONE models in preferred order: `exaone3.5:7.8b` → `exaone3.5:2.4b` → others
- Streams responses and parses JSON from model output
- Function: `_auto_select_ollama_model()` auto-detects best available model at startup

**OpenAI Backend** (`MODEL_BACKEND=openai`):
- Currently disabled/commented out in code
- Would use OpenAI API if `OPENAI_API_KEY` is set
- Used for Whisper STT when `client` is initialized

**Local STT with VOSK**:
- Alternative to OpenAI Whisper for pronunciation checking
- Requires `VOSK_MODEL_PATH` environment variable
- Converts audio to 16kHz mono WAV using ffmpeg
- Function: `_transcribe_with_vosk(wav_path, model_path)`

### Model Output Parsing

Key function: `_parse_model_output(text)` handles LLM response parsing:
1. First attempts to extract JSON from code fences (```json ... ```)
2. Falls back to regex search for JSON objects in text
3. Returns parsed object or None if parsing fails

This is critical because LLMs often wrap JSON in markdown code blocks.

### Audio Processing Pipeline

For pronunciation checking:
1. Browser records audio using MediaRecorder API (WebM/WAV format)
2. Backend receives upload, validates size (5MB limit) and type
3. If using VOSK: converts to 16kHz mono WAV with `_ensure_wav_16k_mono()`
4. Transcribes using either Whisper API or VOSK
5. Compares transcription to target text using `difflib.SequenceMatcher`
6. Calculates similarity score (0-100) and generates feedback
7. Temporary files cleaned up in finally block

**Important**: File cleanup happens in finally blocks to prevent disk bloat from failed uploads.

### Frontend Architecture

**Single-page application** (`templates/index.html`):
- Three feature sections with independent functionality
- Tailwind CSS for styling, Pretendard font for Korean text
- Async/await pattern for all API calls

**Key JavaScript functions**:
- `generateContent()` - Fetches AI-generated learning content
- `loadModels()` - Populates model selector from `/api/ollama/models`
- `testModel()` - Quick test interface for model selection
- MediaRecorder handlers for audio recording (record/stop buttons)
- `checkFluency()` - Submits writing for evaluation

**Model selection UX**:
- Dropdown populated dynamically from Ollama server
- Users can test different models before generating content
- Test prompt interface shows raw model output for debugging

## Environment Configuration

**Required `.env` file** (copy from `.env.example`):

```bash
# Backend selection: 'openai' or 'ollama'
MODEL_BACKEND=ollama

# Ollama settings (when MODEL_BACKEND=ollama)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=exaone3.5:7.8b  # Leave blank for auto-selection

# OpenAI settings (when MODEL_BACKEND=openai, currently disabled)
OPENAI_API_KEY=

# Local STT with VOSK (alternative to Whisper)
LOCAL_STT=vosk  # Set to 'vosk' to enable
VOSK_MODEL_PATH=/path/to/vosk-model-ko  # Required if LOCAL_STT=vosk
```

**Important notes**:
- Never commit `.env` file with real API keys
- Ollama must be running locally if `MODEL_BACKEND=ollama`
- VOSK requires downloading Korean language model separately
- ffmpeg must be installed for VOSK audio conversion

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

**External requirements**:
- ffmpeg (system package) - Required for VOSK audio conversion
- Ollama server with EXAONE models - Required if using local backend

## Common Development Patterns

### Adding a New API Endpoint

1. Define route in `main.py`:
```python
@app.post("/api/new-feature")
async def new_feature(param: str = Form(...)):
    # Implementation
    return JSONResponse(content={"result": "..."})
```

2. Add frontend function in `index.html`:
```javascript
async function callNewFeature() {
    const formData = new FormData();
    formData.append("param", value);
    const res = await fetch("/api/new-feature", {
        method: "POST",
        body: formData
    });
    const data = await res.json();
    // Update UI
}
```

### Working with Ollama Models

**Testing model availability**:
```bash
# List models on Ollama server
curl http://localhost:11434/v1/models

# Test generation
curl -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model": "exaone3.5:7.8b", "prompt": "안녕하세요"}'
```

**Model response format**: Ollama streams newline-delimited JSON. Each line contains:
```json
{"response": "text chunk", "done": false}
```

The app concatenates all `response` values and parses the final result.

### Error Handling Pattern

All API endpoints follow this pattern:
```python
try:
    # Main logic
    return JSONResponse(content={...})
except Exception as e:
    return JSONResponse(
        status_code=500,
        content={"error": "description", "details": str(e)}
    )
```

Frontend displays error messages from the `error` field.

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
```

### VOSK Setup for Local STT

```bash
# Download Korean VOSK model
wget https://alphacephei.com/vosk/models/vosk-model-ko-0.22.zip
unzip vosk-model-ko-0.22.zip
# Set VOSK_MODEL_PATH in .env to extracted directory

# Ensure ffmpeg is installed
ffmpeg -version
# Ubuntu/Debian: apt-get install ffmpeg
# macOS: brew install ffmpeg
```

### Audio Recording Not Working

**Common issues**:
1. Browser requires HTTPS for getUserMedia (except localhost)
2. Microphone permissions blocked - check browser settings
3. MediaRecorder not supported - requires modern browser
4. File size limit exceeded - recordings limited to 5MB

### Model Output Parsing Failures

If `_parse_model_output()` returns None:
1. Model may not be following JSON format instruction
2. Check raw output in browser console (test endpoint)
3. Adjust prompt to be more explicit about JSON format
4. Consider temperature/parameters in model configuration

## Project Structure

```
onui-ai/
├── main.py                 # FastAPI application (all backend logic)
├── templates/
│   └── index.html         # Single-page frontend
├── requirements.txt       # Python dependencies
├── .env.example          # Environment variable template
├── .env                  # Local config (gitignored)
├── docs/                 # Design mockups (HTML)
├── configs/              # (empty, future use)
├── data/                 # (empty, future use)
├── scripts/              # (empty, future use)
├── tests/                # (empty, future use)
└── .venv/                # Python virtual environment
```

**Note**: All backend logic is in single `main.py` file. As project grows, consider refactoring into:
- `routers/` - API route modules
- `services/` - Business logic (STT, model interaction)
- `utils/` - Helper functions (parsing, audio conversion)

## OpenAI Integration (Currently Disabled)

The codebase has OpenAI support **commented out**:
- Import at top of `main.py` is commented: `# from openai import OpenAI`
- Client initialization: `client = None`
- Whisper STT for pronunciation checking is disabled
- To re-enable: uncomment import and restore `client = OpenAI(...)` initialization

**Reason for disabling**: Project uses local Ollama backend by default to avoid API costs and enable offline operation.
