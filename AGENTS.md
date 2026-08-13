# Agent Guidelines for Onui Korean (OAI)

## Core Commands
- **Run dev server**: `.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 9002 --reload` (or `.venv/bin/python main.py`)
- **Run all tests**: `.venv/bin/python -m pytest` (*Must* use `.venv/bin/python -m pytest` or set `PYTHONPATH=.`; bare `pytest` fails on `backend` imports)
- **Run single test**: `.venv/bin/python -m pytest tests/unit/test_config.py`
- **Audit OnuiTube catalog**: `.venv/bin/python scripts/audit_onuitube_catalog.py`
- **PM2 operations**: `./start-service.sh` | `./stop-service.sh` | `./restart.sh` | `pm2 logs onui-ai`

## Architecture & Code Conventions
- **App entrypoint & wiring**: `main.py` initializes DB and calls `create_app()`. Router mounting, middleware, and `app.state` bindings live in `backend/core/app.py`.
- **Router dependencies**: Route files in `backend/routes/` MUST import dependencies from `backend.routes.deps` (not directly from `main`). Access clients and config via `request.app.state`.
- **Database & schema**: SQLite DB at `data/users.db`. Tables and column migrations are handled automatically in `backend/database.py` via `initialize_database()` and `_add_missing_columns()`. No Alembic or external migration tools are used.
- **Frontend & templates**: Jinja2 templates (`templates/`) with Tailwind CSS via CDN. No frontend build/bundling step. Pair JS/CSS files in `static/js/` and `static/css/` named in kebab-case matching the template.
- **Package pinning**: `openai` is pinned to `<2.0.0` (`requirements.txt`). Do not use OpenAI SDK v1+ client syntax in backend calls.
- **System dependency**: `ffmpeg` must be installed on the host for audio processing (SpeechPro/TTS).

## Multilingual / i18n Rules
- **Hybrid i18n (`static/js/i18n.js`)**:
  - **Static locales**: `ko`, `en`, `ja`, `zh`, `vi`, `ne` stored in `data/locales/{lang}.json`.
  - **Dynamic locales**: `id`, `mn`, `lo` render English UI and rely on hidden Google Website Translate element.
- **Adding UI text**: Any new UI string key MUST be added to all 6 static locale files (`ko/en/ja/zh/vi/ne`).
- **Protect Korean practice content**: Wrap practice text elements in `class="notranslate"` or `translate="no"` so Google Translate does not alter practice text.

## Config & Environment
- Config loaded via `backend/config.py` from `.env`.
- Key backend selectors: `MODEL_BACKEND` (`gemini`|`openai`|`ollama`), `TTS_BACKEND`, `STT_BACKEND`.
- Production requires `APP_ENV=production` and `SECRET_KEY`.
