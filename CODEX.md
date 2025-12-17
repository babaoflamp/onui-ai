# CODEX.md

Guidance for Codex (GPT-5) when working inside this repository via the Codex CLI.

## Quick Orientation

- **Project**: 오누이 한국어 (FastAPI + Jinja2 + vanilla JS) with extensive AI integrations (SpeechPro, FluencyPro, Ollama/Gemini, MzTTS).
- **Entry point**: `main.py` hosts all routes, middleware, auth, and integrations.
- **Key data**: JSON/CSV under `data/`; SQLite database at `data/users.db`.
- **Admin docs**: `ADMIN_SYSTEM.md` describes role-based admin flows.

## Environment Setup

```bash
# From repo root
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# Optional utilities
pip install korean-romanizer
```

To run the dev server:

```bash
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 9000 --reload
# or
python main.py
```

## Codex Workflow Tips

1. **Respect sandboxing**: Commands default to sandboxed execution. Escalate only when necessary and include concise justifications.
2. **Use fast tools**: Prefer `rg` for searching text (`rg "needle"`), `rg --files` for listings, and `fd` if available for directories.
3. **Editing**:
   - Use `apply_patch` for targeted modifications unless a formatter or generator is more appropriate.
   - Keep edits ASCII unless the file already requires Unicode (Korean text is common here; mirror existing style).
   - Add comments only when they clarify non-obvious logic.
4. **Planning**: For multi-step tasks, create a plan via the planning tool (skip for trivial edits). Update the plan after executing each step.
5. **Testing**: Run targeted commands such as `pytest`, `python -m pytest tests/...`, or feature-specific scripts when changes warrant it. Summarize key results rather than dumping raw logs.

## Common Commands

```bash
# Inspect routes or services
rg "app\.get" -n main.py
rg "def call_speechpro" -n backend/services

# Database peek
sqlite3 data/users.db ".tables"
sqlite3 data/users.db "PRAGMA table_info('users');"

# Static/template search
rg "speechpro-practice" -n templates static
```

## Deployment Notes

- Systemd service file: `onui-ai.service`
- Helper scripts: `start-service.sh`, `stop-service.sh`
- Production logs: `logs/`
- External exposure via local `ngrok` binary (see README instructions)

## When In Doubt

- Check `CLAUDE.md` for parallel agent guidelines.
- Review `README.md` for feature inventory and API list.
- Confirm active environment variables in `.env` before invoking external APIs.

Keep responses concise, reference files with the required `path:line` format, and suggest logical next actions after delivering changes or analyses.
