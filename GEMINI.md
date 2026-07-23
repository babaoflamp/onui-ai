# GEMINI.md - Project Overview

This document provides a comprehensive overview of the Onui Korean project, designed to serve as instructional context for future interactions with the Gemini CLI.

## Project Overview

Onui Korean is an AI-based Korean learning platform that offers a variety of features including pronunciation evaluation, AI conversation, video learning, and K-Pop games. It supports four languages: Korean, English, Japanese, and Chinese.

**Key Technologies:**
*   **Backend:** FastAPI (Python 3.12), SQLite
*   **Frontend:** Jinja2 Templates, Tailwind CSS (CDN)
*   **AI:** Google Gemini (default) / OpenAI GPT / Ollama
*   **TTS:** Gemini TTS / OpenAI TTS / Google Cloud TTS / MzTTS
*   **STT:** Local (Vosk) / Google Cloud / OpenAI Whisper
*   **Pronunciation Evaluation:** SpeechPro API (phoneme-level analysis)

**Architecture Highlights:**
The application is structured with a FastAPI backend handling API endpoints, services for external AI integrations, and a Jinja2 templating system for the frontend. User data is managed with SQLite. The system is designed to be highly configurable, allowing for different AI backends (Gemini, OpenAI, Ollama), TTS, and STT services via environment variables.

## Building and Running

### 1. Environment Setup

To set up the development environment, clone the repository and install dependencies:

```bash
git clone https://github.com/babaoflamp/onui-ai.git
cd onui-ai

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Variables

Copy the example environment file and configure it:

```bash
cp .env.example .env
```

Key environment variables to configure in `.env`:

*   `MODEL_BACKEND`: `gemini` | `openai` | `ollama` (default: `ollama`)
*   `GEMINI_API_KEY`: Your Google Gemini API key
*   `OPENAI_API_KEY`: Your OpenAI API key (for DALL-E, Whisper)
*   `OLLAMA_URL`, `OLLAMA_MODEL`: For local LLM usage
*   `TTS_BACKEND`: `gemini` | `openai` | `google` | `mztts`
*   `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`: For Google OAuth social login
*   `SECRET_KEY`: Session signing key (randomly generated if not provided)

### 3. Server Execution

To run the development server with hot reload on port 9002:

```bash
source .venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port 9002 --reload
```

Access the application in your browser at `http://localhost:9002`.

### Production Deployment

The project can be managed in production using PM2.

**Service Management with PM2:**
```bash
./start-service.sh    # Start onui-ai via PM2
./stop-service.sh     # Stop the services
pm2 status            # Check process status
pm2 logs onui-ai      # View application logs
pm2 restart onui-ai   # Restart the application
```
PM2 configuration is in `ecosystem.config.js`. Logs are stored in `logs/pm2-out.log` and `logs/pm2-error.log`.

**Nginx + SSL Setup (for `opportunity.ai.kr`):**
The `scripts/setup-domain-onui-ai-kr.sh` script automates Nginx reverse proxy configuration, Let's Encrypt SSL, and UFW firewall settings. It requires DNS `A` records to be propagated.
```bash
sudo bash scripts/setup-domain-onui-ai-kr.sh
```
Nginx configuration is located in `nginx-opportunity.ai.kr.conf`.

## Development Conventions

*   **Backend:** Developed with FastAPI. New features should be implemented in `backend/routes/` for API endpoints and `backend/services/` for external API integrations.
*   **Frontend:** Uses Jinja2 templates for rendering. Reusable UI components are stored in `templates/components`.
*   **Styling:** Utilizes Tailwind CSS for styling.
*   **AI Services:** Integrates with various AI services, configurable via the `MODEL_BACKEND` environment variable.
*   **Database:** Employs SQLite for user data, with schema definition and initialization in `main.py`.
*   **Dependencies:** Python dependencies are managed with `pip` and listed in `requirements.txt`.

## Project Structure

```
onui-ai/
├── main.py                  # Main FastAPI application (routes, authentication, DB initialization)
├── requirements.txt         # Python dependencies
├── restart.sh               # Service restart script
│
├── backend/
│   ├── routes/              # Feature-specific router modules (e.g., roleplay, tts, speechpro, learning_progress, lms)
│   ├── services/            # External API integration services
│   └── utils.py             # Common utility functions
│
├── templates/               # Jinja2 HTML templates
│   ├── base.html            # Common layout (navigation, i18n)
│   ├── components/          # Reusable UI components
│   └── *.html               # Page-specific templates
│
├── static/                  # Static assets (js, css, images)
│   ├── js/
│   ├── css/
│   └── images/
│
├── data/                    # Data files and databases
│   ├── users.db             # SQLite user database
│   ├── locales/             # i18n translation files (ko/en/ja/zh)
│   ├── roleplay-scenarios.json
│   ├── vocabulary.json
│   ├── sentences.json
│   ├── folktales.json
│   └── tts_cache/           # TTS audio cache
│
└── docs/                    # API documentation, design documents
```
