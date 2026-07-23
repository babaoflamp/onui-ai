# 오누이 한국어 (Onui Korean)

AI 기반 한국어 학습 플랫폼 — 발음 평가, AI 대화, 영상 학습, K-Pop 게임까지 한 곳에서.

---

## 주요 기능

| 메뉴 | URL | 설명 |
|---|---|---|
| 홈 대시보드 | `/dashboard` | 학습 현황, 출석 스트릭, 기능 바로가기 |
| 오늘의 표현 | `/daily-expression` | 매일 새로운 한국어 표현 + 문화 맥락 |
| OnuiTube | `/video-learning` | 50개 숏폼 영상 + 이중 자막 + 클릭 사전 + 진도 저장 |
| 오누이 비츠 | `/onui-beats` | K-Pop 가사 빈칸 채우기 게임 |
| AI 음성 통화 | `/voice-call` | AI 튜터와 실시간 음성 회화 연습 |
| AI 역할극 | `/roleplay` | 역사 인물·상황별 시나리오 대화 |
| AI 교재 | `/content-generation` | 주제·레벨 맞춤 대화문·단어장 자동 생성 |
| 발음 점수 측정 | `/speechpro-practice` | 예문 낭독 → 음소 단위 발음 점수 |
| 자유 발음 분석 | `/sentence-evaluation` | 원하는 문장 자유 입력 → AI 발음 코칭 |
| 내 학습 보고서 | `/learning-progress` | 학습 통계, 발음 점수 추이, 출석 현황 |

> 9개 UI 언어: 한국어 · English · 日本語 · 中文 · Tiếng Việt · नेपाली (정적 번역) + Indonesia · Монгол · ລາວ (Google 웹사이트 번역)

---

## 기술 스택

- **Backend**: FastAPI (Python 3.12), SQLite
- **Frontend**: Jinja2 Templates, Tailwind CSS (CDN)
- **AI**: Google Gemini (기본) / OpenAI GPT / Ollama (EXAONE 로컬)
- **TTS**: Gemini TTS / OpenAI TTS / Google Cloud TTS / MzTTS
- **STT**: Local (Vosk) / Google Cloud / OpenAI Whisper
- **발음 평가**: SpeechPro API (음소 단위 분석)
- **영상 학습**: 로컬 MP4 기반 OnuiTube, Gemini 썸네일, Gemini/OpenAI TTS

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
GEMINI_MODEL=gemini-2.5-pro

# OpenAI (DALL-E, Whisper 사용 시)
OPENAI_API_KEY=your_openai_api_key
DALLE_MODEL=gpt-image-1.5

# Ollama (로컬 LLM 사용 시)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=exaone3.5:7.8b

# TTS 백엔드: gemini | openai | google | mztts
TTS_BACKEND=gemini
GEMINI_TTS_MODEL=gemini-2.5-flash-preview-tts
OPENAI_TTS_MODEL=gpt-4o-mini-tts
OPENAI_TTS_VOICE=marin

# STT 백엔드: openai | google | vosk | local
STT_BACKEND=local
VOSK_MODEL_PATH=/path/to/vosk-model-small-ko-0.22
```

### 3. 서버 실행

```bash
# 개발 서버 (hot reload, 포트 9002)
source .venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port 9002 --reload
```

브라우저에서 `http://localhost:9002` 접속

---

## 프로덕션 배포

### 서비스 URL

| 환경 | URL |
|---|---|
| 메인 서비스 | `https://opportunity.ai.kr` |
| 보조 (리다이렉트) | `https://onuiai.kr` |

### PM2로 서비스 관리

```bash
./start-service.sh    # onui-ai 시작 (PM2)
./stop-service.sh     # onui-ai 중지

pm2 status            # 프로세스 상태 확인
pm2 logs onui-ai      # 애플리케이션 로그
pm2 restart onui-ai   # 재시작
```

PM2 설정: `ecosystem.config.js` / 로그: `logs/pm2-out.log`, `logs/pm2-error.log`

### ngrok는 수동으로만 사용

운영 공개는 `opportunity.ai.kr` / `onuiai.kr` 도메인을 사용합니다. `ngrok`는 외부 데모나 임시 공유가 필요할 때만 수동으로 실행합니다.

```bash
./scripts/run-ngrok.sh
```

### Nginx + SSL 설정 (opportunity.ai.kr)

```
opportunity.ai.kr (DNS A → 공인 IP)
  └→ nginx (80/443, SSL termination, Let's Encrypt)
       └→ uvicorn (127.0.0.1:9002)
```

**1. DNS 설정** — 도메인 등록 업체에서 A 레코드 등록:
```
A  @    <서버 공인 IP>
A  www  <서버 공인 IP>
```

**2. 설치 스크립트 실행** (DNS 전파 후):
```bash
# 새로운 메인 도메인 설정 시
sudo bash scripts/setup-domain-onui-ai-kr.sh

# 기존 도메인(onuiai.kr) 재설정 시
sudo bash scripts/setup-domain.sh
```

스크립트가 자동 처리하는 항목:
- UFW 방화벽 80/443 포트 오픈
- nginx + certbot 설치
- nginx 리버스 프록시 설정 (WebSocket `/ws/`, static 파일 직접 서빙, 50MB 업로드)
- Let's Encrypt SSL 인증서 발급 및 자동 갱신
- 정적 파일 디렉터리 ACL 권한 설정

nginx 설정 파일: `nginx-opportunity.ai.kr.conf` (또는 `nginx-onuiai.kr.conf`)

**SSL 인증서 수동 갱신:**
```bash
sudo certbot renew --dry-run   # 갱신 테스트
sudo certbot renew             # 실제 갱신
```

---

## 환경 변수 전체 목록

| 변수 | 설명 | 기본값 |
|---|---|---|
| `MODEL_BACKEND` | AI 백엔드: `gemini` / `openai` / `ollama` | `gemini` |
| `GEMINI_API_KEY` | Gemini API 키 | — |
| `GEMINI_MODEL` | Gemini 모델명 | `gemini-2.5-pro` |
| `GEMINI_IMAGE_MODEL` | Gemini 이미지 생성 모델 | `gemini-2.5-flash-img` |
| `GEMINI_IMAGE_TIMEOUT` | Gemini 이미지 REST 호출 timeout(초) | `60` |
| `GEMINI_IMAGE_USE_SDK` | Gemini 이미지 생성 SDK 사용 여부 (`1`이면 SDK, 기본은 REST) | 비활성 |
| `OPENAI_API_KEY` | OpenAI API 키 | — |
| `OPENAI_MODEL` | OpenAI 텍스트 모델명 | `gpt-4.1-nano` |
| `DALLE_MODEL` | DALL-E 이미지 모델 | `gpt-image-1.5` |
| `OLLAMA_URL` | Ollama 서버 주소 | `http://localhost:11434` |
| `OLLAMA_MODEL` | Ollama 모델명 | `exaone3.5:7.8b` |
| `TTS_BACKEND` | TTS 백엔드: `gemini` / `openai` / `google` / `mztts` | `gemini` |
| `GEMINI_TTS_MODEL` | Gemini TTS 모델 | `gemini-2.5-flash-preview-tts` |
| `OPENAI_TTS_MODEL` | OpenAI TTS 모델 (`gpt-4o-mini-tts`, `tts-1`, `tts-1-hd`) | `tts-1` |
| `OPENAI_TTS_VOICE` | OpenAI TTS 음성 (`marin`, `coral`, `shimmer`, `nova`, `sage`, etc.) | `alloy` |
| `STT_BACKEND` | STT 백엔드: `openai` / `google` / `vosk` / `local` | `local` |
| `VOSK_MODEL_PATH` | Vosk 모델 디렉터리 경로 | — |
| `ONUI_TMP_DIR` | 오디오 변환용 임시 디렉터리 | 시스템 기본 tmp |
| `ROMANIZE_MODE` | 로마자 표기: `force` / `prefer` | `force` |
| `KRDICT_API_KEY` | 국립국어원 한국어기초사전 API 키 | — |
| `APP_ENV` | 실행 환경 (`production`이면 `SECRET_KEY` 필수) | `development` |
| `ALLOWED_ORIGINS` | CORS 허용 origin CSV 목록 | 로컬 9002 + 운영 도메인 |
| `SESSION_COOKIE_SECURE` | 세션 쿠키 Secure 플래그 (`1`/`true`이면 활성) | `0` |
| `SECRET_KEY` | 세션 서명 키 | production 필수 |
| `MZTTS_API_URL` | MzTTS 서버 주소 (mztts 백엔드 사용 시) | — |
| `FLUENCYPRO_WS_URL` | FluencyPro WebSocket URL | — |
| `CLARITY_PROJECT_ID` | MS Clarity 애널리틱스 프로젝트 ID | — |
| `NGROK_AUTHTOKEN` | ngrok 인증 토큰 (임시 공유 시) | — |
| `NGROK_DOMAIN` | ngrok 고정 도메인 | — |

---

## 프로젝트 구조

```
onui-ai/
├── main.py                  # FastAPI 진입점: 미들웨어, DB 초기화, 라우터 마운트
├── requirements.txt
│
├── backend/
│   ├── routes/              # 기능별 라우터 모듈
│   │   ├── pages.py         # 전체 HTML 페이지 GET 라우트
│   │   ├── auth.py          # 회원가입/로그인/로그아웃, Google OAuth
│   │   ├── user.py          # 마이페이지, 비밀번호 변경, 크레딧
│   │   ├── ai_services.py   # AI 음성 통화(WebSocket), 콘텐츠 생성, 이미지 생성
│   │   ├── content.py       # 표현, 교재, 출석, 대시보드 통계
│   │   ├── media.py         # OnuiTube 영상·자막·어휘, 영상 진도
│   │   ├── stt.py           # STT 프록시 (Whisper·Google·Vosk)
│   │   ├── tts.py           # TTS API
│   │   ├── speechpro.py     # 발음 평가 (SpeechPro)
│   │   ├── roleplay.py      # AI 역할극
│   │   ├── learning_progress.py  # 학습 진도 추적
│   │   ├── lms.py           # LMS (성적·출결·학습시간)
│   │   ├── admin.py         # 관리자 대시보드
│   │   └── deps.py          # 공통 의존성 re-export
│   ├── services/            # 외부 API 연동 서비스
│   │   ├── speechpro_service.py
│   │   ├── fluencypro_service.py
│   │   ├── dalle_service.py
│   │   ├── krdict_service.py
│   │   ├── learning_progress_service.py
│   │   ├── onui_tube_catalog.py
│   │   └── analytics_service.py
│   └── utils.py             # 인증·RAG·오디오·한국어 공통 유틸리티
│
├── templates/               # Jinja2 HTML 템플릿
│   ├── base.html            # 공통 레이아웃 (네비, i18n)
│   ├── components/          # 재사용 컴포넌트
│   └── *.html               # 페이지별 템플릿
│
├── static/
│   ├── js/                  # 페이지별 JavaScript (kebab-case)
│   ├── css/                 # 페이지별 CSS (kebab-case)
│   ├── images/tube/         # OnuiTube 썸네일 이미지
│   └── video/               # OnuiTube 로컬 MP4 영상
│
├── data/
│   ├── users.db             # SQLite 사용자 DB
│   ├── locales/             # i18n 번역 파일 (ko/en/ja/zh/vi/ne/id/mn/lo)
│   ├── vocabulary.json      # 72개 어휘 (A1-B2)
│   ├── sentences.json       # 35개 연습 문장
│   ├── voice-call.json      # AI 음성 통화 시나리오
│   ├── roleplay-scenarios.json
│   ├── onui-tube.json       # OnuiTube 영상 메타데이터
│   ├── onui-tube-transcripts.json  # OnuiTube 자막·단어 데이터
│   └── tts_cache/           # TTS 오디오 캐시
│
├── scripts/                 # 일회성 데이터 관리 스크립트
└── docs/                    # 설계 문서
```

---

## OnuiTube 콘텐츠 관리

OnuiTube는 `/video-learning`에서 제공되는 세로형 숏폼 영상 학습 기능입니다.

- 현재 카탈로그: **50개 영상**
- 레벨 분포: **Lv.1 18개 / Lv.2 18개 / Lv.3 14개**
- 신규 30개는 **Lv.1/Lv.2/Lv.3 각 10개**로 구성
- 영상 파일: `static/video/*.mp4`
- 썸네일: `static/images/tube/*.png` 또는 `.jpg`
- 메타데이터: `data/onui-tube.json`
- 자막·단어 데이터: `data/onui-tube-transcripts.json`

> 생성된 MP4와 썸네일 PNG는 Git에 커밋하지 않습니다. 운영 서버에는 생성 결과물을 직접 배포하거나, 별도 object storage(S3/GCS/R2 등)에 업로드한 뒤 카탈로그 URL을 맞춥니다. Git에는 생성 스크립트, 메타데이터, 자막 데이터만 보관합니다.

### 썸네일 생성

```bash
source .venv/bin/activate
GEMINI_IMAGE_TIMEOUT=60 python scripts/generate_tube_images.py --ids <video_id...>
```

기본은 Gemini REST 경로를 사용합니다. SDK를 강제로 쓰려면 `GEMINI_IMAGE_USE_SDK=1`을 설정합니다.

### 영상 생성

```bash
source .venv/bin/activate
python scripts/generate_tube_videos.py \
  --ids <video_id...> \
  --tts-backend openai \
  --tts-model gpt-4o-mini-tts \
  --tts-voice marin \
  --tts-instructions "Speak in Korean with a bright, warm, cute, youthful feminine voice. Keep pronunciation very clear for Korean learners. Read the Korean text exactly once without adding any words." \
  --retime-from-audio \
  --sentence-gap 0.75 \
  --tail-padding 0.25 \
  --cache-version <version>
```

기존 Leda 톤이 필요한 경우 Gemini TTS를 사용할 수 있습니다. 단, Gemini TTS는 일일 quota 제한이 있으므로 대량 생성 시 실패한 ID만 재실행합니다.

```bash
python scripts/generate_tube_videos.py \
  --ids <video_id...> \
  --tts-backend gemini \
  --tts-voice Leda \
  --retime-from-audio
```

### 검증

```bash
python3 scripts/audit_onuitube_catalog.py
python3 -m json.tool data/onui-tube.json
python3 -m json.tool data/onui-tube-transcripts.json
node --check static/js/video-learning.js
```

정상 상태 예:

```text
OnuiTube catalog audit
total=50 ready=50 replacement_required=0 transcript_missing=0
```

---

## 개발 원칙 및 컨벤션

- **라우터**: 새 기능은 `backend/routes/`에 라우터로 추가하고 `main.py`에서 `include_router()`로 마운트합니다. 페이지 GET은 `pages.py`, API는 목적에 맞는 라우터 파일로 분리합니다.
- **서비스**: 외부 API 연동 로직은 `backend/services/`에 별도 파일로 분리합니다.
- **유틸리티**: 공통 함수는 `backend/utils.py`에 추가하고 라우터에서는 `deps.py`를 통해 import합니다.
- **i18n (하이브리드)**:
  - 정적 로케일: `ko` / `en` / `ja` / `zh` / `vi` / `ne` → `data/locales/*.json` + `data-i18n`
  - Google 웹사이트 번역: `id` / `mn` / `lo` → 영어 UI 렌더 후 숨겨진 Google Translate Element
  - 새 정적 UI 문자열은 `ko/en/ja/zh/vi/ne` 파일에 모두 추가
  - 학습용 한국어 텍스트는 `notranslate` 클래스로 보호 (발음 문장, 가사, 자막, 채팅 등)
- **DB 스키마**: `main.py`의 `_ensure_*` 헬퍼로 컬럼·테이블을 추가합니다. 마이그레이션 프레임워크는 사용하지 않습니다.
- **정적 자산**: JS/CSS 파일명은 kebab-case로 대응 템플릿과 동일한 이름을 사용합니다.
- **커밋 스타일**: `feat:`, `fix:`, `refactor:`, `chore:` 접두사 + 선택적 scope (예: `fix(ui): ...`).

---

## 개발자

김영훈 (Kim Young-hoon) — Mediazen
