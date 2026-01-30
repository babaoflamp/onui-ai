# Google Cloud Platform (GCP) SaaS 배포 가이드

오누이 한국어를 Google Cloud Platform에서 다중 테넌트 SaaS 형태로 배포하기 위한 완벽 가이드입니다.

---

## 1. 아키텍처 개요

### SaaS 배포 모델

```
┌─────────────────────────────────────────────┐
│         Client Applications                 │
│  (Web, Mobile, LMS Integration)            │
└────────────────┬────────────────────────────┘
                 │ HTTPS
         ┌───────▼────────┐
         │ Cloud Load     │
         │ Balancing      │
         └───────┬────────┘
                 │
    ┌────────────┼────────────┐
    │            │            │
┌───▼───┐   ┌───▼───┐   ┌───▼───┐
│ Cloud │   │ Cloud │   │ Cloud │
│ Run   │   │ Run   │   │ Run   │
│ (App) │   │ (App) │   │ (App) │
└───┬───┘   └───┬───┘   └───┬───┘
    │           │           │
    └───────────┼───────────┘
                │
    ┌───────────┼───────────┐
    │           │           │
┌───▼─────┐ ┌──▼──────┐ ┌──▼────────┐
│ Cloud   │ │ Cloud   │ │ Cloud     │
│ SQL     │ │ Storage │ │ Monitoring
│ (Data)  │ │ (Files) │ │ (Logs)    │
└─────────┘ └─────────┘ └───────────┘
    │
    │ Replication
    ▼
┌─────────────┐
│ Backup      │
│ (Regional)  │
└─────────────┘
```

---

## 2. GCP 프로젝트 초기 설정

### 2.1 프로젝트 생성

```bash
# GCP CLI 설치
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
gcloud init

# 프로젝트 생성
gcloud projects create onui-korean-saas --name "Onui Korean SaaS"

# 프로젝트 설정
gcloud config set project onui-korean-saas
PROJECT_ID=$(gcloud config get-value project)
echo "Project ID: $PROJECT_ID"
```

### 2.2 필수 API 활성화

```bash
gcloud services enable \
  compute.googleapis.com \
  run.googleapis.com \
  sql-component.googleapis.com \
  storage-api.googleapis.com \
  cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com \
  container.googleapis.com \
  servicenetworking.googleapis.com
```

### 2.3 서비스 계정 생성

```bash
# 서비스 계정 생성
gcloud iam service-accounts create onui-app \
  --display-name="Onui App Service Account"

# 필요한 역할 할당
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:onui-app@$PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/cloudsql.client

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:onui-app@$PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/storage.objectViewer

# 키 생성
gcloud iam service-accounts keys create ~/onui-sa-key.json \
  --iam-account=onui-app@$PROJECT_ID.iam.gserviceaccount.com
```

---

## 3. 데이터베이스 설정 (Cloud SQL)

### 3.1 PostgreSQL 인스턴스 생성

```bash
INSTANCE_NAME="onui-korean-db"
REGION="asia-northeast1"  # 서울 리전

gcloud sql instances create $INSTANCE_NAME \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=$REGION \
  --network=default \
  --backup-start-time=03:00 \
  --retained-backups-count=30 \
  --transaction-log-retention-days=7
```

### 3.2 데이터베이스 및 사용자 생성

```bash
# 데이터베이스 생성
gcloud sql databases create onui_korean \
  --instance=$INSTANCE_NAME

# 비밀번호 생성 (보안)
DB_PASSWORD=$(openssl rand -base64 32)

# 사용자 생성
gcloud sql users create onui \
  --instance=$INSTANCE_NAME \
  --password=$DB_PASSWORD

echo "Database Password: $DB_PASSWORD"
```

### 3.3 Cloud SQL Auth Proxy 설정 (로컬 테스트용)

```bash
# Cloud SQL Proxy 다운로드
curl -o cloud-sql-proxy https://dl.google.com/cloudsql/cloud_sql_proxy.linux.amd64
chmod +x cloud-sql-proxy

# 프록시 실행
./cloud-sql-proxy onui-korean-saas:asia-northeast1:onui-korean-db &
```

### 3.4 백업 정책 설정

```bash
# 자동 백업 활성화 (이미 위에서 설정됨)
# 추가 설정 - 주간 전체 백업
gcloud sql backups create \
  --instance=$INSTANCE_NAME
```

---

## 4. Cloud Storage 설정

### 4.1 버킷 생성

```bash
BUCKET_NAME="onui-korean-storage-$PROJECT_ID"

gsutil mb -l asia-northeast1 gs://$BUCKET_NAME

# 액세스 제한
gsutil uniformbucketlevelaccess set on gs://$BUCKET_NAME

# 서비스 계정 권한 부여
gsutil iam ch \
  serviceAccount:onui-app@$PROJECT_ID.iam.gserviceaccount.com:objectCreator,objectViewer \
  gs://$BUCKET_NAME
```

### 4.2 폴더 구조 생성

```bash
# TTS 캐시
gsutil -m mkdir gs://$BUCKET_NAME/tts-cache/

# 사용자 업로드
gsutil -m mkdir gs://$BUCKET_NAME/uploads/

# 백업
gsutil -m mkdir gs://$BUCKET_NAME/backups/
```

### 4.3 라이프사이클 정책 (자동 정리)

`lifecycle.json`:
```json
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {"age": 30}  # 30일 이후 삭제
      },
      {
        "action": {"type": "SetStorageClass", "storageClass": "COLDLINE"},
        "condition": {"age": 90}   # 90일 이후 콜드라인 저장소로 이동
      }
    ]
  }
}
```

```bash
gsutil lifecycle set lifecycle.json gs://$BUCKET_NAME
```

---

## 5. Container Registry 및 Docker 이미지

### 5.1 Dockerfile 작성

`Dockerfile`:
```dockerfile
FROM python:3.8-slim

WORKDIR /app

# 시스템 의존성
RUN apt-get update && apt-get install -y \
    ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드
COPY . .

# 포트 노출
EXPOSE 8080

# 헬스 체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8080/health')"

# 실행
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### 5.2 이미지 빌드 및 푸시

```bash
IMAGE_NAME="gcr.io/$PROJECT_ID/onui-korean"
VERSION="1.0.0"

# 로컬 빌드
docker build -t $IMAGE_NAME:$VERSION -t $IMAGE_NAME:latest .

# GCP 인증
gcloud auth configure-docker

# 푸시
docker push $IMAGE_NAME:$VERSION
docker push $IMAGE_NAME:latest
```

---

## 6. Cloud Run 배포

### 6.1 배포 전 체크리스트

- [ ] Docker 이미지 준비
- [ ] Cloud SQL 인스턴스 생성
- [ ] Cloud Storage 버킷 생성
- [ ] 환경 변수 준비

### 6.2 .env 파일 (보안 - Secret Manager 사용)

```bash
# Secret Manager에 저장
echo -n "postgresql://onui:$DB_PASSWORD@/onui_korean?sslmode=require&host=/cloudsql/onui-korean-saas:asia-northeast1:onui-korean-db" | \
  gcloud secrets create database-url --data-file=-

echo -n "sk-proj-..." | \
  gcloud secrets create openai-api-key --data-file=-

echo -n "AIzaSyCPvnK..." | \
  gcloud secrets create gemini-api-key --data-file=-
```

### 6.3 Cloud Run 배포

```bash
SERVICE_NAME="onui-korean-app"
REGION="asia-northeast1"

gcloud run deploy $SERVICE_NAME \
  --image=$IMAGE_NAME:latest \
  --platform=managed \
  --region=$REGION \
  --allow-unauthenticated \
  --memory=2Gi \
  --cpu=1 \
  --timeout=3600 \
  --max-instances=100 \
  --min-instances=1 \
  --set-cloudsql-instances=onui-korean-saas:asia-northeast1:onui-korean-db \
  --update-secrets=DATABASE_URL=database-url:latest,OPENAI_API_KEY=openai-api-key:latest,GEMINI_API_KEY=gemini-api-key:latest \
  --set-env-vars=\
MODEL_BACKEND=ollama,\
STT_BACKEND=google,\
TTS_BACKEND=gemini,\
GCP_PROJECT_ID=$PROJECT_ID,\
BUCKET_NAME=$BUCKET_NAME
```

### 6.4 자동 스케일링 설정

```bash
# 최대 인스턴스 수 제한
gcloud run services update $SERVICE_NAME \
  --region=$REGION \
  --max-instances=50 \
  --min-instances=2
```

---

## 7. Cloud Load Balancer 설정

### 7.1 로드 밸런서 생성

```bash
# NEG (Network Endpoint Group) 생성
gcloud compute network-endpoint-groups create onui-neg \
  --region=$REGION \
  --network-endpoint-type=SERVERLESS \
  --cloud-run-service=$SERVICE_NAME \
  --cloud-run-region=$REGION

# 백엔드 서비스 생성
gcloud compute backend-services create onui-backend \
  --global \
  --load-balancing-scheme=EXTERNAL \
  --protocol=HTTP \
  --enable-cdn \
  --session-affinity=CLIENT_IP

# NEG를 백엔드 서비스에 추가
gcloud compute backend-services add-backend onui-backend \
  --global \
  --instance-group=onui-neg \
  --instance-group-region=$REGION

# URL 맵 생성
gcloud compute url-maps create onui-lb \
  --default-service=onui-backend

# HTTP 프록시 생성
gcloud compute target-http-proxies create onui-http-proxy \
  --url-map=onui-lb

# 포워딩 규칙 생성
gcloud compute forwarding-rules create onui-fw \
  --global \
  --target-http-proxy=onui-http-proxy \
  --address-region=us-central1 \
  --ports=80
```

### 7.2 SSL 인증서 추가 (HTTPS)

```bash
# 자체 관리 인증서
gcloud compute ssl-certificates create onui-cert \
  --certificate=path/to/cert.pem \
  --private-key=path/to/key.pem

# 또는 Google 관리 인증서
gcloud compute ssl-certificates create onui-managed-cert \
  --domains=korean.example.com
```

---

## 8. CI/CD 파이프라인 (Cloud Build)

### 8.1 cloudbuild.yaml 작성

```yaml
steps:
  # 1단계: 테스트
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'run'
      - '--rm'
      - '-v'
      - '/workspace:/workspace'
      - 'python:3.8'
      - 'bash'
      - '-c'
      - 'cd /workspace && pip install -r requirements.txt && python -m pytest'
    id: 'test'

  # 2단계: 이미지 빌드
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'build'
      - '-t'
      - 'gcr.io/$PROJECT_ID/onui-korean:$SHORT_SHA'
      - '-t'
      - 'gcr.io/$PROJECT_ID/onui-korean:latest'
      - '.'
    id: 'build-image'

  # 3단계: Container Registry에 푸시
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'push'
      - 'gcr.io/$PROJECT_ID/onui-korean:$SHORT_SHA'
    id: 'push-image'

  # 4단계: Cloud Run 배포
  - name: 'gcr.io/cloud-builders/gke-deploy'
    args:
      - 'run'
      - '--filename=.'
      - '--image=gcr.io/$PROJECT_ID/onui-korean:$SHORT_SHA'
      - '--location=$_REGION'
      - '--output=/dev/null'

  # 5단계: 배포 후 테스트
  - name: 'gcr.io/cloud-builders/gke-deploy'
    env:
      - 'CLOUDSDK_COMPUTE_REGION=$_REGION'
    args:
      - 'run'
      - '--test'

substitutions:
  _REGION: 'asia-northeast1'

images:
  - 'gcr.io/$PROJECT_ID/onui-korean:$SHORT_SHA'
  - 'gcr.io/$PROJECT_ID/onui-korean:latest'

timeout: '3600s'

onFailure:
  - name: 'gcr.io/cloud-builders/gke-deploy'
    args: ['rollout', 'undo', '--region=$_REGION']
```

### 8.2 GitHub 리포지토리 연결

```bash
# Google Cloud Console에서 설정
# Trigger 생성: GitHub 저장소 → Cloud Build → Cloud Run 자동 배포
```

---

## 9. 모니터링 및 로깅 (Cloud Logging, Cloud Monitoring)

### 9.1 로깅 설정

```python
# main.py에 추가
import google.cloud.logging

# Cloud Logging 클라이언트 초기화
logging_client = google.cloud.logging.Client()
logging_client.setup_logging()

# 그 후 일반 logging 사용
import logging
logger = logging.getLogger(__name__)
logger.info("Application started")
```

### 9.2 모니터링 대시보드 생성

```bash
# 커스텀 메트릭 기록
from google.cloud import monitoring_v3

client = monitoring_v3.MetricsServiceClient()
project_name = f"projects/{PROJECT_ID}"

# 시계열 데이터 작성
time_series = monitoring_v3.TimeSeries()
time_series.metric.type_ = 'custom.googleapis.com/onui/stt_requests'
time_series.resource.type = 'cloud_run_revision'
```

### 9.3 알람 설정

```bash
# CPU 사용률 > 80% 알람
gcloud alpha monitoring policies create \
  --notification-channels=CHANNEL_ID \
  --display-name="High CPU Usage" \
  --condition-display-name="CPU > 80%" \
  --condition-threshold-value=0.8 \
  --condition-threshold-filter='resource.type="cloud_run_revision"'
```

---

## 10. 멀티테넌트 아키텍처

### 10.1 테넌트 격리 전략

#### 스키마 기반 격리 (권장)

```python
# models.py
from sqlalchemy import Column, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Tenant(Base):
    __tablename__ = 'tenants'
    id = Column(String(50), primary_key=True)
    name = Column(String(255))
    database_url = Column(String(255))
    api_key = Column(String(255))

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(50), ForeignKey('tenants.id'))
    email = Column(String(255))
```

#### 행 기반 보안 (RLS)

```sql
-- PostgreSQL Row Level Security
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON users
  USING (tenant_id = current_setting('app.tenant_id'));
```

### 10.2 API 라우팅

```python
# main.py
from fastapi import Header, Request

@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    # 헤더에서 API 키 추출
    api_key = request.headers.get("X-API-Key")
    
    # 테넌트 확인
    tenant = db.query(Tenant).filter(Tenant.api_key == api_key).first()
    if not tenant:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    # 테넌트 ID를 요청에 첨부
    request.state.tenant_id = tenant.id
    return await call_next(request)
```

---

## 11. 비용 최적화

### 11.1 자동 스케일링 정책

```yaml
# Cloud Run - Min Instance 최소화
min_instances: 1      # 기본: 1
max_instances: 50     # 피크: 50

# 인스턴스 당 메모리
memory: "2Gi"         # 가격: $0.00002501 / vCPU-초
cpu: "1"              # 1 vCPU = $0.00001667 / 초
```

### 11.2 월 예상 비용 (100명 동시 사용 기준)

| 서비스 | 사용량 | 비용/월 |
|--------|--------|---------|
| Cloud Run | 8.6M vCPU초 | $144 |
| Cloud SQL | db-f1-micro | $45 |
| Cloud Storage | 100GB | $2 |
| Monitoring | 포함 | 무료 |
| **합계** | | **$191** |

### 11.3 비용 절감 팁

```bash
# 1. 커밋먼트 할인 (1년/3년)
# Console에서 "Compute Engine Commitments" 설정

# 2. 다중 리전 배포 (저가 리전 우선)
# asia-south1 (인도): 20% 저가

# 3. 예약 인스턴스 (Cloud SQL)
# 1년: 25% 할인, 3년: 52% 할인

# 4. 자동 스케일링 조정
# 야간 시간: min_instances=0 설정
```

---

## 12. 보안 (VPC, IAM, SSL)

### 12.1 VPC 설정

```bash
# VPC 생성
gcloud compute networks create onui-vpc \
  --subnet-mode=custom

# 서브넷 생성
gcloud compute networks subnets create onui-subnet \
  --network=onui-vpc \
  --region=$REGION \
  --range=10.0.0.0/24
```

### 12.2 Cloud SQL 방화벽

```bash
# 특정 IP만 허용
gcloud sql instances patch onui-korean-db \
  --allowed-networks=YOUR_IP/32
```

### 12.3 IAM 권한 최소화

```bash
# 역할별 최소 권한 할당
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:onui-app@$PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/cloudsql.client \
  --condition='resource.matchTag("env", "prod")'
```

### 12.4 SSL/TLS 자동 갱신

```bash
# Google Managed Certificate
gcloud compute ssl-certificates create onui-cert \
  --domains=korean.example.com \
  --global
```

---

## 13. 백업 및 재해복구

### 13.1 자동 백업 정책

```bash
# Cloud SQL 자동 백업 (7일 보존)
gcloud sql backups create \
  --instance=onui-korean-db \
  --backup-configuration-backup-enabled=true \
  --backup-configuration-backup-start-time=03:00
```

### 13.2 Cloud Storage 버킷 백업

```bash
# 클라우드 스토리지 검사점 활성화
gsutil versioning set on gs://$BUCKET_NAME

# 자동 정리 정책
gsutil lifecycle set lifecycle.json gs://$BUCKET_NAME
```

### 13.3 재해복구 계획 (RTO/RPO)

| 시나리오 | RTO | RPO | 방법 |
|---------|-----|-----|------|
| 데이터베이스 손상 | 1시간 | 1시간 | 자동 백업 복구 |
| 스토리지 손상 | 30분 | 즉시 | 버전 관리 복구 |
| 서비스 다운 | 5분 | 0분 | 다중 리전 배포 |

---

## 14. 배포 절차

### 14.1 개발 환경

```bash
# 로컬 테스트
docker build -t onui-korean:dev .
docker run -p 8080:8080 onui-korean:dev
```

### 14.2 스테이징 배포

```bash
# 스테이징 서비스 배포
gcloud run deploy onui-korean-staging \
  --image=gcr.io/$PROJECT_ID/onui-korean:latest \
  --tag=staging

# 트래픽 기본 설정 (10% 스테이징, 90% 프로덕션)
```

### 14.3 프로덕션 배포 체크리스트

- [ ] 모든 테스트 통과
- [ ] 보안 스캔 완료
- [ ] 데이터베이스 백업 확인
- [ ] 모니터링 알람 설정
- [ ] Runbook 준비 (장애 대응)
- [ ] 롤백 계획 수립

### 14.4 블루-그린 배포

```bash
# 새 리비전 배포
gcloud run deploy onui-korean-app \
  --image=gcr.io/$PROJECT_ID/onui-korean:new-version \
  --no-traffic

# 트래픽 전환 (10% → 50% → 100%)
gcloud run services update-traffic onui-korean-app \
  --to-revisions=LATEST=10
```

---

## 15. 액세스 관리 (멀티테넌트 API)

### 15.1 API Key 기반 인증

```python
# main.py
from fastapi import Header, HTTPException

VALID_API_KEYS = {
    "university-001": {"name": "Seoul University", "tier": "enterprise"},
    "university-002": {"name": "Busan University", "tier": "standard"}
}

@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        api_key = request.headers.get("X-API-Key")
        if not api_key or api_key not in VALID_API_KEYS:
            raise HTTPException(status_code=401, detail="Invalid API Key")
        request.state.tenant = VALID_API_KEYS[api_key]
    return await call_next(request)
```

### 15.2 사용량 추적 및 과금

```python
# 사용량 로깅
@app.post("/api/stt/process")
async def process_stt(request: Request, file: UploadFile):
    tenant = request.state.tenant
    
    # STT 처리
    result = await stt_service.process(file)
    
    # 사용량 기록
    usage = Usage(
        tenant_id=tenant["id"],
        service="stt",
        units=1,
        cost=0.02,
        timestamp=datetime.utcnow()
    )
    db.add(usage)
    db.commit()
    
    return result
```

---

## 16. 성능 최적화

### 16.1 CDN 설정

```bash
# Cloud CDN 활성화
gcloud compute backend-services update onui-backend \
  --global \
  --enable-cdn \
  --cache-mode=CACHE_ALL_STATIC
```

### 16.2 데이터베이스 쿼리 최적화

```bash
# Cloud SQL Insights로 느린 쿼리 분석
# Console: SQL Instances → Insights → Query Insights
```

### 16.3 이미지 최적화

```dockerfile
# 멀티 스테이지 빌드
FROM python:3.8 as builder
COPY requirements.txt .
RUN pip install -r requirements.txt

FROM python:3.8-slim
COPY --from=builder /usr/local/lib/python3.8/site-packages /usr/local/lib/python3.8/site-packages
```

---

## 17. 모니터링 및 알람

### 17.1 주요 메트릭

```bash
# 응답 시간
gcloud monitoring metrics-descriptors create custom.googleapis.com/onui/response_time_ms

# 에러율
gcloud monitoring metrics-descriptors create custom.googleapis.com/onui/error_rate

# 활성 사용자
gcloud monitoring metrics-descriptors create custom.googleapis.com/onui/active_users
```

### 17.2 대시보드

```bash
# Grafana 또는 Data Studio 연동
# Console → Monitoring → Dashboards
```

---

## 18. 문제 해결

### 18.1 Cloud Run 배포 실패

```bash
# 로그 확인
gcloud run services describe onui-korean-app --region=$REGION
gcloud logging read "resource.type=cloud_run_revision" --limit=50

# 이미지 테스트
docker run gcr.io/$PROJECT_ID/onui-korean:latest
```

### 18.2 Cloud SQL 연결 오류

```bash
# 연결 테스트
gcloud sql connect onui-korean-db

# 방화벽 확인
gcloud sql instances describe onui-korean-db | grep authorizedNetworks
```

### 18.3 높은 비용 (의외 요금)

```bash
# 비용 분석
gcloud billing accounts list
gcloud compute instances list --global  # 불필요한 리소스 확인

# 할당량 확인
gcloud compute project-info describe --project=$PROJECT_ID
```

---

## 19. 비용 관리 (Billing)

### 19.1 예산 알람

```bash
gcloud billing budgets create \
  --display-name="Onui Monthly Budget" \
  --budget-amount=500 \
  --threshold-rule=percent=50 \
  --threshold-rule=percent=90 \
  --threshold-rule=percent=100
```

### 19.2 리포트

```bash
# BigQuery에 비용 데이터 내보내기
# Console → Billing → Billing export to BigQuery
```

---

## 20. 초기 배포 체크리스트

```
[ ] GCP 프로젝트 생성 및 API 활성화
[ ] Cloud SQL 인스턴스 생성 및 데이터베이스 초기화
[ ] Cloud Storage 버킷 생성
[ ] 서비스 계정 생성 및 권한 할당
[ ] Docker 이미지 빌드 및 Container Registry 푸시
[ ] Cloud Run 배포
[ ] Cloud Load Balancer 설정
[ ] SSL 인증서 구성
[ ] Cloud Build CI/CD 파이프라인 설정
[ ] 모니터링 및 알람 설정
[ ] 백업 정책 확인
[ ] 보안 감사
[ ] 성능 테스트
[ ] 사용자 문서 작성
```

---

## 21. SaaS 운영 팁

### 21.1 자동화 스크립트

`deploy.sh`:
```bash
#!/bin/bash
set -e

PROJECT_ID=$1
VERSION=$2

# 이미지 빌드 및 푸시
docker build -t gcr.io/$PROJECT_ID/onui-korean:$VERSION .
docker push gcr.io/$PROJECT_ID/onui-korean:$VERSION

# Cloud Run 배포
gcloud run deploy onui-korean-app \
  --image=gcr.io/$PROJECT_ID/onui-korean:$VERSION \
  --region=asia-northeast1

echo "Deployment complete: $VERSION"
```

### 21.2 월간 검토 항목

- [ ] 비용 추이 분석
- [ ] 성능 메트릭 검토
- [ ] 보안 업데이트 확인
- [ ] 사용자 피드백 수집
- [ ] 스케일링 계획 검토

---

**마지막 업데이트**: 2026-01-19

**지원**: GCP 공식 문서 (https://cloud.google.com/docs)
