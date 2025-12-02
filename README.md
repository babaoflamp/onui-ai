# 오누이 한국어 (Onui Korean) 🌸

한국어 학습을 위한 AI 기반 웹 애플리케이션

## 프로젝트 개요

오누이 한국어는 한국어 학습자를 위한 종합 학습 플랫폼입니다. AI 기술과 인터랙티브한 학습 게임을 통해 효과적인 한국어 학습 경험을 제공합니다.

## 주요 기능

### 1. 🎓 AI 학습 도구
- **맞춤형 교재 생성**: 주제와 레벨에 맞는 대화문과 단어장 자동 생성
- **AI 발음 교정**: 음성 인식을 통한 실시간 발음 평가
- **유창성 테스트**: 작문 능력 평가 및 피드백

### 2. 🎮 학습 게임
- **단어 퍼즐**: 드래그 앤 드롭으로 올바른 어순 맞추기
- **오늘의 표현**: 매일 바뀌는 한국어 표현 학습
- **단어 꽃밭**: CEFR 레벨별 단어 학습 (이모지 기반 시각화)

### 3. 🎤 발음 연습 (NEW!)
- **ELSA Speak 스타일** 2단계 학습 인터페이스
- **Step 1 - 듣기**: TTS로 네이티브 발음 듣기, 음소 분해, 발음 팁
- **Step 2 - 말하기**: 녹음 및 AI 발음 평가, 오누이 캐릭터 (👦👧)
- **20개 필수 표현**: A1~A2 레벨 인사말 및 일상 표현
- **실시간 검색**: 한글, 로마자, 의미로 단어 검색
- **레벨 필터링**: 전체, A1, A2 레벨 선택

### 4. 🤖 AI 통합
- **Ollama 지원**: 로컬 LLM (EXAONE 모델) 사용
- **Web Speech API**: 브라우저 기반 TTS/STT
- **VOSK**: 오프라인 음성 인식 (선택)

## 기술 스택

- **Backend**: FastAPI (Python)
- **Frontend**: Jinja2 Templates, Tailwind CSS
- **AI/ML**: Ollama (EXAONE), Web Speech API, VOSK
- **Audio**: MediaRecorder API, ffmpeg

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

# VOSK 음성 인식 (선택)
export LOCAL_STT=vosk
export VOSK_MODEL_PATH=/path/to/vosk-model

# OpenAI (선택, 기본적으로 비활성화)
# export OPENAI_API_KEY=your-api-key
```

### 3. 서버 실행

```bash
# 개발 서버 (자동 재로딩)
uvicorn main:app --host 0.0.0.0 --port 9000 --reload

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

브라우저에서 http://localhost:9000 접속

## 프로젝트 구조

```
onui-ai/
├── main.py                 # FastAPI 메인 앱
├── requirements.txt        # Python 패키지
├── templates/              # Jinja2 템플릿
│   ├── base.html          # 기본 레이아웃
│   ├── index.html         # 홈페이지
│   ├── learning.html      # AI 학습 도구
│   ├── word-puzzle.html   # 단어 퍼즐
│   ├── daily-expression.html  # 오늘의 표현
│   ├── vocab-garden.html  # 단어 꽃밭
│   └── pronunciation-practice.html  # 발음 연습 (NEW!)
├── static/
│   ├── css/               # 스타일시트
│   │   ├── word-puzzle.css
│   │   ├── daily-expression.css
│   │   ├── vocab-garden.css
│   │   └── pronunciation-practice.css  # (NEW!)
│   └── js/                # JavaScript
│       ├── word-puzzle.js
│       ├── daily-expression.js
│       ├── vocab-garden.js
│       └── pronunciation-practice.js  # (NEW!)
└── data/                  # JSON 데이터
    ├── sentences.json     # 어순 연습 문장
    ├── expressions.json   # 오늘의 표현
    ├── vocabulary.json    # 단어 꽃밭 단어
    └── pronunciation-words.json  # 발음 연습 단어 (NEW!)
```

## API 엔드포인트

### 페이지 라우트
- `GET /` - 홈페이지
- `GET /learning` - AI 학습 도구
- `GET /word-puzzle` - 단어 퍼즐
- `GET /daily-expression` - 오늘의 표현
- `GET /vocab-garden` - 단어 꽃밭
- `GET /pronunciation-practice` - 발음 연습 (NEW!)

### API 엔드포인트
- `POST /api/generate-content` - AI 교재 생성
- `POST /api/pronunciation-check` - 발음 평가
- `POST /api/fluency-check` - 유창성 평가
- `GET /api/puzzle/sentences` - 퍼즐 문장 목록
- `GET /api/expressions` - 표현 목록
- `GET /api/expressions/today` - 오늘의 표현
- `GET /api/vocabulary` - 단어 목록
- `GET /api/vocabulary/{word_id}` - 특정 단어
- `GET /api/pronunciation-words` - 발음 연습 단어 목록 (NEW!)
- `GET /api/pronunciation-words/{word_id}` - 특정 발음 단어 (NEW!)
- `GET /api/ollama/models` - Ollama 모델 목록
- `POST /api/ollama/test` - Ollama 모델 테스트

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

## 최근 업데이트 (2025-12-02)

### ✨ 발음 연습 페이지 추가
- ELSA Speak 스타일의 2단계 학습 인터페이스
- Web Speech API 기반 TTS (브라우저 음성 합성)
- MediaRecorder API 기반 녹음 및 AI 발음 평가
- 20개 한국어 필수 표현 (인사말, 일상 표현)
- 오누이 캐릭터 (👦👧) 적용
- 실시간 검색 및 레벨 필터링 (A1/A2)
- 음소 분해 시각화 및 발음 팁 제공

### 🎨 UI 개선
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
