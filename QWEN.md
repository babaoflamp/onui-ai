# QWEN.md — Onui Korean (오누이 한국어)

AI-powered Korean language learning web app. Backend: FastAPI + SQLite. Frontend: Jinja2 + Tailwind (CDN). Dev/prod server port: **9002**.

---

## Project Structure

```
onui-ai/
├── main.py                  # Entry: create_app(), DB init, uvicorn on port 9002
├── backend/
│   ├── config.py            # Settings dataclass + load_settings() (env-driven)
│   ├── core/app.py          # App factory: middleware, app.state, router mounts
│   ├── database.py          # SQLite schema init/migrations
│   ├── utils.py             # Auth, credits, romanizer, RAG helpers, audio utils
│   ├── routes/              # FastAPI routers (import from deps.py, not main)
│   │   ├── pages.py         # HTML page GET routes
│   │   ├── auth.py          # Signup/login/logout, Google OAuth
│   │   ├── user.py          # My page, password change, credits
│   │   ├── ai_services.py   # AI voice call (WebSocket), content gen, image gen
│   │   ├── content.py       # Expressions, textbooks, attendance, dashboard stats
│   │   ├── media.py         # OnuiTube videos, subtitles, vocabulary, progress
│   │   ├── stt.py           # STT proxy (Whisper/Google/Vosk)
│   │   ├── tts.py           # TTS API
│   │   ├── speechpro.py     # Pronunciation scoring (SpeechPro)
│   │   ├── roleplay.py      # AI roleplay scenarios
│   │   ├── learning_progress.py  # Learning progress tracking
│   │   ├── lms.py           # LMS (grades, attendance, study time)
│   │   ├── admin.py         # Admin dashboard
│   │   └── deps.py          # Common dependency re-exports
│   └── services/            # External API integrations
│       ├── speechpro_service.py
│       ├── fluencypro_service.py
│       ├── dalle_service.py
│       ├── krdict_service.py
│       ├── learning_progress_service.py
│       ├── onui_tube_catalog.py
│       └── analytics_service.py
├── templates/               # Jinja2 HTML templates
│   ├── base.html            # Common layout (nav, i18n)
│   ├── components/          # Reusable components
│   └── *.html               # Page templates
├── static/
│   ├── js/                  # Feature JS (kebab-case, co-located)
│   ├── css/                 # Feature CSS (kebab-case, co-located)
│   ├── images/tube/         # OnuiTube thumbnails
│   └── video/               # OnuiTube MP4 videos
├── data/
│   ├── users.db             # SQLite user DB
│   ├── locales/             # i18n: ko/en/ja/zh/vi/ne/id/mn/lo
│   ├── vocabulary.json      # 72 vocab words (A1-B2)
│   ├── sentences.json       # 35 practice sentences
│   ├── voice-call.json      # AI voice call scenarios
│   ├── roleplay-scenarios.json
│   ├── onui-tube.json       # Video metadata
│   ├── onui-tube-transcripts.json
│   └── tts_cache/           # TTS audio cache
├── scripts/                 # One-off data/image/domain utilities
├── tests/unit/              # pytest test suite
└── docs/                    # Design docs
```

---

## Feature URL Map

| Feature | Route |
|---|---|
| Dashboard | `/dashboard` |
| Daily Expression | `/daily-expression` |
| OnuiTube | `/video-learning` |
| Onui Beats | `/onui-beats` |
| AI Voice Call | `/voice-call` |
| AI Roleplay | `/roleplay` |
| Content Generation | `/content-generation` |
| Pronunciation (SpeechPro) | `/speechpro-practice` |
| Sentence Evaluation | `/sentence-evaluation` |
| Learning Progress | `/learning-progress` |
| AI Grammar Coach | `/onui-grammar` |

---

## Build, Test, and Run

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # never commit real secrets

# Dev (hot reload) — always port 9002
python -m uvicorn main:app --host 0.0.0.0 --port 9002 --reload
# or: python main.py

pkill -f uvicorn       # stop dev server

# Tests
python -m pytest
python -m pytest tests/unit
```

### Production (PM2)
```bash
./start-service.sh     # start via PM2
./stop-service.sh
./restart.sh
pm2 status | pm2 logs onui-ai | pm2 restart onui-ai
```
PM2 config: `ecosystem.config.js`. Logs: `logs/pm2-out.log`, `logs/pm2-error.log`.

Host dependency: **ffmpeg** (audio conversion for SpeechPro / FluencyPro).

---

## Configuration & Secrets

- All settings via `.env` (see `.env.example` and `backend/config.py`)
- Key selectors: `MODEL_BACKEND` (`gemini`|`openai`|`ollama`), `TTS_BACKEND`, `STT_BACKEND`
- Production requires `APP_ENV=production` + `SECRET_KEY`
- Do not commit secrets, `.env`, or local DB copies

---

## Coding Style & Conventions

- **Python**: 4-space indent, snake_case modules/functions
- **Templates**: match existing Tailwind patterns; no new CSS frameworks
- **Static assets**: kebab-case; keep CSS/JS paired with the feature template
- **Prefer mirroring** surrounding style over reformatting
- **Routes**: use `request.app.state` for clients/settings; import helpers from `backend.routes.deps`
- **Routers**: new features go in `backend/routes/` and are mounted in `backend/core/app.py` (not `main.py`)
- **Services**: external API logic goes in `backend/services/`
- **Commit style**: `feat:`, `fix:`, `refactor:`, `chore:` (+ optional scope)
- **openai** package is pinned `<2.0.0` — do not upgrade without migration

---

## i18n (Hybrid)

- **Static locales** (curated JSON): `ko`, `en`, `ja`, `zh`, `vi`, `ne` → `data/locales/{lang}.json`
- **Google Website Translate**: `id`, `mn`, `lo` (and any non-static lang) → English UI + hidden Google Element
- **New curated UI strings**: add keys to **all static** locale files (`ko/en/ja/zh/vi/ne`)
- **Korean learning content**: mark with `class="notranslate"` / `translate="no"` so Google does not translate practice text

---

## Architecture Notes

- **App factory**: `main.py` calls `create_app()` from `backend/core/app.py` — all router mounts, middleware, and `app.state` setup live there
- **Cookie sessions**: `session_token` cookie; roles: `learner` | `instructor` | `system_admin`
- **AI endpoints**: gated by daily credits (`DAILY_CREDITS` / `app.state.credit_costs`)
- **DB migrations**: `main.py` uses `_ensure_*` helpers for schema changes; no migration framework
- **Tests**: live under `tests/unit/` as `test_*.py`

---

## Developer

김영훈 (Kim Young-hoon) — Mediazen
