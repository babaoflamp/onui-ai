# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Onui Korean** (오누이 한국어) is an AI-powered Korean language learning web platform. Backend: FastAPI (Python). Frontend: Jinja2 templates + Tailwind CSS. The app runs at port 9002 (both dev and production via PM2).

## Development Commands

```bash
# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Dev server (hot reload) — 반드시 9002 포트 사용 (9000은 onui-academy 서비스)
source .venv/bin/activate && python -m uvicorn main:app --host 0.0.0.0 --port 9002 --reload

# Stop dev server
pkill -f uvicorn

# Run tests (tests/ currently has no source files; add them under tests/unit, tests/api, tests/integration)
python -m pytest
python -m pytest tests/unit   # scoped run
```

### Production (PM2)

```bash
./start-service.sh    # starts onui-ai + ngrok via PM2
./stop-service.sh     # stops both PM2 processes

pm2 status            # check process health
pm2 logs onui-ai      # tail application logs
pm2 restart onui-ai   # restart without full stop
```

PM2 config is in `ecosystem.config.js`. App logs go to `logs/pm2-out.log` and `logs/pm2-error.log`.

## Key Environment Variables (`.env`)

| Variable | Purpose | Default |
|---|---|---|
| `MODEL_BACKEND` | AI backend: `ollama`, `openai`, or `gemini` | `ollama` |
| `OLLAMA_URL` | Ollama server | `http://localhost:11434` |
| `OLLAMA_MODEL` | Model name | `exaone3.5:2.4b` |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Gemini API | — |
| `GEMINI_MODEL` | Gemini model | `gemini-2.5-flash` |
| `OPENAI_API_KEY` | OpenAI (DALL-E, Whisper) | — |
| `MZTTS_API_URL` | Korean TTS service | `http://112.220.79.218:56014` |
| `SECRET_KEY` | Session signing | random at startup |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth | — |
| `ROMANIZE_MODE` | `force` (always romanize) or `prefer` (keep model output if valid) | `force` |
| `TTS_BACKEND` | `gemini`, `openai`, `google`, or `mztts` | `gemini` |
| `STT_BACKEND` | `openai`, `google`, `vosk`, or `local` | auto |
| `VOSK_MODEL_PATH` | Path to Vosk model dir (required when `STT_BACKEND=vosk`) | — |
| `FLUENCYPRO_WS_URL` | FluencyPro WebSocket URL for fluency evaluation | — |
| `DALLE_MODEL` / `DALLE_SIZE` / `DALLE_QUALITY` / `DALLE_STYLE` | DALL-E generation params | `gpt-image-1` / `1024x1024` / `standard` / `natural` |
| `GEMINI_IMAGE_MODEL` | Gemini model used for image generation | `gemini-2.0-flash-preview-image-generation` |
| `CLARITY_PROJECT_ID` | Microsoft Clarity analytics project ID | — |

## System Dependencies

`ffmpeg` must be installed on the host — used for audio conversion (PCM → 8kHz mono WAV) in FluencyPro and SpeechPro routes.

## Architecture

### Single-file Backend (`main.py`, ~7300 lines)

All FastAPI routes, middleware, and most business logic live in `main.py`. It is large by design (~7450 lines) — don't split it without strong motivation.

Key sections in `main.py`:
- **Lines 1–500**: imports, env config, AI client initialization
- **Lines 500–970**: TTS helpers (MzTTS, Gemini, Google, OpenAI), audio conversion utilities
- **Lines 970–2090**: SQLite DB init (`data/users.db`), auth helpers (PBKDF2 passwords, session tokens), app factory, middleware setup
- **Lines 2090+**: All route handlers (`@app.get/post/...`), including WebSocket endpoints at `/ws/voice-call/{scenario_id}` (Gemini Live API streaming) and `/ws/fluency` (FluencyPro real-time evaluation)

### Routers in `backend/routes/`

These are mounted in `main.py` (~line 1976) via `app.include_router(...)`:

| Router | Prefix/Routes |
|---|---|
| `learning_progress.py` | `/api/learning/*` — per-user progress tracking |
| `tts.py` | `/api/tts/*` — TTS generation endpoint |
| `speechpro.py` | `/api/speechpro/*` — pronunciation evaluation |
| `roleplay.py` | `/roleplay`, `/api/roleplay/*` — AI historical figure roleplay |
| `lms.py` | LMS (Learning Management System) routes — grades, attendance, time-on-task |
| `auth.py` | `/api/signup`, `/api/login`, `/api/logout` and related auth endpoints |

### `backend/utils.py`

Thin shared helper — currently just `_get_state(request, name)` for reading from `request.app.state`. Import from here rather than accessing `app.state` directly in routers/services.

Routers receive AI clients, DB helpers, and other dependencies via `request.app.state`. State is populated in `main.py` after the app factory runs (~line 2076+). Always use `_get_state()` rather than importing globals from `main.py`.

### Services in `backend/services/`

| Service | Purpose |
|---|---|
| `speechpro_service.py` | Pronunciation evaluation via external SpeechPro API |
| `fluencypro_service.py` | Writing fluency evaluation |
| `learning_progress_service.py` | Track per-user learning progress in SQLite |
| `krdict_service.py` | Korean dictionary lookup (KRDICT API) |
| `dalle_service.py` | Image generation (DALL-E / Gemini) |
| `analytics_service.py` | Usage analytics |

### Database

SQLite at `data/users.db`. Schema is created/migrated programmatically in `_init_user_db()` (main.py ~line 977). The DB is called at startup and uses `_ensure_*` helper functions to add columns/tables to existing DBs — no migration framework.

Tables: `users`, `word_scores`, `sentence_scores`, `attendance`, `n_documents`/`n_chunks`/`n_settings` (RAG with SQLite FTS5), LMS tables, admin logging tables.

### Session Auth

Cookie-based sessions using an in-memory `active_sessions` dict (token → user info). Token is a 64-char hex string stored in an `auth_token` cookie. Sessions expire after 24 hours. Google OAuth via `authlib`. Admin roles use `is_admin` flag + `role` field (`learner`, `instructor`, `system_admin`).

### Frontend

- **`templates/base.html`**: Master layout — navigation, i18n initialization, character popup. All pages extend this.
- **`templates/components/`**: Reusable Jinja2 partials — `character-popup.html`, `floating-buttons.html`, `ai-avatar.html`.
- **`static/js/` and `static/css/`**: Feature-specific assets with kebab-case names matching their template (e.g., `word-puzzle.js` ↔ `word-puzzle.html`).
- Tailwind CSS is loaded via CDN (not compiled locally).
- JavaScript in templates is mostly inline; standalone JS files exist for complex pages: `word-puzzle.js`, `vocab-garden.js`, `daily-expression.js`, `ui-components.js`, `floating-buttons.js`, `auth.js`.

Notable templates: `ai-roleplay.html`, `voice-call.html`, `video-learning.html`, `onui-beats.html`, `sentence-evaluation.html`, `speechpro-practice.html`, `content-generation.html`, `daily-expression.html`, `learning-progress.html`, `dashboard.html`, `onui-grammar.html` (AI Grammar Coach), and a full admin section (`admin-dashboard.html`, `admin-users.html`, `admin-logs.html`, `admin-settings.html`, `admin-system.html`, `admin-api.html`). Dev/test templates (`api-test.html`, `stt-multi-test.html`) are not user-facing.

File storage under `uploads/` (served at `/uploads`):
- `uploads/` — user profile images and miscellaneous uploads
- `uploads/images/` — DALL-E / Gemini generated vocabulary images (persisted, not temp)
- `uploads/audio/` — pronunciation recordings; auto-cleaned after 30 days

### i18n System

UI strings are translated client-side. Locale files live in `data/locales/{lang}.json` (supports `ko`, `en`, `ja`, `zh`) and are served as static JSON at `/data/locales/`. `static/js/i18n.js` fetches the file on page load, then applies translations to any element with a `data-i18n="key"` attribute. The active language is persisted in `localStorage` under `app_lang`.

**FOUC prevention**: `base.html` sets `document.documentElement.style.visibility = "hidden"` immediately; `i18n.js` clears it after translations are applied. When adding new translatable strings, add the key to all four locale files.

### Data Files (`data/`)

Static JSON datasets read at startup or on-demand:
- `sentences.json` — 35 sentences for listening/puzzle activities
- `vocabulary.json` — 72 vocabulary words (A1–B2)
- `pronunciation-words.json` / `speechpro-sentences.json` — pronunciation practice content
- `expressions.json` — daily expressions served via `/api/expressions`
- `folktales.json` — 10 Korean folktales
- `cultural-expressions.json` — 30 cultural expressions
- `voice-call.json` — voice call scenario definitions (used by `/ws/voice-call/` WebSocket)
- `onui-beats.json` — music/lyrics data for Onui Beats feature
- `onui-tube.json` / `onui-tube-transcripts.json` — video metadata and transcripts for OnuiTube
- `roleplay-scenarios.json` — historical figure scenarios for AI Roleplay
- `tongue-twister-metadata.json` — tongue twister content
- `sp_ko_questions.json` — SpeechPro Korean question bank
- `landing_intake.json` — landing page intake/onboarding data
- `word_image_cache.json` — cached DALL-E image URLs for vocabulary words
- `tts_cache/` — pre-generated TTS audio files (`.bin` = audio, `.json` = metadata)

### Scripts (`scripts/`)

Utility scripts for one-off data management — not part of the app runtime:
- `generate_locales.py` / `translate_locales.py` — generate and machine-translate locale JSON files
- `import_excel_sentences.py` / `sync_sentences_json.py` / `merge_sentences.py` — manage `sentences.json`
- `rotate-logs.py` — manual log rotation (also configured via `onui-ai-logrotate.conf`)

### Dependency Note

`requirements.txt` pins `openai<2.0.0`. The codebase uses the v1 `OpenAI` client style — upgrading to v2 would break DALL-E and Whisper integrations.

## Coding Conventions

- Python: 4-space indentation, snake_case for modules and functions.
- Templates: mirror the Tailwind utility patterns already in use; don't introduce new CSS frameworks.
- Static assets: kebab-case filenames; keep CSS/JS co-located by feature name.
- Commit style: `feat:`, `fix:`, `refactor:`, `chore:` prefixes with optional scope (e.g., `fix(ui): ...`).

## AI Backend Routing

The `MODEL_BACKEND` env var controls which LLM handles content generation:
- `ollama` → local EXAONE model via Ollama REST API
- `openai` → OpenAI GPT via `openai` SDK
- `gemini` → Gemini via `google-genai` SDK

TTS and STT have separate backend selectors (`TTS_BACKEND`, `STT_BACKEND`) and can differ from the main `MODEL_BACKEND`.

Image generation (`dalle_service.py`) uses DALL-E when `OPENAI_API_KEY` is set, falling back to Gemini image generation otherwise.

The app includes a built-in Hangul→Latin romanizer (syllable-table lookup) that requires no extra packages. The `korean_romanizer` package is optional and used automatically if installed.
