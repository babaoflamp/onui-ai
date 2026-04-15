# 오누이 한국어 (Onui Korean)

AI 기반 한국어 학습 플랫폼 — 발음 평가, AI 대화, 영상 학습, K-Pop 게임까지 한 곳에서.

---

## 주요 기능

| 메뉴 | URL | 설명 |
|---|---|---|
| 홈 대시보드 | `/dashboard` | 학습 현황, 출석 스트릭, 기능 바로가기 |
| 오늘의 표현 | `/daily-expression` | 매일 새로운 한국어 표현 + 문화 맥락 |
| OnuiTube | `/video-learning` | 한/영 이중 자막 영상 + 클릭 사전 |
| 오누이 비츠 | `/onui-beats` | K-Pop 가사 빈칸 채우기 게임 |
| AI 음성 통화 | `/voice-call` | AI 튜터와 실시간 음성 회화 연습 |
| AI 역할극 | `/roleplay` | 역사 인물·상황별 시나리오 대화 |
| AI 교재 | `/content-generation` | 주제·레벨 맞춤 대화문·단어장 자동 생성 |
| 발음 점수 측정 | `/speechpro-practice` | 예문 낭독 → 음소 단위 발음 점수 |
| 자유 발음 분석 | `/sentence-evaluation` | 원하는 문장 자유 입력 → AI 발음 코칭 |
| 내 학습 보고서 | `/learning-progress` | 학습 통계, 발음 점수 추이, 출석 현황 |

> 4개 언어 지원: 한국어 · English · 日本語 · 中文

---

## 기술 스택

- **Backend**: FastAPI (Python 3.12), SQLite
- **Frontend**: Jinja2 Templates, Tailwind CSS (CDN)
- **AI**: Google Gemini (기본) / OpenAI GPT / Ollama (EXAONE 로컬)
- **TTS**: Gemini TTS / OpenAI TTS / Google Cloud TTS / MzTTS
- **STT**: Local (Vosk) / Google Cloud / OpenAI Whisper
- **발음 평가**: SpeechPro API (음소 단위 분석)

---

## 설치 및 실행

### 1. 환경 설정

```bash
git clone https://github.com/babaoflamp/onui-ai.git
cd onui-ai

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 환경 변수

`.env.example`을 복사해서 `.env` 파일 생성:

```bash
cp .env.example .env
```

주요 설정:

```bash
# AI 백엔드 선택: gemini | openai | ollama
MODEL_BACKEND=gemini
GEMINI_API_KEY=your_gemini_api_key

# OpenAI (DALL-E, Whisper 사용 시)
OPENAI_API_KEY=your_openai_api_key

# Ollama (로컬 LLM 사용 시)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=exaone3.5:2.4b

# TTS 백엔드: gemini | openai | google | mztts
TTS_BACKEND=gemini

# Google OAuth (소셜 로그인 사용 시)
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
```

### 3. 서버 실행

```bash
# 개발 서버 (hot reload, 포트 9002)
source .venv/bin/activate
python -m uvicorn main:app --host 0.0.0.0 --port 9002 --reload
```

```bash
# 재시작 스크립트 (기존 프로세스 자동 종료 후 재시작)
./restart.sh
```

브라우저에서 `http://localhost:9002` 접속

---

## 환경 변수 전체 목록

| 변수 | 설명 | 기본값 |
|---|---|---|
| `MODEL_BACKEND` | AI 백엔드: `gemini` / `openai` / `ollama` | `ollama` |
| `GEMINI_API_KEY` | Gemini API 키 | — |
| `GEMINI_MODEL` | Gemini 모델명 | `gemini-2.5-flash` |
| `OPENAI_API_KEY` | OpenAI API 키 | — |
| `OLLAMA_URL` | Ollama 서버 주소 | `http://localhost:11434` |
| `OLLAMA_MODEL` | Ollama 모델명 | `exaone3.5:2.4b` |
| `TTS_BACKEND` | TTS 백엔드: `gemini` / `openai` / `google` / `mztts` | `gemini` |
| `STT_BACKEND` | STT 백엔드: `openai` / `google` / `vosk` / `local` | auto |
| `MZTTS_API_URL` | MzTTS 서버 주소 | `http://112.220.79.218:56014` |
| `ROMANIZE_MODE` | 로마자 표기: `force` / `prefer` | `force` |
| `SECRET_KEY` | 세션 서명 키 | 랜덤 생성 |
| `GOOGLE_CLIENT_ID` | Google OAuth 클라이언트 ID | — |
| `GOOGLE_CLIENT_SECRET` | Google OAuth 시크릿 | — |

---

## 프로젝트 구조

```
onui-ai/
├── main.py                  # FastAPI 앱 (라우트, 인증, DB 초기화)
├── requirements.txt
├── restart.sh               # 서비스 재시작 스크립트
│
├── backend/
│   ├── routes/              # 기능별 라우터 모듈
│   │   ├── roleplay.py      # AI 역할극
│   │   ├── tts.py           # TTS API
│   │   ├── speechpro.py     # 발음 평가
│   │   ├── learning_progress.py
│   │   └── lms.py           # LMS (성적·출결)
│   ├── services/            # 외부 API 연동 서비스
│   └── utils.py             # 공통 유틸리티
│
├── templates/               # Jinja2 HTML 템플릿
│   ├── base.html            # 공통 레이아웃 (네비, i18n)
│   ├── components/          # 재사용 컴포넌트
│   └── *.html               # 페이지별 템플릿
│
├── static/
│   ├── js/                  # 페이지별 JavaScript
│   ├── css/                 # 페이지별 CSS
│   └── images/
│
├── data/
│   ├── users.db             # SQLite 사용자 DB
│   ├── locales/             # i18n 번역 파일 (ko/en/ja/zh)
│   ├── roleplay-scenarios.json
│   ├── vocabulary.json      # 72개 어휘 (A1-B2)
│   ├── sentences.json       # 35개 연습 문장
│   ├── folktales.json       # 10개 전래동화
│   └── tts_cache/           # TTS 오디오 캐시
│
└── docs/                    # API 문서, 설계 문서
```

---

## 개발자

김영훈 (Kim Young-hoon) — Mediazen
