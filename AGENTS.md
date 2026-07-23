# Repository Guidelines

## Project Overview
**Onui Korean** (오누이 한국어) is an AI-powered Korean language learning web app. Backend: FastAPI + SQLite. Frontend: Jinja2 + Tailwind (CDN). Dev/prod server port: **9002**.

## Project Structure
- `main.py` — thin entry: `create_app()`, DB init, uvicorn on port 9002
- `backend/config.py` — `Settings` dataclass + `load_settings()` (env-driven)
- `backend/core/app.py` — app factory: middleware, `app.state`, router mounts
- `backend/database.py` — SQLite schema init/migrations (`initialize_database`)
- `backend/utils.py` — auth, credits, romanizer, RAG helpers, audio utils
- `backend/routes/` — FastAPI routers (import deps from `deps.py`, not `main`)
- `backend/services/` — SpeechPro, TTS, DALL-E, FluencyPro, learning progress, etc.
- `templates/` — Jinja2 pages; `templates/components/` for partials
- `static/js|css/` — feature assets (kebab-case, co-located by feature)
- `data/` — JSON datasets, locales, SQLite (`users.db`), TTS cache
- `tests/unit/` — pytest suite
- `scripts/` — one-off data/image/domain utilities (not runtime)

## Build, Test, and Development
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # never commit real secrets

# Dev (hot reload) — always port 9002
python -m uvicorn main:app --host 0.0.0.0 --port 9002 --reload
# or: python main.py

pkill -f uvicorn       # stop dev server
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

## Coding Style
- Python: 4-space indent, snake_case modules/functions
- Templates: match existing Tailwind patterns; no new CSS frameworks
- Static assets: kebab-case; keep CSS/JS paired with the feature template
- Prefer mirroring surrounding style over reformatting
- Routes: use `request.app.state` for clients/settings; import helpers from `backend.routes.deps`
- Commit style: `feat:`, `fix:`, `refactor:`, `chore:` (+ optional scope)

## Testing
- Tests live under `tests/unit` (`test_*.py` / `test_*`)
- Run: `python -m pytest` or `python -m pytest tests/unit`

## Configuration & Secrets
- Configure via `.env` (see `.env.example` and `backend/config.py`)
- Key selectors: `MODEL_BACKEND` (`gemini`|`openai`|`ollama`), `TTS_BACKEND`, `STT_BACKEND`
- Production requires `APP_ENV=production` + `SECRET_KEY`
- Do not commit secrets, `.env`, or local DB copies

## Architecture Notes (for agents)
- Routers are mounted in `backend/core/app.py`, not `main.py`
- Cookie sessions (`session_token`); roles: `learner` | `instructor` | `system_admin`
- AI endpoints gated by daily credits (`DAILY_CREDITS` / `app.state.credit_costs`)
- i18n hybrid (`static/js/i18n.js`):
  - **Static locales** (curated JSON): `ko`, `en`, `ja`, `zh`, `vi`, `ne` → `data/locales/{lang}.json`
  - **Google Website Translate**: `id`, `mn`, `lo` (and any non-static lang) → English UI + hidden Google Element
- New curated UI strings: add keys to **all static** locale files (`ko/en/ja/zh/vi/ne`)
- Korean learning content: mark with `class="notranslate"` / `translate="no"` so Google does not translate practice text
- `openai` package is pinned `<2.0.0` — do not upgrade without migration

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

## PRs
- Concise summary, test notes, and screenshots for UI changes
