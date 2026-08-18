# Onui Korean GCP 이관 계획

## 요약

현재 `FastAPI + Uvicorn + SQLite + 로컬 파일 저장 + PM2/Nginx` 구조를 다음 구성으로 전환한다.

- 실행: Cloud Run
- 리전: 서울 `asia-northeast3`
- DB: Cloud SQL for PostgreSQL
- 파일/미디어: Cloud Storage
- 비밀정보: Secret Manager
- 이미지 저장소: Artifact Registry
- 배포: Cloud Build 트리거
- 로그/모니터링: Cloud Logging·Monitoring
- AI·SpeechPro·FluencyPro: 기존 외부 API 유지
- 운영 도메인: `opportunity.ai.kr`
- 전환 방식: 스테이징 검증 후 짧은 점검 시간 동안 DNS 전환

현재의 GCP 문서는 Cloud Run 배포 명령 중심의 초안이며, SQLite와 로컬 파일 저장 문제를 해결한 뒤 실제 운영 계획으로 보완한다.

## 주요 변경 사항

### 1. 컨테이너화 및 Cloud Run 전환

- `Dockerfile` 추가
  - Python 버전 고정
  - `ffmpeg`, `libsndfile` 설치
  - 애플리케이션·템플릿·정적 리소스 포함
- Cloud Run이 제공하는 `PORT` 환경변수를 사용하도록 실행 명령 수정
- 운영 환경에서는 `reload=True` 제거
- `/healthz` 또는 `/readyz` 헬스체크 추가
- 파일 로그를 주 저장소로 사용하지 않고 표준 출력으로 기록
- WebSocket 음성 통화를 고려해 Cloud Run 요청 타임아웃과 인스턴스 수를 별도 설정
- 초기 운영값:
  - 최소 인스턴스: 1
  - 최대 인스턴스: 3
  - 메모리: 2 GiB
  - CPU: 2
  - 동시성: 낮은 값부터 부하 테스트 후 확정

### 2. SQLite에서 Cloud SQL PostgreSQL로 전환

현재 여러 라우터가 `sqlite3.connect()`와 SQLite 전용 SQL을 직접 사용하므로 DB 전환을 최우선 선행 작업으로 한다.

- 공통 DB 접근 계층 도입
  - 연결 풀
  - 트랜잭션 관리
  - 행(row) 변환
  - 파라미터 바인딩
- 기존 라우터의 직접적인 `sqlite3` 의존성 제거
- SQLite 전용 구문 교체
  - `INSERT OR IGNORE`
  - `PRAGMA`
  - SQLite의 `AUTOINCREMENT`
  - `BEGIN IMMEDIATE`
  - SQLite 행 객체 의존성
- `initialize_database()`를 PostgreSQL 스키마 초기화 방식으로 재구성
- 기존 프로젝트 방침에 맞춰 Alembic을 도입하지 않고, 명시적인 버전별 SQL/마이그레이션 모듈을 유지
- 크레딧 차감·학습 진도·발음 기록 등 동시성에 민감한 작업은 PostgreSQL 트랜잭션으로 재검증
- 기존 `data/users.db`에서 PostgreSQL로 이전하는 일회성 마이그레이션 스크립트 작성
  - 테이블별 데이터 이전
  - 사용자 ID 및 외래 참조 보존
  - 날짜·JSON·Boolean 타입 변환
  - 행 수와 주요 통계 비교 리포트 생성

### 3. Cloud Storage 기반 파일 저장

Cloud Run의 로컬 디스크는 임시 저장소로만 사용한다.

버킷 구조:

```text
gs://<project>-onui/
├── uploads/audio/
├── uploads/images/
├── tts-cache/
├── static/videos/
├── content/
└── backups/
```

변경 대상:

- 발음 녹음 파일을 Cloud Storage에 저장
- DALL·E/Gemini 생성 이미지를 Cloud Storage에 저장
- TTS 캐시는 로컬 캐시를 1차로 사용하되 장기 캐시는 Cloud Storage에 저장
- OnuiTube 동영상과 PDF/HTML 강의 자료를 Cloud Storage로 이전
- 관리자 편집 대상 JSON을 GCS의 `content/` 아래에 저장
- 관리자 수정은 임시 로컬 파일에 쓰지 않고 GCS 객체의 읽기-수정-쓰기 방식으로 처리
- 업로드 파일명은 사용자 입력값을 그대로 사용하지 않고 사용자 ID·UUID 기반으로 생성
- MIME type, 확장자, 파일 크기 제한을 서버에서 검증
- 버킷은 비공개로 유지하고, 애플리케이션이 인증된 요청에 대해서만 파일을 제공하거나 짧은 수명의 Signed URL을 발급
- TTS 캐시·오디오 업로드에는 보존 기간 정책을 적용

정적 CSS/JS와 템플릿은 우선 컨테이너에 포함하고, 변경 빈도가 높은 동영상과 생성 파일만 GCS로 분리한다.

### 4. 인증·세션·환경설정

- 현재 HMAC 서명 세션 토큰 형식은 유지하되 `SECRET_KEY`를 Secret Manager에서 주입
- `active_sessions` 인메모리 캐시에 의존하지 않도록 수정
- 로그아웃·세션 폐기 정책이 필요한 경우 PostgreSQL 세션/폐기 토큰 테이블을 추가
- `SESSION_COOKIE_SECURE=1`, HTTPS 전용 쿠키, 적절한 `SameSite` 설정 적용
- Google OAuth Redirect URI를 GCP 운영 도메인으로 변경
- `ALLOWED_ORIGINS`에서 실제 운영 도메인만 허용하도록 정리
- API 키와 비밀값은 환경변수 파일이나 서비스 계정 JSON으로 배포하지 않음
- Cloud Run 서비스 계정에 최소 권한만 부여:
  - Cloud SQL Client
  - 지정 버킷 Object Viewer/Creator
  - 필요한 Secret Manager Secret Accessor

Google Cloud SDK의 Application Default Credentials를 사용해 `GOOGLE_APPLICATION_CREDENTIALS` JSON 파일 배포를 피한다.

### 5. 외부 AI·음성 서비스

1차 전환에서는 기존 외부 API를 유지한다.

- Gemini API
- OpenAI API
- SpeechPro API
- FluencyPro WebSocket
- MzTTS가 사용되는 경우 기존 외부 URL 유지

환경별 Secret Manager 항목:

```text
SECRET_KEY
GEMINI_API_KEY
OPENAI_API_KEY
GOOGLE_CLIENT_SECRET
KRDICT_API_KEY
SPEECHPRO_TARGET
FLUENCYPRO_WS_URL
MZTTS_API_URL
```

Cloud Run에서 외부 WebSocket 접근이 가능한지 스테이징에서 확인하고, 외부 서비스가 IP allowlist를 요구하면 Cloud NAT 또는 고정 egress 구성을 별도 검토한다.

Vertex AI 전환과 Ollama GPU 운영은 1차 이관 범위에서 제외하고 후속 최적화 과제로 둔다.

## 실행 단계

### 1단계: 사전 조사와 기준선 확보

- 현재 운영 서버에서 SQLite DB 백업
- `uploads/`, 동영상, PDF/HTML, TTS 캐시 목록과 용량 산출
- 운영 사용자 수·주요 테이블 행 수 기록
- 현재 도메인 DNS와 Google OAuth 설정 확인
- 기존 기능별 smoke test 기준선 확보
- 로컬 파일 중 실제로 운영에 필요한 파일과 폐기 가능한 캐시 분리

### 2단계: 애플리케이션 영속성 분리

- DB 접근 계층 및 PostgreSQL 스키마 구현
- GCS 저장소 어댑터 구현
- 세션의 인메모리 의존성 제거
- 관리자 JSON 편집 영속화
- `/healthz` 추가
- 포트·로그·운영 실행 방식 수정
- 모든 런타임 경로를 상대 경로 또는 설정값 기반으로 정리

### 3단계: 데이터 및 파일 마이그레이션

- Cloud SQL PostgreSQL 생성
- Cloud Storage 버킷 생성
- DB 마이그레이션 스크립트 실행
- 기존 이미지·오디오·동영상·강의 파일 업로드
- 체크섬, 파일 수, 파일 크기 비교
- 관리자 콘텐츠 JSON을 GCS에 등록
- 마이그레이션 결과를 별도 검증 리포트로 저장

### 4단계: 이미지 빌드와 스테이징 배포

- Artifact Registry 저장소 생성
- Cloud Build로 이미지 빌드·푸시
- Secret Manager 연결
- Cloud Run 스테이징 서비스 배포
- Cloud SQL 연결
- GCS 권한 및 파일 접근 확인
- WebSocket, ffmpeg, 외부 API 연결 확인

### 5단계: 기능·부하 검증

필수 검증 범위:

- 회원가입·로그인·로그아웃
- Google OAuth 로그인
- 세션 만료와 다중 인스턴스 요청
- 대시보드와 학습 진도 저장
- 크레딧 동시 차감
- AI 역할극·콘텐츠 생성
- TTS·STT
- 발음 녹음 업로드 및 SpeechPro 평가
- AI 음성 통화 WebSocket
- OnuiTube 영상·자막·단어 저장
- 관리자 콘텐츠 수정
- 이미지·오디오·영상 파일 재시작 후 접근
- Cloud Run 재배포 후 DB와 파일 보존
- 2개 이상 인스턴스에서 동일 사용자 세션 유지

### 6단계: 운영 전환

- Cloud Run 운영 서비스에 새 리비전 배포
- 임시 GCP URL로 최종 smoke test
- 기존 서버를 읽기 전용 또는 점검 모드로 전환
- 최종 SQLite 덤프와 파일 동기화
- PostgreSQL 최종 데이터 반영
- 도메인 DNS를 Cloud Run으로 전환
- HTTPS, OAuth, WebSocket을 운영 도메인에서 확인
- 장애 시 기존 서버로 DNS를 되돌릴 수 있도록 유지

## CI/CD 및 운영

- GitHub `main` 브랜치에 Cloud Build 트리거 연결
- 빌드 단계:
  1. 테스트 실행
  2. 컨테이너 이미지 빌드
  3. Artifact Registry 푸시
  4. Cloud Run 새 리비전 배포
- 운영 배포 전 테스트 실패 시 배포 중단
- Cloud Run 로그를 Cloud Logging으로 통합
- 다음 알림 구성:
  - 5xx 비율 증가
  - 인스턴스 시작 실패
  - 요청 지연 증가
  - Cloud SQL 연결 오류
  - 외부 AI API 실패 증가
  - 예산 임계치 초과
- Cloud SQL 자동 백업과 PITR 활성화
- Cloud Storage 버전 관리 또는 별도 백업 적용
- Secret Manager에는 버전별 비밀값을 보관하고 키 교체 절차 마련

## 테스트 및 완료 기준

다음 조건을 모두 만족하면 1차 이관 완료로 판단한다.

- 전체 기존 테스트가 통과한다.
- PostgreSQL에서 스키마 초기화와 데이터 마이그레이션이 재현 가능하다.
- 마이그레이션 전후 사용자 수와 핵심 학습 통계가 일치한다.
- Cloud Run 재시작·스케일아웃 이후 사용자 데이터가 유지된다.
- 업로드·생성 파일이 GCS에서 정상 제공된다.
- 음성 WebSocket이 운영 도메인에서 연결된다.
- Google OAuth Redirect URI가 정상 동작한다.
- 관리자 콘텐츠 수정이 인스턴스 재배포 후에도 유지된다.
- 기존 도메인 전환 후 주요 사용자 흐름이 정상 동작한다.
- 장애 발생 시 기존 서버로 복귀할 수 있다.

## 가정 및 제외 범위

- 1차 대상은 소규모/MVP 운영이다.
- 서울 리전과 `opportunity.ai.kr`을 사용한다.
- 전체 기능을 유지한다.
- AI 모델 자체는 기존 외부 API를 계속 사용한다.
- Ollama, Vertex AI 전환, 멀티테넌트 분리, 대규모 비동기 작업 큐는 후속 단계다.
- Cloud Run의 로컬 디스크는 임시 오디오 변환용으로만 사용한다.
- 기존 서버의 실제 `users.db`와 운영 미디어 원본은 별도 백업을 받아 마이그레이션한다.
