이제 모든 핵심 파일을 분석했습니다. 프로젝트 전체 구조를 상세히 설명하겠습니다.

---

# 📚 오누이 한국어 (Onui Korean) 프로젝트 전체 구조 분석

## 🏗️ 프로젝트 개요

**오누이 한국어**는 AI 기반 한국어 학습 웹 플랫폼입니다. FastAPI(Python) 백엔드와 Jinja2 템플릿 + Tailwind CSS 프론트엔드로 구성되어 있으며, Google Gemini / OpenAI GPT / Ollama 등 여러 AI 백엔드를 지원합니다.

---

## 📂 디렉토리 구조 및 핵심 파일

```
onui-ai/
├── main.py                        # 🎯 [엔트리 포인트] FastAPI 앱 생성, DB 초기화, 서버 실행
├── requirements.txt               # Python 의존성 목록
├── .env                           # 환경변수 설정 (보안 파일, 직접 읽기 불가)
├── .env.example                   # 환경변수 템플릿
│
├── backend/                       # 🧠 [백엔드 코어]
│   ├── config.py                  # 설정 관리 (환경변수 → Settings dataclass)
│   ├── database.py                # SQLite DB 스키마 정의 및 초기화
│   ├── utils.py                   # 공통 유틸리티 (인증, 비밀번호, 세션, 로마자 변환 등)
│   │
│   ├── core/
│   │   └── app.py                 # 🎯 [핵심] FastAPI 앱 팩토리 (라우터 등록, 의존성 주입)
│   │
│   ├── routes/                    # 📡 [API 라우터] - 각 기능별 엔드포인트
│   │   ├── pages.py              # HTML 페이지 라우팅 (GET 요청)
│   │   ├── auth.py               # 인증 (회원가입, 로그인, Google OAuth)
│   │   ├── speechpro.py          # 🎤 발음 평가 API (12개 엔드포인트)
│   │   ├── ai_services.py        # 🤖 AI 서비스 (콘텐츠 생성, 챗봇, 이미지 생성, 발화통화 WebSocket)
│   │   ├── stt.py                # 🎙️ STT (음성인식) - Whisper/Google/Vosk
│   │   ├── tts.py                # 🔊 TTS (음성합성) - Gemini/OpenAI/Google/MzTTS
│   │   ├── roleplay.py           # 🎭 AI 역할극 (역사 인물 대화)
│   │   ├── learning_progress.py  # 📊 학습 진도 추적
│   │   ├── lms.py                # 🏫 LMS (강의 출석, 성적)
│   │   ├── content.py            # 📖 콘텐츠 API (대시보드, 표현, 교재)
│   │   ├── media.py              # 🎬 미디어 API (OnuiTube 비디오)
│   │   ├── user.py               # 👤 사용자 프로필
│   │   ├── admin.py              # 🔧 관리자 페이지
│   │   └── deps.py               # 의존성 재-export (utils.py → 라우터)
│   │
│   └── services/                  # 🔌 [외부 API 연동 서비스]
│       ├── speechpro_service.py   # 🎤 SpeechPro 발음 평가 API 3단계 (GTP→Model→Score)
│       ├── ai_services.py         # 🤖 AI 피드백 생성 (발음 평가 피드백)
│       ├── fluencypro_service.py  # 유창성 평가
│       ├── dalle_service.py       # 🎨 DALL-E / Gemini 이미지 생성
│       ├── tts_service.py         # 🔊 TTS 공통 (오디오 변환 등)
│       ├── krdict_service.py      # 📖 국립국어원 사전 API
│       ├── learning_progress_service.py  # 학습 진도 서비스
│       ├── analytics_service.py   # 사용 분석
│       └── onui_tube_catalog.py   # OnuiTube 비디오 카탈로그 관리
│
├── templates/                     # 🖼️ [Jinja2 템플릿]
│   ├── base.html                 # 공통 레이아웃 (네비게이션, i18n)
│   ├── index.html                # 랜딩 페이지
│   ├── dashboard.html            # 사용자 대시보드
│   ├── speechpro-practice.html   # 🎤 발음 평가 페이지
│   ├── video-learning.html       # 🎬 OnuiTube 영상 학습
│   ├── onui-beats.html           # 🎵 K-Pop 가사 학습
│   ├── voice-call.html           # 📞 AI 발화 통화
│   ├── ai-roleplay.html          # 🎭 AI 역할극
│   ├── onui-grammar.html         # 📝 AI 문법 코치
│   ├── content-generation.html   # 📚 AI 교재 생성
│   ├── sentence-evaluation.html  # 문장 평가 (SpeechPro 연동)
│   ├── learning-progress.html    # 학습 진도
│   ├── daily-expression.html     # 오늘의 표현
│   ├── components/               # 재사용 가능한 컴포넌트
│   └── admin-*.html              # 관리자 페이지
│
├── static/                        # 🎨 [정적 파일]
│   ├── js/                       # JavaScript 파일
│   │   ├── speechpro-practice.js # 🎤 발음 평가 클라이언트 로직
│   │   ├── voice-call.js         # 발화 통화 클라이언트
│   │   ├── ai-roleplay.js        # 역할극 클라이언트
│   │   ├── i18n.js               # 국제화 (다국어 지원)
│   │   ├── auth.js               # 인증 관련
│   │   └── ...                   # 각 기능별 JS
│   ├── css/                      # CSS 파일 (기능별)
│   └── images/                   # 이미지
│
├── data/                          # 📊 [데이터 파일]
│   ├── users.db                  # SQLite 사용자 DB
│   ├── speechpro-sentences.json  # 🎤 SpeechPro 사전 계산 문장
│   ├── speechpro-sentences.json  # 발음 연습 문장 모음
│   ├── locales/                  # i18n 번역 파일 (ko/en/ja/zh)
│   ├── vocabulary.json           # 어휘 데이터
│   ├── sentences.json            # 문장 데이터
│   ├── onui-tube.json            # OnuiTube 비디오 메타데이터
│   ├── onui-beats.json           # K-Pop 음악/가사 데이터
│   ├── voice-call.json           # 발화 통화 시나리오
│   ├── roleplay-scenarios.json   # 역할극 시나리오
│   └── ...
│
├── scripts/                       # 🛠️ [유틸리티 스크립트]
│   ├── precompute_speechpro_sentences.py  # SpeechPro 문장 미리 생성
│   ├── generate_locales.py       # 로케일 파일 생성
│   └── ...
│
├── tests/                         # 🧪 [테스트]
├── docs/                          # 📝 [문서]
└── uploads/                       # 📁 [업로드 파일]
    ├── audio/                    # 발음 녹음 파일 (30일 후 자동 삭제)
    └── images/                   # 생성된 이미지
```

---

## 🎯 핵심 파일 기능 상세 설명

### 1️⃣ `main.py` — 애플리케이션 엔트리 포인트
- FastAPI 앱 인스턴스 생성
- 환경변수 로드 및 임시 디렉토리 설정
- SQLite 데이터베이스 초기화
- `uvicorn` 개발 서버 실행 (포트 9002)

### 2️⃣ `backend/core/app.py` — 🎯 **가장 핵심 파일** (앱 공장)
- **라우터 등록**: 13개의 모든 라우터를 `app.include_router()`로 등록
- **의존성 주입**: 모든 서비스, 클라이언트, 헬퍼 함수를 `app.state`에 저장
- **미들웨어**: CORS, 로깅 설정
- **정적 파일**: `/static`, `/uploads` 마운트
- **초기화**: Google OAuth, Gemini/OpenAI/Ollama 클라이언트, SpeechPro 헬퍼, TTS/STT 설정

### 3️⃣ `backend/config.py` — 설정 관리
- `Settings` dataclass로 환경변수 통합 관리
- `model_backend`, `db_path`, `api_key` 등 모든 설정 정의
- 50개 이상의 환경변수 처리

### 4️⃣ `backend/database.py` — 데이터베이스 스키마
- SQLite 데이터베이스 초기화 및 마이그레이션
- **핵심 테이블**: `users`, `sentence_scores`, `word_score_history`
- **LMS 테이블**: `lecture_attendance`, `study_sessions`
- **RAG 테이블**: `rag_settings`, `rag_documents`, `rag_chunks`, `rag_chunks_fts` (FTS5 전문 검색)
- **기타**: `pronunciation_attempt_history`, `saved_textbooks`, `user_video_progress` 등

### 5️⃣ `backend/utils.py` — 공통 유틸리티
- **인증**: `create_session_token()`, `parse_session_token()`, `hash_password()`, `verify_password()`
- **세션**: 쿠키 기반 세션 (HMAC 서명, PBKDF2 비밀번호)
- **크레딧**: `check_and_consume_credits()` — 일일 사용량 제한
- **한국어**: `romanize_korean()` — 한글→로마자 변환 (표준 국어 로마자 표기법)
- **AI**: `parse_model_output()` — AI JSON 응답 파싱
- **RAG**: `rag_search()`, `rag_get_settings()` — SQLite FTS5 기반 검색

---

## 📡 라우터별 상세 기능

### `routes/pages.py` — HTML 페이지 라우팅
- 모든 GET 요청 처리 (페이지 렌더링)
- 15개 이상의 페이지 라우트
- 인증 체크 후 템플릿 반환

### `routes/speechpro.py` — 🎤 발음 평가 (12개 엔드포인트)
| 엔드포인트 | 기능 |
|-----------|------|
| `GET /speechpro-practice` | 발음 평가 페이지 |
| `GET /api/speechpro/sentences` | 평가 문장 목록 (레벨 필터, 페이지네이션) |
| `GET /api/speechpro/precomputed` | 사전 계산된 문장 정보 조회 |
| `GET /api/speechpro/config` | SpeechPro API 설정 조회 |
| `POST /api/speechpro/evaluate` | 🎯 **통합 발음 평가** (프리셋 → Score / 전체 워크플로우) |
| `POST /api/speechpro/feedback` | AI 피드백 생성 |
| `POST /api/speechpro/batch-evaluate` | 배치 평가 (최대 3개 파일) |
| `POST /api/speechpro/gtp` | GTP API (텍스트→음소) |
| `POST /api/speechpro/model` | Model API (FST 생성) |
| `POST /api/speechpro/score` | Score API (발음 점수) |

### `routes/ai_services.py` — 🤖 AI 서비스 (25개 이상 엔드포인트)
- **콘텐츠 생성**: `POST /api/generate-content` (주제/레벨 기반 대화문 생성)
- **발화 통화**: `WS /ws/voice-call/{scenario_id}` (Gemini Live API 실시간 WebSocket)
- **이미지 생성**: `POST /api/gemini/image`, `POST /api/generate-image` (DALL-E 3 / Gemini)
- **챗봇**: `POST /api/chatbot`, `POST /api/messenger/chat`
- **문장 교정**: `POST /api/fluency-check`, `POST /api/pronunciation-check`
- **유창성**: `POST /api/fluencypro/analyze`
- **Ollama**: `GET /api/ollama/models`, `POST /api/ollama/test`
- **단어 이미지 캐시**: `GET/POST /api/word-images/cache`

### `routes/auth.py` — 인증
- `POST /api/signup` — 회원가입
- `POST /api/login` — 로그인
- `POST /api/logout` — 로그아웃
- `GET /api/login/google` — Google OAuth 로그인

### `routes/stt.py` — 음성 인식
- `POST /api/stt/whisper` — OpenAI Whisper
- `POST /api/stt/google` — Google Cloud STT
- `POST /api/stt/vosk` — 로컬 Vosk
- `POST /api/stt/proxy` — STT 프록시

### `routes/tts.py` — 음성 합성
- `POST /api/tts/generate` — TTS 생성
- `GET /api/tts/info` — TTS 서버 정보

### `routes/roleplay.py` — AI 역할극
- `GET /roleplay` — 역할극 페이지
- `POST /api/roleplay/chat` — 역할극 대화 API

### `routes/lms.py` — 학습 관리 시스템
- `GET /api/lms/grades` — 성적 조회
- `POST /api/lms/attendance` — 출석 기록

---

## 🔌 외부 API 연동 서비스

### `services/speechpro_service.py` — 🎤 SpeechPro 발음 평가
- **3단계 워크플로우**:
  1. **GTP** (Grapheme-to-Phoneme): 한글→음소 변환
  2. **Model**: FST 발음 모델 생성
  3. **Score**: 사용자 음성 발음 평가 (음소 단위 정밀 분석)
- **사전 계산 캐싱**: JSON 파일 + 런타임 메모리 캐시 (중복 API 호출 방지)
- **자동 재시도**: Score API 5xx 오류 시 3회 재시도
- **공백 정규화**: 다양한 유니코드 공백 문자 처리

### `services/ai_services.py` — 🤖 AI 피드백
- `generate_pronunciation_feedback()`: 발음 평가 결과를 바탕으로 AI 코치 피드백 생성
- Gemini/OpenAI/Ollama 모두 지원

### `services/dalle_service.py` — 🎨 이미지 생성
- DALL-E 3 (OpenAI) 우선, Gemini fallback
- 한글→영어 프롬프트 자동 번역
- `word_image_cache.json` 캐싱

---

## 🌐 인프라

| 서비스 | URL | 설명 |
|--------|-----|------|
| 개발 서버 | `http://localhost:9002` | uvicorn hot-reload |
| 프로덕션 | `https://opportunity.ai.kr` | Nginx + SSL |
| 백업 도메인 | `https://onuiai.kr` | Nginx + SSL |
| SpeechPro API | `http://112.220.79.222:33005/speechpro` | 외부 발음 평가 서버 |
| MzTTS | `http://112.220.79.218:56014` | 한국어 TTS |

---

## 🔑 데이터 흐름 예시 (SpeechPro 발음 평가)

```
1. 사용자 브라우저에서 문장 선택 + 녹음
       ↓
2. POST /api/speechpro/evaluate (audio + text)
       ↓
3. 라우터(speechpro.py)가 요청 수신
   ├─ 오디오 파일 업로드 저장 (uploads/audio/)
   ├─ STT로 음성 인식 (OpenAI Whisper / Google STT)
   ├─ 사전 계산 문장 확인 (캐시)
   │   ├─ 있으면 → 바로 Score API 호출
   │   └─ 없으면 → GTP → Model → Score 전체 워크플로우
   ├─ AI 피드백 생성 (Gemini/OpenAI/Ollama)
   ├─ LMS 성적 자동 저장 (SQLite)
   └─ 결과 반환 (score, details, ai_feedback)
       ↓
4. 클라이언트 JS가 결과 표시
   ├─ 종합 점수 (Dashboard 탭)
   ├─ 음소별 상세 점수 (Detailed Analysis 탭)
   └─ AI 코치 피드백 (AI Coach 탭)
```

---

## ⚡ 핵심 포인트 요약

| 항목 | 내용 |
|------|------|
| **백엔드 프레임워크** | FastAPI (Python 3.12) |
| **데이터베이스** | SQLite (WAL 모드) |
| **템플릿 엔진** | Jinja2 |
| **CSS** | Tailwind CSS (CDN) |
| **기본 AI** | Google Gemini 2.0 Flash |
| **대체 AI** | OpenAI GPT-4o-mini / Ollama (EXAONE) |
| **TTS** | Gemini / OpenAI / Google Cloud / MzTTS |
| **STT** | OpenAI Whisper / Google Cloud / Vosk |
| **발음 평가** | **SpeechPro API** (외부) |
| **인증** | 세션 쿠키 (HMAC) + Google OAuth |
| **다국어** | ko/en/ja/zh (클라이언트 i18n) |
| **크레딧 시스템** | 일일 100크레딧 (자정 리셋) |
| **배포** | PM2 + Nginx + SSL (Let's Encrypt) |

이 프로젝트는 **발음 평가(SpeechPro)**와 **AI 서비스(Gemini/OpenAI/Ollama)**의 연동이 가장 핵심적인 기능이며, `backend/core/app.py`에서 모든 의존성을 통합 관리하고, 각 `routes/*.py`에서 기능별 API를 제공하는 구조입니다.