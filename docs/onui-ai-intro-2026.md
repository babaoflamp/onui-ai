# 오누이 한국어 (Onui Korean) — 솔루션 소개

> 내부 팀 미팅 자료 · 2026년 4월

---

## 1. 서비스 개요

**오누이 한국어**는 AI 기술을 기반으로 한 한국어 학습 웹 플랫폼입니다.  
발음 평가, AI 음성 회화, 영상 학습, K-Pop 활동 등 다양한 학습 방식을 하나의 플랫폼에서 제공합니다.

| 항목 | 내용 |
|---|---|
| 서비스 URL | `https://opportunity.ai.kr` (메인), `https://onuiai.kr` (보조) |
| 지원 언어 | 한국어 · English · 日本語 · 中文 (UI 4개 국어) |
| 대상 | 한국어 학습자 (외국인 / 재외동포) |
| 운영 방식 | 자체 서버 (On-premise) + PM2 + nginx |

---

## 2. 핵심 기능

### 2-1. AI 음성 통화 (`/voice-call`)
- Google Gemini Live API 기반 실시간 WebSocket 음성 스트리밍
- 시나리오 선택 (카페, 공항, 병원 등) → AI 튜터와 양방향 음성 대화
- STT(음성→텍스트) + TTS(텍스트→음성) 파이프라인 완비

### 2-2. AI 역할극 (`/roleplay`)
- 역사 인물·상황별 시나리오 선택 (이순신, 세종대왕 등)
- Gemini / OpenAI / Ollama 중 백엔드 선택 가능
- 대화 맥락 유지 + 한국어 교정 피드백 제공

### 2-3. 발음 평가 (`/speechpro-practice`, `/sentence-evaluation`)
- **SpeechPro API** 연동 → 음소 단위 발음 점수 산출
- 예제 문장 낭독 평가 + 자유 문장 입력 평가 두 가지 모드
- 발음 히트맵, 점수 추이 차트로 시각화

### 2-4. OnuiTube — 영상 학습 (`/video-learning`)
- 한국어/영어 이중 자막 동영상 + 자막 클릭 → 즉시 사전 검색
- 영상별 학습 진도 추적

### 2-5. 오누이 비츠 (`/onui-beats`)
- K-Pop 가사 빈칸 채우기 게임
- 음악 재생 + 리얼타임 채점

### 2-6. 오늘의 표현 (`/daily-expression`)
- 매일 새로운 한국어 표현 + 문화 맥락 설명
- AI 생성 예시 대화문 + TTS 발음 듣기

### 2-7. AI 교재 생성 (`/content-generation`)
- 주제·레벨 입력 → 대화문·단어장 자동 생성
- DALL-E / Gemini 이미지 생성 연동

### 2-8. 학습 대시보드 & 리포트 (`/dashboard`, `/learning-progress`)
- 출석 스트릭, 학습 통계, 발음 점수 추이
- AI 문법 코치 (`/onui-grammar`) 통합

---

## 3. 기술 스택

```
┌─────────────────────────────────────────────────────┐
│                   Frontend                          │
│  Jinja2 Templates · Tailwind CSS (CDN) · i18n.js   │
└────────────────────┬────────────────────────────────┘
                     │ HTTP / WebSocket
┌────────────────────▼────────────────────────────────┐
│                   Backend                           │
│  FastAPI (Python 3.12) · Uvicorn · SQLite           │
│  PM2 프로세스 관리 · nginx 리버스 프록시             │
└──────────┬──────────────┬───────────────────────────┘
           │              │
    ┌──────▼──────┐  ┌────▼────────────────────────────┐
    │   AI/LLM    │  │     외부 API / 서비스             │
    │  Gemini     │  │  SpeechPro (발음 평가)            │
    │  OpenAI GPT │  │  DALL-E / Gemini Image           │
    │  Ollama     │  │  Google OAuth / Clarity          │
    └─────────────┘  │  MzTTS (한국어 TTS)              │
                     └─────────────────────────────────┘
```

| 계층 | 기술 |
|---|---|
| Web Framework | FastAPI 0.115+ |
| DB | SQLite (`data/users.db`) |
| AI Backend | Google Gemini 2.5 Flash (기본) / OpenAI GPT / Ollama EXAONE |
| TTS | Gemini TTS / OpenAI TTS / Google Cloud TTS / MzTTS |
| STT | OpenAI Whisper / Google Cloud Speech / Vosk (로컬) |
| 발음 평가 | SpeechPro API (음소 단위) |
| 이미지 생성 | gpt-image-1 (DALL-E) / Gemini Image |
| 인증 | 자체 PBKDF2 세션 + Google OAuth |

---

## 4. 아키텍처 개요

### 4-1. 디렉터리 구조

```
onui-ai/
├── main.py                   # FastAPI 앱 코어 (~7,400줄)
├── backend/
│   ├── routes/               # 기능별 라우터 (roleplay, tts, speechpro ...)
│   ├── services/             # 외부 API 연동 (dalle, speechpro, krdict ...)
│   └── utils.py
├── templates/                # Jinja2 HTML (base.html + 20+ 페이지)
├── static/js|css/            # 기능별 정적 에셋
├── data/
│   ├── locales/              # i18n JSON (ko / en / ja / zh)
│   ├── users.db              # SQLite DB
│   └── *.json                # 콘텐츠 데이터셋
└── docs/                     # 설계·운영 문서
```

### 4-2. 운영 인프라

```
인터넷
  └→ opportunity.ai.kr (DNS A → 서버 공인 IP)
       └→ nginx (443 SSL · Let's Encrypt)
            └→ uvicorn 127.0.0.1:9002
                  ↑
                PM2 (onui-ai 프로세스)
```

- **배포 명령**: `./start-service.sh` (PM2 기동)
- **로그**: `pm2 logs onui-ai` / `logs/pm2-out.log`
- **SSL 갱신**: `sudo certbot renew`

---

## 5. 데이터 & 콘텐츠

| 데이터 | 규모 |
|---|---|
| 연습 문장 | 35개 (`sentences.json`) |
| 어휘 단어 | 72개 A1~B2 (`vocabulary.json`) |
| 전래동화 | 10편 (`folktales.json`) |
| 문화 표현 | 30개 (`cultural-expressions.json`) |
| 발음 평가 문장 | `speechpro-sentences.json` |
| K-Pop 곡 | `onui-beats.json` |
| 역할극 시나리오 | `roleplay-scenarios.json` |
| OnuiTube 영상 | `onui-tube.json` + 자막 |

---

## 6. 다국어 지원 (i18n)

- UI 전체를 클라이언트 사이드 번역으로 처리 (`static/js/i18n.js`)
- `data/locales/{lang}.json` — 4개 국어 JSON 키-값 쌍
- 언어 설정은 `localStorage`에 저장, 페이지 새로고침 없이 전환
- FOUC 방지: 번역 완료 전 화면 숨김 처리

---

## 7. 현재 상태 및 로드맵 (논의 예정)

| 영역 | 현황 |
|---|---|
| 핵심 기능 | ✅ 전체 기능 운영 중 |
| 음성 통화 | ✅ Gemini Live API WebSocket 연동 완료 |
| 발음 평가 | ✅ SpeechPro 연동, 음소 단위 분석 |
| 다국어 UI | ✅ 4개 국어 (ko/en/ja/zh) |
| AI 교재 생성 | ✅ 대화문 + 이미지 자동 생성 |
| LMS (성적·출결) | ✅ 강사/학생 역할 분리, 출결 추적 |
| 테스트 커버리지 | 🔧 `tests/` 디렉터리 구성 중 |
| 모바일 최적화 | 🔧 개선 중 |

---

## 8. 팀 참고 링크

| 항목 | 경로 |
|---|---|
| 상세 개발 가이드 | `CLAUDE.md` |
| 배포 가이드 | `DEPLOYMENT.md` |
| API 테스트 | `http://localhost:9002/api-test` (개발 환경) |
| 관리자 대시보드 | `/admin` |
| PM2 로그 | `logs/pm2-out.log`, `logs/pm2-error.log` |

---

*작성: 오누이 개발팀 · 2026-04-28*
