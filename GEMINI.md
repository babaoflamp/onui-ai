# GEMINI.md - Onui Korean (오누이 한국어) 🌸

## Project Overview
Onui Korean is an AI-powered Korean language learning platform designed for global learners. It leverages modern AI technologies to provide interactive pronunciation evaluation, personalized content generation, and gamified learning experiences.

- **Primary Purpose:** Comprehensive Korean language learning (Pronunciation, Grammar, Culture).
- **Key Technologies:**
  - **Backend:** FastAPI (Python 3.8+), SQLite (User data), JSON (Content data).
  - **Frontend:** Jinja2 Templates, Tailwind CSS, Vanilla JavaScript.
  - **AI Ecosystem:**
    - **LLM:** Ollama (EXAONE), OpenAI (GPT-4), Google Gemini.
    - **Speech (STT/TTS):** MzTTS (Professional Korean TTS), Vosk (Local STT), Google Cloud Speech/TTS, OpenAI Whisper/TTS.
    - **Evaluation:** SpeechPro API (Proprietary pronunciation scoring workflow).
- **Architecture:** Modular service-oriented architecture with FastAPI routers and independent service layers.

## Core Modules & Structure

### Backend (`/backend`)
- **`routes/`**: Feature-specific API endpoints (e.g., `speechpro.py`, `tts.py`, `learning_progress.py`).
- **`services/`**: Core business logic and external API integrations (e.g., `speechpro_service.py`, `dalle_service.py`).

### Data (`/data`)
- **`users.db`**: SQLite database for user accounts, progress, and history.
- **JSON Files**: Content storage for `vocabulary.json`, `sentences.json`, `folktales.json`, and `cultural-expressions.json`.

### Templates (`/templates`)
- **`base.html`**: Master layout with header/footer.
- **`speechpro-practice.html`**: Core pronunciation evaluation interface.
- **`learning.html`**: AI-driven personalized learning tool.
- **`components/`**: Reusable UI elements like `character-popup.html`.

### Static Assets (`/static`)
- CSS/JS organized by feature (e.g., `static/js/pronunciation-practice.js`).

## Building and Running

### Prerequisites
- Python 3.8+
- `ffmpeg` (Required for audio processing)
- `Ollama` (Optional, for local LLM features)

### Setup & Execution
1.  **Virtual Environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```
2.  **Environment Variables:** Create a `.env` file based on `.env.example`.
    - `MODEL_BACKEND`: `ollama`, `openai`, or `gemini`.
    - `OLLAMA_URL`: Default `http://localhost:11434`.
    - `MZTTS_API_URL`: Professional Korean TTS endpoint.
    - `SPEECHPRO_TARGET`: Pronunciation evaluation server URL.
3.  **Run Server:**
    ```bash
    python main.py
    # OR
    uvicorn main:app --host 0.0.0.0 --port 9000 --reload
    ```

## Development Conventions

### Coding Style
- **Python:** PEP 8 compliant. Use type hints where possible.
- **FastAPI:** Use `app.state` for global dependencies and `Depends` for request-scoped injections.
- **Frontend:** Prefer Vanilla JS for interactivity to minimize build complexity. Styling via Tailwind CSS utility classes.

### API Standards
- **Standardized Responses:** Use `JSONResponse` for API endpoints.
- **Naming:** Snake_case for Python, camelCase for JavaScript and JSON keys.

### Authentication & Security
- **Session Management:** Custom token-based session management stored in `active_sessions` (in-memory) and cookies.
- **Password Hashing:** PBKDF2 with 120,000 iterations (stored in `users.db`).
- **Roles:** `learner`, `instructor`, `system_admin`.

### Pronunciation Workflow (SpeechPro)
- Follows a 3-step sequence: **GTP** (Grapheme-to-Phoneme) -> **Model** (FST Generation) -> **Score** (Audio Evaluation).
- Always normalize Korean text using `normalize_spaces` before sending to SpeechPro.

## Key Maintenance Commands
- **Fix Password:** `python fix_admin_pwd.py`
- **Cleanup Users:** `python cleanup_users.py`
- **Test SpeechPro:** `python scripts/test_speechpro_score_api.py`
- **Generate Metadata:** `python generate_tongue_twister_metadata.py`
