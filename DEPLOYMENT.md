# Google Cloud Run 빠른 배포 가이드

이 프로젝트를 Google Cloud Run에 배포하기 위한 단계별 가이드입니다.

## 🚀 빠른 시작

### 사전 요구사항

1. **Google Cloud SDK 설치**
```bash
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
gcloud init
```

2. **Docker 설치**
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install docker.io

# Docker 권한 설정
sudo usermod -aG docker $USER
```

3. **GCP 프로젝트 생성**
- [Google Cloud Console](https://console.cloud.google.com)에서 새 프로젝트 생성
- 또는 CLI로: `gcloud projects create your-project-id`

---

## 📋 배포 단계

### 방법 1: 자동 배포 스크립트 사용 (추천)

```bash
# 1. 환경 변수 설정
cp .env.production .env.production.local
# .env.production.local 파일을 편집하여 실제 값 입력

# 2. 배포 실행
./deploy.sh your-project-id
```

### 방법 2: 수동 배포

#### 1단계: GCP 프로젝트 설정

```bash
# 프로젝트 ID 설정
export PROJECT_ID="your-project-id"
gcloud config set project $PROJECT_ID

# 필수 API 활성화
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  containerregistry.googleapis.com
```

#### 2단계: Docker 이미지 빌드 및 푸시

```bash
# 이미지 빌드
docker build -t gcr.io/$PROJECT_ID/onui-korean:latest .

# Container Registry에 푸시
docker push gcr.io/$PROJECT_ID/onui-korean:latest
```

#### 3단계: Cloud Run 배포

```bash
gcloud run deploy onui-korean \
  --image gcr.io/$PROJECT_ID/onui-korean:latest \
  --platform managed \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --max-instances 10 \
  --port 8080
```

#### 4단계: 환경 변수 설정 (선택사항)

```bash
gcloud run services update onui-korean \
  --region asia-northeast1 \
  --update-env-vars MODEL_BACKEND=ollama,OLLAMA_URL=your-ollama-url
```

---

## 🔧 환경 변수 설정

[.env.production](.env.production) 파일을 참고하여 다음 환경 변수를 설정하세요:

### 필수 환경 변수
- `MODEL_BACKEND`: AI 모델 백엔드 (ollama, openai, google)
- `SECRET_KEY`: 보안 키 (랜덤 문자열)

### 선택 환경 변수
- `OLLAMA_URL`: Ollama 서버 URL
- `OPENAI_API_KEY`: OpenAI API 키
- `GOOGLE_APPLICATION_CREDENTIALS`: GCP 서비스 계정 JSON 경로

---

## 📊 배포 확인

### 서비스 URL 확인
```bash
gcloud run services describe onui-korean \
  --region asia-northeast1 \
  --format 'value(status.url)'
```

### 로그 확인
```bash
gcloud run services logs read onui-korean \
  --region asia-northeast1 \
  --limit 50
```

### 서비스 상태 확인
```bash
gcloud run services list --platform managed
```

---

## 🔄 CI/CD (자동 배포)

Cloud Build를 사용한 자동 배포가 설정되어 있습니다 ([cloudbuild.yaml](cloudbuild.yaml)).

### GitHub 연동 설정

1. GCP Console > Cloud Build > 트리거
2. "트리거 만들기" 클릭
3. GitHub 저장소 연결
4. 브랜치: `main` 또는 `master`
5. 빌드 구성: `cloudbuild.yaml`
6. 저장

이제 GitHub에 푸시할 때마다 자동으로 배포됩니다!

---

## 💰 비용 최적화

### 리소스 설정 조정

```bash
# 메모리 및 CPU 조정 (비용 절감)
gcloud run services update onui-korean \
  --region asia-northeast1 \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 5
```

### 무료 할당량
- Cloud Run: 월 200만 요청 무료
- Container Registry: 월 0.5GB 무료 저장소
- Cloud Build: 일 120분 무료 빌드 시간

---

## 🐛 문제 해결

### 빌드 실패
```bash
# 로컬에서 Docker 빌드 테스트
docker build -t test-image .
docker run -p 8080:8080 test-image
```

### 배포 실패
```bash
# Cloud Build 로그 확인
gcloud builds list --limit 5
gcloud builds log [BUILD_ID]
```

### 서비스 실행 오류
```bash
# 컨테이너 로그 확인
gcloud run services logs read onui-korean --region asia-northeast1
```

---

## 📚 추가 리소스

- [Cloud Run 문서](https://cloud.google.com/run/docs)
- [Cloud Build 문서](https://cloud.google.com/build/docs)
- [전체 GCP SaaS 배포 가이드](docs/GCP_SAAS_DEPLOYMENT.md)

---

## 🔒 보안 권장사항

1. **.env 파일 보안**: `.env` 파일을 절대 커밋하지 마세요
2. **Secret Manager 사용**: 민감한 정보는 GCP Secret Manager에 저장
3. **IAM 최소 권한**: 필요한 최소한의 권한만 부여
4. **HTTPS 강제**: Cloud Run은 기본적으로 HTTPS 제공

---

## 📞 지원

문제가 있으시면 이슈를 등록해주세요!
