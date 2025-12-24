# Repository Guidelines

## Project Structure & Module Organization
- `main.py` is the FastAPI entry point.
- `backend/` holds business logic (`services/`), lightweight models (`models/`), and utilities (`utils/`).
- `templates/` contains Jinja2 HTML templates grouped by feature area.
- `static/` contains CSS, JS, and images; feature-specific assets use kebab-case names (e.g., `pronunciation-practice.css`).
- `data/` stores JSON datasets and SQLite files used by the app.
- `tests/` is organized into `unit/`, `integration/`, and `api/` directories.
- `docs/`, `scripts/`, and `tools/` contain documentation, utilities, and helper scripts.

## Build, Test, and Development Commands
- `python -m venv .venv` and `source .venv/bin/activate` to create/activate a virtualenv.
- `python -m pip install -r requirements.txt` to install dependencies.
- `python -m uvicorn main:app --host 0.0.0.0 --port 9000 --reload` for the hot-reload dev server.
- `python main.py` for a simple local run without uvicorn flags.
- `pkill -f uvicorn` to stop the dev server.
- `./start-service.sh` and `./stop-service.sh` for systemd service workflows.

## Coding Style & Naming Conventions
- Python: 4-space indentation; keep modules in snake_case (e.g., `learning_progress_service.py`).
- Templates: keep Jinja2 structure minimal and match existing Tailwind utility patterns.
- Static assets: prefer kebab-case filenames and colocate CSS/JS with the feature they style.
- When in doubt, mirror the surrounding file’s style instead of reformatting.

## Testing Guidelines
- Place tests under `tests/unit`, `tests/integration`, and `tests/api`.
- Use pytest: `python -m pytest` or scoped runs like `python -m pytest tests/unit`.
- Name tests `test_*.py` and test functions `test_*` for pytest discovery.

## Commit & Pull Request Guidelines
- Recent history mixes conventional commits and descriptive summaries. Prefer:
  - `feat: ...`, `fix: ...`, `chore: ...`, `refactor: ...`
  - Optional scope: `feat(ui): ...`
- PRs should include a concise summary, test notes, and screenshots for UI changes.

## Configuration & Secrets
- Use `.env` for local configuration; `MODEL_BACKEND`, `OLLAMA_URL`, and related values are documented in `README.md`.
- Do not commit secrets or local database copies; use `.env.example` as the template.
