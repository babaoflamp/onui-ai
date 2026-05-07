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

# Dev server (hot reload) — 반드시 9002 포트 사용
source .venv/bin/activate && python -m uvicorn main:app --host 0.0.0.0 --port 9002 --reload

# Stop dev server
pkill -f uvicorn

# Run tests
python -m pytest
python -m pytest tests/unit   # scoped run (test_onui_tube_catalog.py lives here)
```

### Production (PM2)

```bash
./start-service.sh    # starts onui-ai via PM2
./stop-service.sh     # stops both PM2 processes

pm2 status            # check process health
pm2 logs onui-ai      # tail application logs
pm2 restart onui-ai   # restart without full stop
```

PM2 config is in `ecosystem.config.js`. App logs go to `logs/pm2-out.log` and `logs/pm2-error.log`.

### Production URLs & Network Topology

```
onuiai.kr / onui.ai.kr  (DNS A → server IP)
  └→ nginx (80/443, SSL via Let's Encrypt)
  │   configs: nginx-onuiai.kr.conf, nginx-onui.ai.kr.conf
       └→ uvicorn (127.0.0.1:9002)
           ↑
          optional manual ngrok tunnel (run only when temporarily needed)
```

`scripts/setup-domain.sh` / `scripts/setup-domain-onui-ai-kr.sh` handle first-time nginx + certbot setup. SSL renewal: `sudo certbot renew`.

### Feature URL Map

| Feature | Route |
|---|---|
| Dashboard | `/dashboard` |
| Daily Expression | `/daily-expression` |
| OnuiTube (video) | `/video-learning` |
| Onui Beats (K-Pop) | `/onui-beats` |
| AI Voice Call | `/voice-call` |
| AI Roleplay | `/roleplay` |
| Content Generation | `/content-generation` |
| Pronunciation (SpeechPro) | `/speechpro-practice` |
| Free Sentence Evaluation | `/sentence-evaluation` |
| Learning Progress | `/learning-progress` |
| AI Grammar Coach | `/onui-grammar` |

## Key Environment Variables (`.env`)

| Variable | Purpose | Default |
|---|---|---|
| `MODEL_BACKEND` | AI backend: `ollama`, `openai`, or `gemini` | `gemini` |
| `OLLAMA_URL` | Ollama server | `http://localhost:11434` |
| `OLLAMA_MODEL` | Model name | `exaone3.5:2.4b` |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Gemini API | — |
| `GEMINI_MODEL` | Gemini model for content generation | `gemini-2.0-flash` |
| `OPENAI_API_KEY` | OpenAI (DALL-E, Whisper) | — |
| `OPENAI_MODEL` | OpenAI model for content generation | `gpt-4o-mini` |
| `MZTTS_API_URL` | Korean TTS service | `http://112.220.79.218:56014` |
| `SECRET_KEY` | Session signing | random at startup |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth | — |
| `ROMANIZE_MODE` | `force` (always romanize) or `prefer` (keep model output if valid) | `force` |
| `TTS_BACKEND` | `gemini`, `openai`, `google`, or `mztts` | `gemini` |
| `GEMINI_LIVE_MODEL` | Gemini model for Live API (voice call WebSocket) | `gemini-2.5-flash-native-audio-latest` |
| `GEMINI_TTS_MODEL` | Gemini model for TTS | `gemini-1.5-flash` |
| `GEMINI_TTS_VOICE` | Gemini TTS voice name | `Aoede` |
| `GEMINI_TTS_MIME` | Gemini TTS output MIME type | `audio/wav` |
| `OPENAI_TTS_MODEL` | OpenAI TTS model | `tts-1` |
| `OPENAI_TTS_VOICE` | OpenAI TTS voice | `alloy` |
| `OPENAI_TTS_FORMAT` | OpenAI TTS output format | `mp3` |
| `GOOGLE_TTS_LANGUAGE` | Google Cloud TTS language code | `ko-KR` |
| `GOOGLE_TTS_VOICE` | Google Cloud TTS voice name | `ko-KR-Standard-A` |
| `GOOGLE_TTS_AUDIO_ENCODING` | Google Cloud TTS encoding | `MP3` |
| `STT_BACKEND` | `openai`, `google`, `vosk`, or `local` | auto |
| `VOSK_MODEL_PATH` | Path to Vosk model dir (required when `STT_BACKEND=vosk`) | — |
| `FLUENCYPRO_WS_URL` | FluencyPro WebSocket URL for fluency evaluation | — |
| `DALLE_MODEL` / `DALLE_SIZE` / `DALLE_QUALITY` / `DALLE_STYLE` | DALL-E generation params | `gpt-image-1` / `1024x1024` / `standard` / `natural` |
| `GEMINI_IMAGE_MODEL` | Gemini model used for image generation | `gemini-2.0-flash-preview-image-generation` |
| `CLARITY_PROJECT_ID` | Microsoft Clarity analytics project ID | — |
| `DAILY_CREDITS` | Per-user daily credit budget (resets at midnight) | `100` |

## System Dependencies

`ffmpeg` must be installed on the host — used for audio conversion (PCM → 8kHz mono WAV) in FluencyPro and SpeechPro routes.

## Architecture

### Entry Point (`main.py`, ~700 lines)

`main.py` is now a thin orchestrator. It handles:
- Imports, env config, AI client initialization (lines 1–100)
- TTS helpers (MzTTS, Gemini, Google, OpenAI) and audio conversion utilities
- SQLite DB init (`data/users.db`) via `_init_user_db()` and `_ensure_*` helpers
- App factory, middleware setup (CORS, session, logging)
- All `app.include_router(...)` mounts (lines 673–685)
- WebSocket endpoints at `/ws/voice-call/{scenario_id}` (Gemini Live API streaming) and `/ws/fluency` (FluencyPro real-time evaluation) live in `backend/routes/ai_services.py`

### Routers in `backend/routes/`

All mounted in `main.py` via `app.include_router(...)`:

| Router | Key Routes |
|---|---|
| `pages.py` | All HTML page GETs (`/`, `/dashboard`, `/video-learning`, `/onui-beats`, `/voice-call`, `/onui-grammar`, `/daily-expression`, `/sentence-evaluation`, `/learning-progress`, `/login`, `/signup`, `/mypage`, `/privacy`, etc.) |
| `auth.py` | `/api/signup`, `/api/login`, `/api/logout` and Google OAuth |
| `user.py` | `/mypage`, `/change-password`, `/api/user/profile`, `/api/user/password/change`, `/api/credits` |
| `ai_services.py` | `/api/voice-call/scenarios`, `/ws/voice-call/{scenario_id}` (auth + credit-gated), `/api/generate-content`, `/api/gemini/image`, `/api/word-images/cache`, `/api/ollama/*`, `/api/chat/test`, `/api/fluency-check` |
| `content.py` | `/api/dashboard/quick-stats`, `/api/expressions`, `/api/textbooks`, `/api/attendance/*` |
| `media.py` | `/api/tube/videos`, `/api/tube/transcripts`, `/api/tube/vocab`, `/api/video-lessons`, `/api/video-progress` |
| `stt.py` | `/api/stt/proxy`, `/api/stt/whisper`, `/api/stt/google`, `/api/stt/vosk`, `/api/voice-call/stt` |
| `learning_progress.py` | `/api/learning/*` — per-user progress tracking |
| `tts.py` | `/api/tts/*` — TTS generation |
| `speechpro.py` | `/api/speechpro/*` — pronunciation evaluation |
| `roleplay.py` | `/roleplay`, `/api/roleplay/*` — AI historical figure roleplay |
| `lms.py` | LMS routes — grades, attendance, time-on-task |
| `admin.py` | `/api/admin/*` — admin dashboard, user management, logs |

`deps.py` re-exports everything from `backend/utils.py` for use in routers — always import from `deps.py` inside routes, not directly from `utils.py` or `main.py`.

### `backend/utils.py`

Comprehensive shared utility module. Exports: auth helpers (`get_current_user`, `get_current_admin_user`, `get_optional_user`, `get_session`, `create_session_token`, `parse_session_token`, `hash_password`, `verify_password`), data helpers (`load_json_data`, `get_user_credits`, `check_and_consume_credits`), RAG utilities (`ensure_rag_tables`, `rag_chunk_text`, `rag_get_settings`, `rag_search`), Korean language utils (`romanize_korean`, `parse_model_output`), Ollama helpers (`list_ollama_models`), and audio utils (`ensure_wav_16k_mono`, `transcribe_with_vosk`).

Routers receive AI clients, DB helpers, and other dependencies via `request.app.state`. Always use utilities from `backend/utils.py` (via `deps.py`) rather than importing globals from `main.py`.

### Services in `backend/services/`

| Service | Purpose |
|---|---|
| `speechpro_service.py` | Pronunciation evaluation via external SpeechPro API |
| `fluencypro_service.py` | Writing fluency evaluation |
| `learning_progress_service.py` | Track per-user learning progress in SQLite |
| `krdict_service.py` | Korean dictionary lookup (KRDICT API) |
| `dalle_service.py` | Image generation (DALL-E / Gemini) |
| `analytics_service.py` | Usage analytics |
| `onui_tube_catalog.py` | Annotates OnuiTube videos with transcript/vocab metadata at page render time |

### Database

SQLite at `data/users.db`. Schema is created/migrated programmatically in `_init_user_db()` (main.py line 176). The DB is called at startup and uses `_ensure_*` helper functions to add columns/tables to existing DBs — no migration framework.

Tables: `users`, `word_scores`, `sentence_scores`, `attendance`, `n_documents`/`n_chunks`/`n_settings` (RAG with SQLite FTS5), LMS tables, admin logging tables.

### Session Auth

Cookie-based sessions using an in-memory `active_sessions` dict (token → user info). Token is a 64-char hex string stored in a `session_token` cookie. Sessions expire after 24 hours. Google OAuth via `authlib`. Admin roles use `is_admin` flag + `role` field (`learner`, `instructor`, `system_admin`).

**Credit system**: `app.state.credit_costs` holds `{"lesson": 3, "image": 10, "quiz": 2, "chat": 2, "tts": 1, "voice": 5}`. `check_and_consume_credits()` (in `utils.py`) gates all AI endpoints; budget resets daily based on `DAILY_CREDITS`. The WebSocket auth check for voice call reads the cookie directly via `websocket.cookies`.

### Frontend

- **`templates/base.html`**: Master layout — navigation, i18n initialization, character popup. All pages extend this.
- **`templates/components/`**: Reusable Jinja2 partials — `character-popup.html`, `floating-buttons.html`, `ai-avatar.html`.
- **`static/js/` and `static/css/`**: Feature-specific assets with kebab-case names matching their template (e.g., `word-puzzle.js` ↔ `word-puzzle.html`).
- Tailwind CSS is loaded via CDN (not compiled locally).
- Most feature pages have a dedicated JS file in `static/js/` matching their name (e.g., `voice-call.js`, `onui-beats.js`, `video-learning.js`, `daily-expression.js`, `onui-grammar.js`, `speechpro-practice.js`, `dashboard.js`, `learning-progress.js`, `content-generation.js`, `ai-roleplay.js`). Shared utilities: `i18n.js`, `ui-components.js`, `floating-buttons.js`, `auth.js`, `audio-processor.js`.

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
- `landing_intent.json` — landing page intake/onboarding intent data
- `word_image_cache.json` — cached DALL-E image URLs for vocabulary words
- `landing_intake.json` — extended onboarding intake data (alongside `landing_intent.json`)
- `tts_cache/` — pre-generated TTS audio files (`.bin` = audio, `.json` = metadata)

### Scripts (`scripts/`)

Utility scripts for one-off data management — not part of the app runtime:
- `generate_locales.py` / `translate_locales.py` — generate and machine-translate locale JSON files
- `import_excel_sentences.py` / `sync_sentences_json.py` / `merge_sentences.py` — manage `sentences.json`
- `audit_onuitube_catalog.py` / `build_onuitube_replacement_template.py` — OnuiTube video catalog audit and replacement template builder
- `generate_tube_transcript.py` / `generate_tube_videos.py` — yt-dlp pipeline for OnuiTube content
- `generate_tube_images.py` / `generate_roleplay_images.py` / `generate_folktale_images.py` / `generate_landing_images.py` — DALL-E / Gemini image generation for static content
- `regen_tts.py` — regenerate pre-built TTS cache files
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
