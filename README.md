# 오누이 한국어 (Onui Korean) 🌸

한국어 학습을 위한 AI 기반 웹 애플리케이션

## 프로젝트 개요

오누이 한국어는 한국어 학습자를 위한 종합 학습 플랫폼입니다. AI 기술과 인터랙티브한 학습 게임을 통해 효과적인 한국어 학습 경험을 제공합니다.

## 주요 기능

### 1. 🗣️ 발음 학습 (메뉴와 동일)
- **발음 정확도 평가** (`/speechpro-practice`): 녹음 후 AI가 발음 점수와 피드백 제공
- **유창성 평가** (`/fluency-practice`): 말하기 흐름·억양·문법을 실시간 평가
- **단계별 발음 학습** (`/pronunciation-stages`): 단계/레벨별 발음 가이드
- **발음 규칙** (`/pronunciation-rules`): 규칙 이해 ↔ 예제 연습 탭으로 학습

### 2. 🤖 AI 학습 (메뉴와 동일)
- **AI 학습 도구** (`/learning`): 질문/주제 입력 후 AI 피드백
- **맞춤형 교재** (`/content-generation`): 주제·레벨 맞춤 대화문·단어장 생성
- **작문 테스트** (`/fluency-test`): 입력/음성 기반 작문 채점
- **상황별 콘텐츠 생성** (`/media-generation`): 상황별 표현·대화 자동 생성

### 3. 🎲 활동하기 (메뉴와 동일)
- **단어 삭제** (`/word-puzzle`): 드래그 앤 드롭 퍼즐
- **조사 떠다니기** (`/vocab-garden`): 조사/어휘 조합 연습
- **오늘의 표현** (`/daily-expression`): 매일 갱신 표현 학습


## 기술 스택

- **Backend**: FastAPI (Python)
- **Frontend**: Jinja2 Templates, Tailwind CSS
- **AI/ML**: Ollama (EXAONE), MzTTS, VOSK
- **Audio**: MediaRecorder API, MzTTS API, ffmpeg

## 설치 및 실행

### 1. 가상환경 설정

```bash
# 기존 .venv 제거 (선택)
rm -rf .venv

# 새 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate

# pip 및 의존성 설치
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

### 2. 환경 변수 설정

`.env` 파일을 생성하거나 환경 변수를 설정하세요:

```bash
# Ollama 설정 (로컬 LLM)
export MODEL_BACKEND=ollama
export OLLAMA_URL=http://localhost:11434
export OLLAMA_MODEL=exaone3.5:2.4b

# MzTTS 설정 (한국어 TTS)
export MZTTS_API_URL=http://112.220.79.218:56014

# VOSK 음성 인식 (선택)
export LOCAL_STT=vosk
export VOSK_MODEL_PATH=/path/to/vosk-model

# OpenAI (선택, 기본적으로 비활성화)
# export OPENAI_API_KEY=your-api-key
```

### Korean romanizer (발음 표기 개선)

This project can use `korean-romanizer` to produce consistent, accurate Latin-script pronunciations when the model output is absent or unreliable.

Install into the virtualenv:

```bash
source .venv/bin/activate
pip install korean-romanizer
```

Control romanization behavior with the `ROMANIZE_MODE` environment variable:

- `ROMANIZE_MODE=force` (default) — always replace pronunciation fields with the romanizer output for consistent results.
- `ROMANIZE_MODE=prefer` — keep model-provided Latin pronunciations when they look valid; otherwise fall back to the romanizer.

Example:

```bash
export ROMANIZE_MODE=force
```

### 3. 서버 실행

```bash
# 개발 서버 (자동 재로딩)
source .venv/bin/activate && python -m uvicorn main:app --host 0.0.0.0 --port 9000 --reload

# 또는
python main.py

# 백그라운드 실행
python main.py &
```

### 4. 서버 종료

```bash
pkill -f uvicorn
```

## 접속

### 로컬 접속
브라우저에서 http://localhost:9000 접속

### 외부 인터넷 접속 (ngrok)

ngrok을 사용하면 로컬 서버를 외부 인터넷에 공개할 수 있습니다.

#### 1. ngrok 설치

```bash
# 프로젝트 디렉토리에 ngrok 다운로드 및 설치
cd ~/Projects/onui-ai
curl -Lo /tmp/ngrok.tgz https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
tar xzf /tmp/ngrok.tgz -C .
chmod +x ngrok
```

#### 2. ngrok 인증 설정

1. https://ngrok.com/signup 에서 무료 계정 생성
2. 대시보드에서 인증 토큰 확인 (https://dashboard.ngrok.com/get-started/your-authtoken)
3. 토큰 설정:

```bash
./ngrok config add-authtoken <your-auth-token>
```

#### 3. ngrok 터널 시작

```bash
# 백그라운드에서 실행
./ngrok http 9000 --log=stdout &

# 또는 포그라운드에서 실행 (터미널 창 유지 필요)
./ngrok http 9000
```

#### 4. 공개 URL 확인

터미널에서 `https://xxxxxxxx.ngrok-free.app` 형태의 URL을 확인할 수 있습니다.
이 URL을 통해 전 세계 어디서든 접속 가능합니다!

#### 5. ngrok 대시보드

실시간 트래픽 모니터링:
```
http://localhost:4040
```

#### ngrok 중지

```bash
pkill -f ngrok
```

#### 주의사항

- **무료 계정**: ngrok 재시작 시마다 URL이 변경됩니다
- **고정 URL**: 유료 플랜에서 사용 가능
- **보안**: 프로덕션 환경에서는 인증 시스템 추가 권장
- **세션 유지**: 애플리케이션(port 9000)과 ngrok이 모두 실행 중이어야 합니다

## 프로젝트 구조

```
onui-ai/
├── main.py                           # FastAPI 메인 앱
├── requirements.txt                  # Python 패키지
├── README.md                         # 프로젝트 설명서
├── database_schema_learning_progress.sql  # 학습 진도 DB 스키마
│
├── backend/                          # 백엔드 모듈
│   ├── models/                       # DB 모델 (empty - ORM 미사용)
│   ├── services/                     # 비즈니스 로직
│   │   ├── speechpro_service.py      # 발음 평가 서비스 (SpeechPro API)
│   │   └── learning_progress_service.py  # 학습 진도 추적
│   └── utils/                        # 유틸리티 (empty)
│
├── templates/                        # Jinja2 HTML 템플릿
│   ├── base.html                     # 기본 레이아웃 (헤더, 내비게이션)
│   ├── index.html                    # 홈페이지
│   ├── components/
│   │   └── character-popup.html      # 오누이 캐릭터 팝업
│   │
│   ├── 🗣️ 발음 학습
│   │   ├── speechpro-practice.html   # 발음 정확도 평가
│   │   ├── fluency-practice.html     # 유창성 평가
│   │   ├── pronunciation-stages.html # 단계별 발음 학습
│   │   └── pronunciation-rules.html  # 발음 규칙 (NEW!)
│   │
│   ├── 🤖 AI 학습
│   │   ├── learning.html             # AI 학습 도구
│   │   ├── content-generation.html   # 맞춤형 교재 생성
│   │   ├── fluency-test.html         # 작문 테스트
│   │   ├── media-generation.html     # 상황별 콘텐츠 생성
│   │   └── essay-test.html           # 에세이 평가
│   │
│   ├── 🎲 활동하기
│   │   ├── word-puzzle.html          # 단어 삭제 (어순 퍼즐)
│   │   ├── vocab-garden.html         # 조사 떠다니기
│   │   └── daily-expression.html     # 오늘의 표현
│   │
│   ├── 👤 사용자 기능
│   │   ├── login.html                # 로그인
│   │   ├── mypage.html               # 내 프로필
│   │   ├── learning-progress.html    # 학습 진도 (NEW!)
│   │   └── change-password.html      # 비밀번호 변경
│   │
│   ├── 🔧 관리자 페이지
│   │   ├── api-test.html             # API 테스트
│   │   ├── sitemap.html              # 사이트맵
│   │   ├── chatbot.html              # 챗봇
│   │   ├── pronunciation-check.html  # 발음 점검
│   │   ├── pronunciation-correction.html  # 발음 교정
│   │   ├── sentence-evaluation.html  # 문장 평가
│   │   └── custom-materials.html     # 맞춤 교재
│   │
│   └── 🗂️ 기타
│       ├── index_old.html.bak        # 구 홈페이지
│       └── login.html                # 인증 페이지
│
├── static/                           # 정적 파일
│   ├── css/                          # 스타일시트
│   │   ├── pronunciation-practice.css  # 발음 연습 UI
│   │   ├── vocab-garden.css          # 어휘 학습 UI
│   │   ├── word-puzzle.css           # 퍼즐 UI
│   │   └── daily-expression.css      # 표현 학습 UI
│   │
│   ├── js/                           # JavaScript
│   │   ├── pronunciation-practice.js # 발음 연습 로직
│   │   ├── vocab-garden.js           # 어휘 학습 로직
│   │   ├── word-puzzle.js            # 퍼즐 로직
│   │   └── daily-expression.js       # 표현 학습 로직
│   │
│   ├── img/                          # 이미지 (favicon, 캐릭터 등)
│   └── (favicon, manifest 등)
│
├── data/                             # JSON 데이터 파일
│   ├── sentences.json                # 어순 연습 문장
│   ├── expressions.json              # 오늘의 표현
│   ├── vocabulary.json               # 단어 꽃밭 단어
│   ├── pronunciation-words.json      # 발음 연습 단어
│   ├── sp_ko_questions.json          # SpeechPro 질문
│   ├── sp_ko_questions.csv           # SpeechPro 질문 (CSV)
│   ├── speechpro-sentences.json      # SpeechPro 문장
│   ├── landing_intake.json           # 랜딩 페이지 데이터
│   └── users.db                      # SQLite 사용자 DB
│
├── docs/                             # 문서
│   ├── design/                       # 디자인 자료
│   │   ├── character.png             # 오누이 캐릭터
│   │   ├── elsaspeak.png             # ELSA Speak 참고 이미지
│   │   ├── tiger_chatbot.svg         # 챗봇 캐릭터
│   │   └── HTML 디자인 템플릿들
│   ├── api/                          # API 문서
│   └── requirements/                 # 요구사항 명세
│
├── scripts/                          # 유틸리티 스크립트
│   └── test_speechpro_api.py         # SpeechPro API 테스트
│
├── tests/                            # 테스트 코드
│   └── (테스트 파일들)
│
├── tools/                            # 도구/유틸리티
│   └── (헬퍼 도구들)
│
├── .env                              # 환경 변수 (로컬)
├── .env.example                      # 환경 변수 템플릿
├── onui-ai.service                   # Systemd 서비스 파일
├── start-service.sh                  # 서비스 시작 스크립트
├── stop-service.sh                   # 서비스 중지 스크립트
├── ngrok                             # ngrok 바이너리 (외부 공개용)
│
├── 📋 문서 파일
│   ├── CLAUDE.md                     # 개발 노트
│   ├── SPEECHPRO_API_WORKFLOW.md     # SpeechPro 워크플로우
│   ├── SPEECHPRO_IMPLEMENTATION.md   # SpeechPro 구현 가이드
│   ├── CURRICULUM_OPTIMIZATION_REPORT.md  # 커리큘럼 최적화 보고서
│   └── MODEL_COMPARISON_REPORT.md    # 모델 비교 보고서
│
└── 📁 자동 생성 폴더
    ├── __pycache__/                  # Python 캐시
    ├── .git/                         # Git 저장소
    ├── .pytest_cache/                # Pytest 캐시
    ├── htmlcov/                      # 테스트 커버리지 리포트
    ├── logs/                         # 로그 파일
    ├── test_results/                 # 테스트 결과
    └── .venv/                        # Python 가상환경
```

## API 엔드포인트

### 🏠 페이지 라우트 (GET)
| 라우트 | 설명 |
|--------|------|
| `/` | 홈페이지 |
| `/learning` | AI 학습 도구 |
| `/content-generation` | 맞춤형 교재 생성 |
| `/pronunciation-check` | 발음 점검 |
| `/fluency-test` | 작문 테스트 |
| `/custom-materials` | 맞춤 교재 |
| `/essay-test` | 에세이 테스트 |
| `/pronunciation-correction` | 발음 교정 |
| `/word-puzzle` | 단어 삭제 (어순 퍼즐) |
| `/daily-expression` | 오늘의 표현 |
| `/vocab-garden` | 조사 떠다니기 |
| `/pronunciation-practice` | 발음 연습 |
| `/pronunciation-stages` | 단계별 발음 학습 |
| `/pronunciation-rules` | 발음 규칙 |
| `/speechpro-practice` | 발음 정확도 평가 |
| `/fluency-practice` | 유창성 평가 |
| `/api-test` | API 테스트 |
| `/media-generation` | 상황별 콘텐츠 생성 |
| `/sitemap` | 사이트맵 |
| `/login` | 로그인 |
| `/mypage` | 내 프로필 |
| `/learning-progress` | 학습 진도 |
| `/change-password` | 비밀번호 변경 |
| `/chatbot` | 챗봇 |

### 👤 사용자 인증 API
| 메서드 | 라우트 | 설명 |
|--------|--------|------|
| `POST` | `/api/signup` | 회원 가입 |
| `POST` | `/api/login` | 로그인 |
| `POST` | `/api/logout` | 로그아웃 |
| `POST` | `/api/landing-intake` | 랜딩 페이지 입력 저장 |
| `GET` | `/api/user/profile` | 사용자 프로필 조회 |
| `POST` | `/api/user/profile/update` | 프로필 업데이트 |
| `POST` | `/api/user/password/change` | 비밀번호 변경 |
| `POST` | `/api/log/guest-login` | 게스트 로그인 |
| `POST` | `/api/log/activity` | 활동 기록 |

### 🎤 발음 평가 API (SpeechPro)
| 메서드 | 라우트 | 설명 |
|--------|--------|------|
| `POST` | `/api/pronunciation-check` | 단어 발음 평가 |
| `POST` | `/api/speechpro/gtp` | SpeechPro GTP 분석 |
| `POST` | `/api/speechpro/model` | SpeechPro 모델 평가 |
| `POST` | `/api/speechpro/score` | SpeechPro 점수 계산 |
| `POST` | `/api/speechpro/evaluate` | 문장 발음 평가 (전체 워크플로우) |
| `GET` | `/api/speechpro/sentences` | 모든 발음 연습 문장 |
| `GET` | `/api/speechpro/sentences/{sentence_id}` | 특정 발음 문장 |
| `GET` | `/api/speechpro/sentences/level/{level}` | 레벨별 발음 문장 |
| `GET` | `/api/speechpro/config` | SpeechPro 설정 조회 |
| `POST` | `/api/speechpro/config` | SpeechPro 설정 업데이트 |

### 🗣️ 유창성 평가 API (FluencyPro)
| 메서드 | 라우트 | 설명 |
|--------|--------|------|
| `POST` | `/api/fluency-check` | 작문 유창성 평가 |
| `POST` | `/api/fluencypro/analyze` | FluencyPro 상세 분석 |
| `POST` | `/api/fluencypro/combined-feedback` | SpeechPro + FluencyPro 복합 피드백 |
| `GET` | `/api/fluencypro/metrics/{user_id}` | 사용자 유창성 지표 |

### 🎓 AI 콘텐츠 생성 API
| 메서드 | 라우트 | 설명 |
|--------|--------|------|
| `POST` | `/api/generate-content` | AI 교재 생성 (주제/레벨 기반) |
| `POST` | `/api/situational-content` | 상황별 표현/대화 생성 |
| `POST` | `/api/chat/test` | 챗봇 메시지 (Ollama) |
| `POST` | `/api/generate-image` | 이미지 생성 (Image API) |
| `POST` | `/api/generate-music` | 음악 생성 (Music API) |

### 🎲 학습 활동 API
| 메서드 | 라우트 | 설명 |
|--------|--------|------|
| `GET` | `/api/puzzle/sentences` | 어순 퍼즐 문장 목록 |
| `GET` | `/api/puzzle/sentences/{sentence_id}` | 특정 퍼즐 문장 |
| `GET` | `/api/expressions` | 전체 표현 목록 |
| `GET` | `/api/expressions/today` | 오늘의 표현 (매일 갱신) |
| `GET` | `/api/vocabulary` | 단어 꽃밭 단어 목록 |
| `GET` | `/api/vocabulary/{word_id}` | 특정 단어 상세 정보 |
| `GET` | `/api/pronunciation-words` | 발음 연습 단어 목록 |
| `GET` | `/api/pronunciation-words/{word_id}` | 특정 발음 단어 상세 정보 |

### 🎵 TTS (Text-to-Speech) API
| 메서드 | 라우트 | 설명 |
|--------|--------|------|
| `GET` | `/api/tts/info` | MzTTS 서버 정보 조회 |
| `POST` | `/api/tts/generate` | MzTTS로 음성 생성 |

### 🤖 Ollama (로컬 LLM) API
| 메서드 | 라우트 | 설명 |
|--------|--------|------|
| `GET` | `/api/ollama/models` | Ollama 사용 가능 모델 목록 |
| `POST` | `/api/ollama/test` | Ollama 모델 테스트 |

### 📊 학습 진도 API
| 메서드 | 라우트 | 설명 |
|--------|--------|------|
| `POST` | `/api/learning/pronunciation-completed` | 발음 학습 완료 기록 |
| `POST` | `/api/learning/popup-shown` | 캐릭터 팝업 표시 기록 |
| `GET` | `/api/learning/user-stats/{user_id}` | 사용자 학습 통계 |
| `GET` | `/api/learning/today-progress/{user_id}` | 오늘 학습 진도 |
| `POST` | `/api/learning/check-popup/{user_id}` | 팝업 표시 여부 확인 |

## 주요 의존성

- `fastapi` - 웹 프레임워크
- `uvicorn` - ASGI 서버
- `jinja2` - 템플릿 엔진
- `python-multipart` - 파일 업로드
- `requests` - HTTP 클라이언트
- `vosk` - 음성 인식 (선택)
- `pydub` - 오디오 처리 (선택)

## 환경 요구사항

- Python 3.8+
- ffmpeg (오디오 변환용)
- Ollama (로컬 LLM 사용 시)
- VOSK 모델 (오프라인 STT 사용 시)

## 문제 해결

### 1. 가상환경 오류 (bad interpreter)
```bash
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 오디오 변환 실패
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg
```

### 3. Ollama 연결 실패
```bash
# Ollama 서버 실행 확인
curl http://localhost:11434/api/tags

# 모델 다운로드
ollama pull exaone3.5:2.4b
```

### 4. 마이크 권한 오류
- 브라우저 설정에서 마이크 권한 허용
- HTTPS 환경에서만 MediaRecorder API 사용 가능

## 최근 업데이트

### 2025-12-10

#### 🎛 발음 규칙 학습 리뉴얼
- 규칙 이해 / 예제 연습 탭 전환 UI 추가 (기본은 규칙, 클릭으로 연습 전환)
- 연습 카드별 정답 보기/숨기기 토글 개선 (색상/텍스트 동기화)
- 사용자 입력 정답 확인 기능 추가: 입력 → 확인/Enter로 즉시 채점, 피드백 표시
- 연습 카드마다 입력창 자동 생성, 공백/대소문자 무시 비교

### 2025-12-02

#### 🌐 외부 인터넷 배포 (ngrok 통합)
- ngrok 설치 및 설정 가이드 추가
- 로컬 서버를 전 세계에 공개 가능
- HTTPS 자동 지원
- 실시간 트래픽 모니터링 대시보드

#### ✨ MzTTS API 통합
- 전문 한국어 TTS (한나 화자) 통합
- 발음 연습 페이지에 고품질 음성 추가
- 단어 꽃밭에서 단어/문장 음성 재생 기능
- API 테스트 페이지 추가

#### 🎤 발음 연습 페이지
- ELSA Speak 스타일의 2단계 학습 인터페이스
- MzTTS 전문 TTS로 네이티브 발음 듣기
- MediaRecorder API 기반 녹음 및 AI 발음 평가
- 20개 한국어 필수 표현 (인사말, 일상 표현)
- 오누이 캐릭터 (👦👧) 적용
- 실시간 검색 및 레벨 필터링 (A1/A2)
- 음소 분해 시각화 및 발음 팁 제공

#### 🎨 UI 개선
- 단어 꽃밭: 각 단어에 어울리는 이모지 추가
- AI 학습 도구: 친근한 placeholder 텍스트
- 모델 선택: 기본값 exaone3.5:2.4b 설정

## 라이선스

MIT License

## 기여

이슈 및 PR 환영합니다!

## 개발자

김영훈 (Kim Young-hoon)

## 저장소

https://github.com/babaoflamp/onui-ai
