# CLAUDE.md

Guidance for AI coding agents working in this repository. Keep this file accurate when architecture changes.

## Project Overview

**Onui Korean** (오누이 한국어) is an AI-powered Korean language learning web platform.

- **Backend**: FastAPI (Python), SQLite (`data/users.db`)
- **Frontend**: Jinja2 templates + Tailwind CSS (CDN)
- **Port**: 9002 (dev and production via PM2)
- **UI languages**: static `ko/en/ja/zh/vi/ne` + Google Translate widget for `id/mn/lo`

## Development Commands

```bash
# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Dev server (hot reload) — always port 9002
source .venv/bin/activate && python -m uvicorn main:app --host 0.0.0.0 --port 9002 --reload
# or: python main.py

# Stop dev server
pkill -f uvicorn

# Tests
python -m pytest
python -m pytest tests/unit
```

### Production (PM2)

```bash
./start-service.sh    # starts onui-ai via PM2
./stop-service.sh
./restart.sh

pm2 status
pm2 logs onui-ai
pm2 restart onui-ai
```

PM2 config: `ecosystem.config.js`. Logs: `logs/pm2-out.log`, `logs/pm2-error.log`.

### Production URLs & Network Topology

```
onuiai.kr / opportunity.ai.kr  (DNS A → server IP)
  └→ nginx (80/443, SSL via Let's Encrypt)
  │   configs: nginx-onuiai.kr.conf, nginx-opportunity.ai.kr.conf
       └→ uvicorn (127.0.0.1:9002)
           ↑
          optional manual ngrok tunnel (scripts/run-ngrok.sh)
```

Domain setup: `scripts/setup-domain.sh`, `scripts/setup-domain-onui-ai-kr.sh`. SSL: `sudo certbot renew`.

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

Defined primarily in `backend/config.py` (`Settings` / `load_settings()`). Template: `.env.example`.

| Variable | Purpose | Default |
|---|---|---|
| `APP_ENV` | `development` / `production` (`SECRET_KEY` required in production) | `development` |
| `MODEL_BACKEND` | AI backend: `ollama`, `openai`, or `gemini` | `gemini` |
| `OLLAMA_URL` | Ollama server | `http://localhost:11434` |
| `OLLAMA_MODEL` | Model name | `exaone` |
| `GEMINI_API_KEY` | Gemini API | — |
| `GEMINI_MODEL` | Content generation model | `gemini-2.0-flash` |
| `OPENAI_API_KEY` | OpenAI (DALL-E, Whisper, chat) | — |
| `OPENAI_MODEL` | OpenAI content model | `gpt-4o-mini` |
| `TTS_BACKEND` | `gemini`, `openai`, `google`, or `mztts` | `gemini` |
| `GEMINI_TTS_MODEL` / `GEMINI_TTS_VOICE` / `GEMINI_TTS_MIME` | Gemini TTS | see config |
| `OPENAI_TTS_MODEL` / `OPENAI_TTS_VOICE` / `OPENAI_TTS_FORMAT` | OpenAI TTS | `tts-1` / `alloy` / `mp3` |
| `GOOGLE_TTS_*` | Google Cloud TTS language/voice/encoding | `ko-KR` / Standard-A / MP3 |
| `STT_BACKEND` | `openai`, `google`, `vosk`, or `local` | `openai` |
| `VOSK_MODEL_PATH` | Vosk model dir (when local/vosk STT) | — |
| `SECRET_KEY` | Session HMAC signing | required in production |
| `SESSION_EXPIRY_SECONDS` | Cookie / session lifetime | `14400` (4h in config) |
| `SESSION_COOKIE_SECURE` | Secure cookie flag | `false` |
| `ALLOWED_ORIGINS` | CORS origins (CSV) | localhost:9002 + opportunity.ai.kr |
| `DAILY_CREDITS` | Per-user daily credit budget | `100` |
| `DB_PATH` | SQLite path | `data/users.db` |
| `ONUI_TMP_DIR` | Scratch/temp dir | `data/tmp` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth | — |
| `CLARITY_PROJECT_ID` | Microsoft Clarity | — |
| `KRDICT_API_KEY` | Korean dictionary API | — |

Also used elsewhere (not all on `Settings`): `GEMINI_LIVE_MODEL`, `GEMINI_IMAGE_MODEL`, `DALLE_*`, `FLUENCYPRO_WS_URL`, `ROMANIZE_MODE`, `MZTTS_API_URL`.

## System Dependencies

**ffmpeg** must be installed — used for audio conversion (e.g. PCM → 8kHz mono WAV) in FluencyPro and SpeechPro routes.

## Architecture

### Entry Point (`main.py`)

Thin bootstrap only:

1. `create_app()` from `backend.core.app`
2. Apply temp-dir env from settings
3. `initialize_database(settings.db_path)`
4. Optional `__main__` uvicorn on port 9002

### App Factory (`backend/core/app.py`)

`create_app()`:

- Loads settings + logging (`logs/detailed.log`, midnight rotation)
- Builds FastAPI app, Jinja2 templates, OAuth (authlib Google)
- Initializes Gemini / Gemini Live / OpenAI clients when keys present
- Populates `app.state` (settings, db helpers, AI clients, credit costs, SpeechPro helpers, …)
- Mounts `/static` and `/uploads`
- CORS from `settings.allowed_origins`
- Includes all routers

### Config (`backend/config.py`)

Frozen `Settings` dataclass. Prefer reading configuration from `request.app.state.settings` or fields already copied onto `app.state` — avoid scattering raw `os.getenv` in new route code.

### Database (`backend/database.py`)

SQLite at `data/users.db` (or `DB_PATH`). Schema created/migrated via `initialize_database()` and `ensure_*` helpers — no Alembic/migration framework.

Tables include: `users`, `sentence_scores`, `word_score_history`, attendance/LMS, media progress, RAG (`n_documents` / `n_chunks` / FTS5), admin logging, etc.

### Routers (`backend/routes/`)

Mounted in `backend/core/app.py`:

| Router | Key routes |
|---|---|
| `pages.py` | HTML GETs: `/`, `/dashboard`, `/video-learning`, `/onui-beats`, `/voice-call`, `/onui-grammar`, `/daily-expression`, `/sentence-evaluation`, `/learning-progress`, `/login`, `/signup`, `/mypage`, `/privacy`, admin pages |
| `auth.py` | `/api/signup`, `/api/login`, `/api/logout`, Google OAuth |
| `user.py` | Profile/password/credits APIs |
| `ai_services.py` | Content gen, image, chat, voice-call scenarios, WebSockets (`/ws/voice-call/{scenario_id}`, fluency) |
| `content.py` | Dashboard stats, expressions, textbooks, attendance, locale JSON (`/data/locales/{filename}`) |
| `media.py` | OnuiTube videos/transcripts/vocab, video lessons/progress |
| `stt.py` | STT proxy / Whisper / Google / Vosk / voice-call STT |
| `learning_progress.py` | `/api/learning/*` |
| `tts.py` | `/api/tts/*` |
| `speechpro.py` | `/api/speechpro/*` pronunciation evaluation |
| `roleplay.py` | `/roleplay`, `/api/roleplay/*` |
| `lms.py` | Grades, attendance, time-on-task |
| `admin.py` | `/api/admin/*` |

`deps.py` re-exports helpers from `backend.utils` — **import from `deps` inside routes**, not from `main` or ad-hoc globals.

### `backend/utils.py`

Auth (`get_current_user`, `get_session`, session tokens, password hashing), credits (`check_and_consume_credits`, `get_user_credits`), RAG helpers, Hangul romanizer, Ollama listing, audio helpers (`ensure_wav_16k_mono`, `transcribe_with_vosk`), JSON data loading.

Routers receive AI clients and DB helpers via `request.app.state`.

### Services (`backend/services/`)

| Service | Purpose |
|---|---|
| `speechpro_service.py` | Pronunciation evaluation (SpeechPro API + precomputed sentences) |
| `fluencypro_service.py` | Fluency evaluation |
| `learning_progress_service.py` | Per-user learning progress (SQLite) |
| `krdict_service.py` | Korean dictionary (KRDICT API) |
| `dalle_service.py` | Image generation (DALL-E / Gemini) |
| `tts_service.py` | Shared TTS / audio conversion helpers |
| `ai_services.py` | Shared AI helpers (e.g. pronunciation feedback) |
| `analytics_service.py` | Usage analytics |
| `onui_tube_catalog.py` | OnuiTube catalog annotation at page render |

### Session Auth & Credits

- Cookie-based sessions: signed token in `session_token` cookie; in-memory `active_sessions` cache
- Roles: `learner`, `instructor`, `system_admin` (+ `is_admin`)
- Google OAuth via authlib when client id/secret set
- Credits: `app.state.credit_costs` default `lesson=3, image=10, quiz=2, chat=2, tts=1, voice=5`; daily reset via `DAILY_CREDITS`
- Voice-call WebSocket auth reads the session cookie and is credit-gated

### Frontend

- `templates/base.html` — master layout, nav, i18n, character popup
- `templates/components/` — `character-popup.html`, `floating-buttons.html`, `ai-avatar.html`
- Feature JS/CSS in `static/js/` and `static/css/` (kebab-case, name-matched to templates)
- Tailwind via CDN (not compiled)

Notable pages: dashboard, daily-expression, video-learning, onui-beats, voice-call, ai-roleplay, content-generation, speechpro-practice, sentence-evaluation, learning-progress, onui-grammar, admin-* pages. Dev-only: `api-test.html`, `stt-multi-test.html`.

Uploads served at `/uploads`:

- profile / misc uploads
- `uploads/images/` — generated vocab images
- `uploads/audio/` — pronunciation recordings

### i18n (hybrid)

- **Static (curated)**: `data/locales/{ko,en,ja,zh,vi,ne}.json` via `data-i18n`
- **Google Website Translate** (no new JSON required): `id`, `mn`, `lo`
  - Loads English UI first, then hidden `translate.google.com` Element (`#google_translate_element` in `base.html`)
  - Cookie `googtrans=/en/{code}`; leaving Google mode reloads to clear DOM mutations
- Served static JSON at `/data/locales/` (`content.py`)
- Language in `localStorage` key `app_lang`
- FOUC prevention: `base.html` hides document until i18n applies
- **Korean practice content**: `class="notranslate"` / `translate="no"` on sentences, lyrics, captions, chat logs
- **Add new curated UI strings** to all static locale files (`ko/en/ja/zh/vi/ne`)
- Optional leftover `id.json`/`mn.json`/`lo.json` are **not used** when Google path is active

### Data Files (`data/`)

Static JSON used at runtime (partial list):

- `sentences.json`, `vocabulary.json`, `expressions.json`, `cultural-expressions.json`
- `pronunciation-words.json`, `speechpro-sentences.json`, `sp_ko_questions.json`
- `voice-call.json`, `roleplay-scenarios.json`, `onui-beats.json`
- `onui-tube.json`, `onui-tube-transcripts.json`
- `folktales.json`, `landing_intent.json`, `landing_intake.json`
- `word_image_cache.json`, `tongue-twister-metadata.json`
- `tts_cache/` — pre-generated TTS (`.bin` + `.json` metadata)
- `locales/` — UI translations

### Scripts (`scripts/`)

One-off tools only (not app runtime): locale gen/translate, sentence import, OnuiTube catalog/video/image pipelines, roleplay/folktale/landing images, TTS regen, domain setup, logrotate, ngrok helper.

### Dependency Note

`requirements.txt` pins `openai<2.0.0`. Code uses the v1 `OpenAI` client style — upgrading to v2 breaks DALL-E/Whisper integrations.

## Coding Conventions

- Python: 4-space indentation, snake_case modules and functions
- Templates: mirror existing Tailwind utility patterns; no new CSS frameworks
- Static assets: kebab-case; keep CSS/JS co-located by feature
- Prefer `request.app.state` and `backend.routes.deps` over importing from `main`
- Commits: `feat:`, `fix:`, `refactor:`, `chore:` with optional scope (e.g. `fix(ui): ...`)

## AI Backend Routing

`MODEL_BACKEND` selects the content LLM:

- `ollama` → local EXAONE via Ollama REST
- `openai` → OpenAI GPT SDK
- `gemini` → `google-genai` SDK

TTS (`TTS_BACKEND`) and STT (`STT_BACKEND`) are independent of `MODEL_BACKEND`.

Image generation (`dalle_service.py`): DALL-E when `OPENAI_API_KEY` is set, else Gemini image models.

Built-in Hangul→Latin romanizer (syllable tables) needs no extra package; optional `korean_romanizer` if installed.
