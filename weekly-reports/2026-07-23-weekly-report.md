# Onui AI 주간보고

## 1. 보고 개요

- 보고일: 2026-07-23
- 대상 저장소: `/home/scottk/Projects/onui-ai`
- 현재 브랜치: `codex/core-stabilization`
- 원격 추적 브랜치: `origin/codex/core-stabilization`
- 기준 범위: 최근 7일 커밋 내역 및 현재 작업 트리 변경 사항
- 확인 결과: 최근 7일 내 신규 커밋은 없으며, 현재 작업 내용은 모두 미커밋 상태

이번 주 작업은 커밋 이력보다는 현재 작업 트리에 누적된 변경 사항을 기준으로 정리했다. 전체적으로는 `main.py`에 집중되어 있던 앱 초기화, 라우터 등록, AI/TTS/SpeechPro 보조 함수, 인증 훅, DB 접근 로직을 분리해 FastAPI 앱 구조를 안정화하는 작업이 가장 큰 축이다. 동시에 다국어 지원 범위를 4개 언어에서 9개 언어로 확장하고, 운영 도메인을 `opportunity.ai.kr` 중심으로 정리했으며, SpeechPro/TTS/콘텐츠 생성 관련 기능도 보강했다.

## 2. 현재 Git 상태

현재 작업 트리에는 tracked 파일 39개 변경과 다수의 untracked 파일이 존재한다. 스테이징된 변경은 없다.

### 수정된 주요 파일

- `main.py`
- `backend/config.py`
- `backend/database.py`
- `backend/routes/ai_services.py`
- `backend/routes/content.py`
- `backend/routes/lms.py`
- `backend/routes/media.py`
- `backend/services/speechpro_service.py`
- `static/js/i18n.js`
- `static/js/daily-expression.js`
- `static/js/speechpro-practice.js`
- `templates/base.html`
- `templates/index.html`
- `templates/daily-expression.html`
- `templates/speechpro-practice.html`
- `templates/video-learning.html`
- `templates/voice-call.html`
- `templates/onui-beats.html`
- `templates/onui-grammar.html`
- `templates/sentence-evaluation.html`
- `templates/ai-roleplay.html`
- `templates/content-generation.html`
- `README.md`
- `AGENTS.md`
- `CLAUDE.md`
- `GEMINI.md`
- `tests/unit/test_auth_security.py`

### 삭제된 파일

- `nginx-onui.ai.kr.conf`
- `scripts/setup-domain-onui-ai-kr.sh`

### 신규 파일 및 디렉터리

- `backend/core/app.py`
- `backend/services/ai_services.py`
- `backend/services/tts_service.py`
- `data/locales/id.json`
- `data/locales/lo.json`
- `data/locales/mn.json`
- `data/locales/ne.json`
- `data/locales/vi.json`
- `design/`
- `docs/OAI_v2.0.backup.pptx`
- `docs/OAI_v2.0.pptx`
- `docs/screenshots/13-onui-grammar.png`
- `nginx-domains.conf`
- `onuiai-structure.md`
- `pytest.ini`
- `scripts/setup-domains.sh`
- `scripts/translate_new_locales.py`
- `tests/unit/test_dalle_service.py`

## 3. 주요 성과 요약

### 3.1 FastAPI 앱 구조 안정화

가장 큰 변경은 `main.py`를 얇은 진입점으로 축소한 것이다. 기존 `main.py`는 약 724줄 규모로 앱 생성, 설정 로딩, 로깅, OAuth 등록, AI 클라이언트 초기화, TTS 헬퍼, SpeechPro 헬퍼, 라우터 등록, DB 초기화 등 많은 책임을 한 파일에서 처리하고 있었다.

이번 작업으로 `main.py`는 다음 역할만 수행하도록 축소되었다.

- `backend.core.app.create_app()` 호출
- 설정 기반 임시 디렉터리 환경 변수 설정
- `initialize_database()` 호출
- `python main.py` 실행 시 uvicorn을 9002 포트로 실행

새로 추가된 `backend/core/app.py`는 앱 팩토리 역할을 담당한다. 이 파일에서 FastAPI 앱을 생성하고, CORS, 정적 파일 마운트, 템플릿 설정, OAuth, AI 클라이언트, 라우터 등록, `app.state` 의존성 주입을 처리한다. 라우터들이 `main.py`에 직접 의존하지 않고 `request.app.state`와 `backend.routes.deps`를 통해 필요한 설정과 서비스를 참조하는 방향으로 정리되었다.

이 구조 변경은 향후 테스트, 유지보수, 라우터 단위 분리, 서버 실행 방식 변경에 유리하다. 특히 `main.py` import 시 부작용을 줄이고, 앱 생성 과정을 함수로 캡슐화했다는 점에서 안정성이 개선되었다.

### 3.2 서비스 계층 분리

기존에 `main.py` 안에 있던 AI 발음 피드백 및 TTS 관련 유틸이 별도 서비스 파일로 분리되었다.

- `backend/services/ai_services.py`
  - 발음 평가 결과를 기반으로 학습자용 AI 피드백을 생성한다.
  - `MODEL_BACKEND`에 따라 Gemini, OpenAI, Ollama 중 하나를 사용한다.
  - 피드백은 영어로 3문장 이내, 학습자에게 실질적인 발음 개선 팁을 주도록 prompt가 구성되어 있다.

- `backend/services/tts_service.py`
  - Gemini TTS 응답에서 audio payload를 추출한다.
  - TTS 캐시 키 생성, 메모리/파일 캐시 조회, 캐시 저장을 담당한다.
  - PCM16 증폭, PCM16 to WAV 변환, ffmpeg 기반 WAV 16k mono 변환을 제공한다.

SpeechPro 관련 사전 계산 문장 로딩 및 런타임 FST 생성 캐시도 `backend/services/speechpro_service.py`로 이동했다. 이를 통해 발음 평가 라우트가 `main.py`의 내부 함수에 기대지 않고 서비스 모듈을 사용할 수 있게 되었다.

### 3.3 데이터베이스 및 라우트 안정화

`backend/database.py`에는 사용자 조회, Google 계정 기반 사용자 생성, 회원가입 저장, 단어/문장 점수 히스토리 조회 헬퍼가 추가되었다.

추가된 주요 함수는 다음과 같다.

- `get_user_by_email()`
- `get_user_by_nickname()`
- `get_user_by_google_id()`
- `create_google_user()`
- `store_user_signup()`
- `get_word_score_history()`
- `get_sentence_score_history()`

또한 여러 라우트에서 필요한 테이블을 요청 처리 시점에 보장하도록 변경했다.

- `backend/routes/ai_services.py`
  - AI 콘텐츠 히스토리 저장 전 `ensure_content_tables()` 호출
- `backend/routes/content.py`
  - 출석, 교재 저장/조회/삭제 API에서 `ensure_content_tables()` 호출
- `backend/routes/lms.py`
  - DB 연결 생성 시 `ensure_lms_tables()` 호출
- `backend/routes/media.py`
  - 저장 단어, 영상 진행률 관련 테이블 생성을 `ensure_media_tables()`로 통합

이 변경은 일부 환경에서 DB 초기화 순서나 누락된 테이블 때문에 API가 실패하는 문제를 줄이기 위한 조치로 볼 수 있다.

### 3.4 다국어 지원 확대

이번 작업의 두 번째 큰 축은 i18n 확장이다. 기존 README 기준 UI 지원 언어는 한국어, 영어, 일본어, 중국어 4개였으나, 현재 변경에서는 9개 언어로 확장되었다.

정적 번역 파일을 사용하는 언어:

- `ko`
- `en`
- `ja`
- `zh`
- `vi`
- `ne`

Google Website Translate를 사용하는 언어:

- `id`
- `mn`
- `lo`

`static/js/i18n.js`에는 다음 기능이 추가되었다.

- 정적 로케일과 Google Translate 기반 언어를 구분
- `SUPPORTED_LANGS`, `STATIC_LOCALES`, `GOOGLE_UI_LANGS` 정의
- 언어별 flag class 매핑
- Google Translate cookie(`googtrans`) 설정 및 삭제
- Google Translate Element 로딩 후 콤보박스 자동 선택
- Google Translate 모드에서 정적 로케일로 이동할 때 DOM 오염을 제거하기 위한 reload 처리
- 브라우저 언어 자동 감지 범위 확대
- 번역 파일 로딩 실패 시 영어 fallback 처리
- 탭 간 `localStorage` 언어 동기화 개선

`templates/base.html`에는 숨김 Google Translate Element가 추가되었고, Google의 기본 배너와 iframe UI를 숨기기 위한 CSS가 포함되었다. 또한 사이드바 언어 선택 영역에 베트남어, 네팔어, 인도네시아어, 몽골어, 라오어 버튼이 추가되었다.

`templates/index.html`의 랜딩 페이지 언어 드롭다운도 9개 언어를 표시하도록 확장되었다.

### 3.5 학습용 한국어 콘텐츠 번역 보호

Google Website Translate를 도입하면서 한국어 학습 콘텐츠가 잘못 번역되는 것을 방지하기 위한 작업도 진행되었다. 다음 영역에 `class="notranslate"`와 `translate="no"`가 추가되었다.

- Daily Expression의 한국어 문장과 로마자 표기
- SpeechPro 문장 목록, 입력 필드, 선택 문장
- Sentence Evaluation 입력 필드와 선택 문장
- OnuiTube 자막 영역
- Onui Beats 가사 영역
- AI Voice Call 채팅 로그
- AI Roleplay 채팅 영역
- AI Grammar Coach 채팅 영역
- Content Generation의 대화 결과 영역

이 작업은 Google Translate가 UI 문구는 번역하되, 학습자가 실제로 익혀야 하는 한국어 문장, 가사, 자막, 채팅 예문은 원문으로 유지하도록 하는 데 목적이 있다.

### 3.6 운영 도메인 정리

운영 도메인이 `onui.ai.kr` 중심에서 `opportunity.ai.kr` 중심으로 정리되었다.

변경된 내용:

- `README.md`
  - 메인 서비스 URL을 `https://opportunity.ai.kr`로 변경
  - `onuiai.kr`은 보조/리다이렉트 도메인으로 정리
  - i18n 설명을 9개 언어 기준으로 업데이트
- `CLAUDE.md`, `GEMINI.md`, `AGENTS.md`
  - 새 구조, 새 도메인, 새 i18n 정책 반영
- `backend/config.py`
  - 기본 허용 origin에 `https://opportunity.ai.kr` 추가
  - `https://onuiai.kr` 기본 origin은 제거됨
- `nginx-onuiai.kr.conf`
  - `onuiai.kr` 요청을 `https://opportunity.ai.kr$request_uri`로 리다이렉트하도록 변경
- `static/robots.txt`
  - sitemap URL을 `https://opportunity.ai.kr/sitemap.xml`로 변경
- `ngrok-config.yml`
  - `opportunity.ai.kr`와 `onui.ai.kr` 터널을 분리
- `scripts/run-ngrok.sh`
  - config에 tunnels가 있으면 `ngrok start --all`로 실행하도록 변경

기존 `nginx-onui.ai.kr.conf`와 `scripts/setup-domain-onui-ai-kr.sh`는 삭제 상태다. 대신 `nginx-domains.conf`, `scripts/setup-domains.sh`가 신규 파일로 추가되어 도메인 설정을 통합하려는 흐름으로 보인다.

### 3.7 Daily Expression 및 TTS 개선

`data/expressions.json`에서 일부 일일 표현이 더 자연스럽거나 TTS/학습용으로 적합한 문장으로 교체되었다.

예시:

- `새해 복 많이 받으세요!` → `새해에도 건강하세요.`
- `이제 곧 봄이 오겠네요.` → `따뜻한 봄이 기다려져요.`
- `벚꽃이 정말 예쁘네요!` → `벚꽃길을 같이 걸어요.`
- `주말에 꽃놀이 하러 갈까요?` → `이번 주말에 봄꽃 보러 갈까요?`
- `오늘따라 하늘이 정말 높아 보여요.` → `가을 하늘이 참 맑아요.`

각 문장에 대응하는 영어 번역, 문화 설명, 로마자 표기도 함께 갱신되었다.

`static/js/daily-expression.js`에서는 IndexedDB 캐시 이름이 `OnuiTTSCacheLedaV2`로 변경되었고, TTS 요청 시 `voice: "Leda"`를 전달하도록 수정되었다. `templates/daily-expression.html`은 JS cache busting query를 `v=leda-tts-2`로 변경했다.

`scripts/regen_tts.py`도 앱 기본 Gemini TTS voice와 캐시 키가 일치하도록 수정되었다. `GEMINI_TTS_VOICE` 환경 변수를 사용하고, 캐시 키에 voice를 포함하며, PCM MIME 타입 비교를 소문자 기준으로 처리한다.

### 3.8 SpeechPro UX 및 서비스 보강

SpeechPro 관련 변경은 두 방향이다.

첫째, 사전 계산 문장 로딩과 런타임 precompute 캐시 로직이 `backend/services/speechpro_service.py`에 추가되었다. 이 로직은 `data/speechpro-sentences.json`과 `data/sp_ko_questions.csv`를 읽어 SpeechPro 문장 목록을 구성하고, 필요 시 `call_speechpro_gtp()`와 `call_speechpro_model()`을 호출해 런타임으로 필요한 FST 정보를 생성한다.

둘째, 프론트엔드 문장 로딩 방식이 변경되었다. `static/js/speechpro-practice.js`는 기존 limit/offset 기반 pagination과 load-more 흐름을 제거하고, `/api/speechpro/sentences`에서 전체 목록을 받아 렌더링하는 방식으로 바뀌었다. 레벨 필터가 있으면 query string으로 `level`만 전달한다.

`templates/speechpro-practice.html`에는 Google Translate 보호를 위해 문장 목록, 입력 필드, 선택 문장 표시 영역에 `notranslate` 설정이 추가되었다.

### 3.9 테스트 보강

`tests/unit/test_auth_security.py`는 app factory 구조에 맞춰 수정되었다.

변경 전에는 `main.py`에서 OAuth 및 cache hook 등록 여부를 문자열로 확인했지만, 이제는 `backend/core/app.py`에서 다음 항목이 등록되는지 확인한다.

- `app.state.get_user_by_google_id`
- `app.state.create_google_user`
- `app.state.clear_user_cache`
- `allow_origins=list(settings.allowed_origins)`

또한 production origin 테스트는 `https://opportunity.ai.kr`, `https://onui.ai.kr`, `https://onuiai.kr` 조합을 기준으로 갱신되었다.

신규 테스트 `tests/unit/test_dalle_service.py`도 추가되었다. 이 테스트는 `enhance_prompt_for_korean_learning()`이 한국어 교재용 이미지 prompt를 적절히 강화하는지 확인한다.

검증하는 내용:

- Korean language textbook content 문맥 포함
- classroom learning materials 포함
- 명확한 일상 장면 지시 포함
- speech bubble, logo 금지 지시 포함
- photorealistic 스타일에서 과도한 `8k resolution`, `cinematic` 표현을 제거

## 4. 문서 업데이트

문서 파일도 현재 구조에 맞춰 대폭 갱신되었다.

### `AGENTS.md`

기존 단순 contributor guide에서 프로젝트별 agent 지침으로 확장되었다. 주요 반영 내용은 다음과 같다.

- 프로젝트 개요
- 실제 디렉터리 구조
- 개발/테스트/PM2 명령
- 설정 및 secret 관리
- `backend/core/app.py` 중심 아키텍처
- i18n hybrid 전략
- 기능 URL map
- PR 작성 기준

### `CLAUDE.md`

AI coding agent용 상세 가이드가 현재 구조에 맞게 정리되었다.

- `main.py`가 얇은 bootstrap이 되었음을 명시
- `backend/core/app.py` 역할 설명
- 환경 변수 목록 확장
- 라우터, 서비스, utils, i18n, data, scripts 구조 정리
- 도메인 및 운영 topology를 `opportunity.ai.kr` 기준으로 업데이트

### `GEMINI.md`

도메인 관련 설명이 `onui.ai.kr`에서 `opportunity.ai.kr` 기준으로 변경되었다. 다만 명령 예시에는 아직 `scripts/setup-domain-onui-ai-kr.sh`가 남아 있어, 삭제된 파일과 불일치가 있는지 확인이 필요하다.

### `README.md`

사용자/운영자 문서도 다음 내용으로 업데이트되었다.

- 9개 UI 언어 지원 설명
- 메인/보조 도메인 변경
- nginx + SSL 설명 업데이트
- i18n hybrid 정책 추가
- 학습용 한국어 텍스트는 `notranslate`로 보호해야 한다는 규칙 추가

## 5. 변경 규모

현재 tracked 변경 기준 diff stat은 다음과 같다.

- 39 files changed
- 1,177 insertions
- 1,261 deletions

가장 큰 변경은 `main.py` 축소다. `main.py`에서 약 700줄 이상의 코드가 제거되고, 그 책임이 `backend/core/app.py`, `backend/services/ai_services.py`, `backend/services/tts_service.py`, `backend/services/speechpro_service.py`, `backend/database.py` 등으로 분산되었다.

프론트엔드에서는 `static/js/i18n.js`와 `templates/base.html` 변경량이 크다. 이는 다국어 지원 범위 확대와 Google Translate 연동 때문이다.

## 6. 리스크 및 확인 필요 사항

### 6.1 Secret 노출 가능성

`ngrok-config.yml`에 authtoken 값이 포함되어 있다. 이 값이 실제 token이라면 커밋 전 반드시 제거하거나 `.env` 기반으로 분리해야 한다.

권장 조치:

- `ngrok-config.yml`에서 실제 token 제거
- `.env.example`에는 placeholder만 유지
- 필요 시 token rotate

### 6.2 런타임 데이터 커밋 여부 확인

`data/landing_intent.json`에 landing signup intent 데이터가 대량 추가되어 있다. 이 파일은 실제 운영/테스트 중 생성된 런타임 데이터일 가능성이 있다.

권장 조치:

- 의도한 seed data인지 확인
- 실제 사용자/테스트 이벤트 로그라면 커밋 대상에서 제외
- 런타임 수집 데이터와 정적 seed data를 분리하는 방안 검토

### 6.3 `__pycache__` untracked 파일

`find` 결과에 `backend/services/__pycache__`, `tests/unit/__pycache__`, `scripts/__pycache__` 파일들이 보였다. 현재 `git status --short` 출력에는 디렉터리 단위로 명확히 보이지 않았지만, 커밋 전 `.gitignore` 적용 여부와 실제 untracked 상태를 다시 확인하는 것이 좋다.

### 6.4 문서와 삭제 파일의 불일치 가능성

`GEMINI.md`에는 여전히 `scripts/setup-domain-onui-ai-kr.sh` 명령 예시가 남아 있는 것으로 확인된다. 하지만 해당 파일은 삭제 상태다.

권장 조치:

- 문서에서 삭제된 스크립트명을 `scripts/setup-domains.sh` 또는 실제 유지할 스크립트명으로 교체
- nginx 설정 파일명도 실제 신규 파일명과 맞추기

### 6.5 `backend/database.py` 역할 비대화

`backend/database.py`에 인증/회원가입 관련 함수가 추가되었다. DB 접근 헬퍼로 볼 수는 있지만, password hashing, HTTPException, email validation까지 포함되어 있어 장기적으로는 `auth_service` 또는 `user_service` 계층으로 이동하는 편이 더 명확할 수 있다.

현재는 구조 안정화를 위한 임시 통합으로 보이며, 다음 refactor에서 책임 분리를 검토할 수 있다.

### 6.6 Google Translate DOM 영향

Google Website Translate는 DOM을 직접 변형한다. 이번 작업에서 cookie 삭제, reload, static locale 전환 처리 등이 추가되었지만, 페이지별 동적 UI와 충돌할 가능성이 있다.

권장 검증:

- `en → id → ko`
- `ko → mn → vi`
- `lo → en`
- 모바일 sidebar collapsed 상태에서 언어 변경
- SpeechPro, OnuiTube, Voice Call에서 학습 콘텐츠가 번역되지 않는지 확인

## 7. 다음 주 권장 작업

### 7.1 커밋 전 정리

- secret 포함 여부 점검
- 런타임 데이터 파일 커밋 여부 결정
- `__pycache__`, 임시 파일, `.continue/` 커밋 제외 확인
- 삭제된 도메인 스크립트와 문서 참조 정합성 확인
- 신규 파일 중 실제 필요한 파일과 작업 산출물을 분류

### 7.2 테스트 실행

다음 명령으로 최소 검증을 권장한다.

```bash
python -m pytest tests/unit
python -m pytest
```

앱 구조가 `main.py`에서 `backend/core/app.py`로 크게 이동했으므로, 단순 unit test 외에 서버 import와 기본 페이지 접근도 확인하는 것이 좋다.

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 9002 --reload
```

확인할 페이지:

- `/`
- `/dashboard`
- `/daily-expression`
- `/video-learning`
- `/speechpro-practice`
- `/sentence-evaluation`
- `/voice-call`
- `/onui-grammar`

### 7.3 i18n 브라우저 검증

신규 i18n은 실제 브라우저 검증이 중요하다.

확인 항목:

- 정적 로케일 `ko/en/ja/zh/vi/ne`가 JSON 기반으로 정상 적용되는지
- Google Translate 기반 `id/mn/lo`에서 UI가 번역되는지
- Google 모드에서 정적 언어로 돌아올 때 DOM이 깨지지 않는지
- `notranslate`가 적용된 학습 콘텐츠가 원문으로 유지되는지
- 랜딩 페이지와 로그인 후 sidebar 언어 선택 상태가 일관적인지

### 7.4 도메인/운영 설정 검증

`opportunity.ai.kr` 전환이 문서, nginx, CORS, robots, ngrok에 걸쳐 반영되었으므로 실제 운영 설정과 맞는지 확인해야 한다.

확인 항목:

- DNS A record
- nginx server_name
- Let's Encrypt 인증서 대상
- `ALLOWED_ORIGINS`
- `SESSION_COOKIE_SECURE`
- `robots.txt` sitemap
- `onuiai.kr` redirect

### 7.5 구조 리팩터 후속 작업

현재 구조 변경은 큰 방향에서 유효하지만, 후속 정리가 필요하다.

- `backend/database.py`에 섞인 인증성 로직 정리
- `backend/core/app.py`의 app.state 등록 항목을 기능별 helper로 나누기
- TTS/Gemini/OpenAI 클라이언트 생성 방식을 서비스 단위로 통일
- 신규 `backend/services/ai_services.py`와 기존 `backend/routes/ai_services.py` 이름 충돌 가능성 검토
- 테스트에서 source 문자열 검사 대신 실제 `create_app()` 결과 검증으로 전환 검토

## 8. 결론

이번 주 작업은 기능 추가보다는 운영 가능한 구조로 코드베이스를 안정화하는 데 초점이 맞춰져 있다. 가장 중요한 변화는 `main.py`의 책임을 줄이고 `backend/core/app.py` 중심의 app factory 구조로 전환한 점이다. 이 변경은 앞으로 라우터, 서비스, 테스트를 분리하고 유지보수하기 위한 기반 작업이다.

동시에 다국어 지원이 크게 확장되었다. 정적 번역과 Google Website Translate를 혼합하는 방식으로 9개 UI 언어를 지원하도록 바뀌었고, 한국어 학습 콘텐츠가 자동 번역되지 않도록 주요 템플릿에 보호 속성이 추가되었다.

운영 측면에서는 `opportunity.ai.kr`를 메인 도메인으로 삼는 방향의 문서와 설정 변경이 진행되었다. 다만 secret 노출 가능성, 런타임 데이터 커밋 여부, 삭제된 스크립트와 문서 참조 불일치 등은 커밋 전에 반드시 정리해야 한다.

현재 상태는 "작업 구현은 상당히 진행되었으나, 커밋 전 정리와 검증이 필요한 단계"로 보는 것이 적절하다.
