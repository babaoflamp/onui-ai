#!/bin/bash

# Google Cloud Run 배포 스크립트
# 사용법: ./deploy.sh [프로젝트ID]

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 프로젝트 ID 설정
PROJECT_ID=${1:-$(gcloud config get-value project)}

if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}❌ 프로젝트 ID를 지정해주세요${NC}"
    echo "사용법: ./deploy.sh [프로젝트ID]"
    exit 1
fi

echo -e "${GREEN}🚀 Onui Korean - Cloud Run 배포 시작${NC}"
echo "프로젝트 ID: $PROJECT_ID"
echo ""

# 1. 프로젝트 설정
echo -e "${YELLOW}📋 Step 1: 프로젝트 설정${NC}"
gcloud config set project $PROJECT_ID

# 2. 필수 API 활성화
echo -e "${YELLOW}📋 Step 2: 필수 API 활성화${NC}"
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  containerregistry.googleapis.com \
  cloudresourcemanager.googleapis.com

# 3. Docker 이미지 빌드 및 푸시
echo -e "${YELLOW}📋 Step 3: Docker 이미지 빌드${NC}"
IMAGE_NAME="gcr.io/$PROJECT_ID/onui-korean"
docker build -t $IMAGE_NAME:latest .

echo -e "${YELLOW}📋 Step 4: Container Registry에 푸시${NC}"
docker push $IMAGE_NAME:latest

# 4. Cloud Run 배포
echo -e "${YELLOW}📋 Step 5: Cloud Run 배포${NC}"
gcloud run deploy onui-korean \
  --image $IMAGE_NAME:latest \
  --platform managed \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --max-instances 10 \
  --min-instances 0 \
  --port 8080 \
  --timeout 300 \
  --set-env-vars "$(cat .env.production 2>/dev/null || echo 'ENV=production')"

# 5. 배포 완료
echo ""
echo -e "${GREEN}✅ 배포가 완료되었습니다!${NC}"
echo ""
echo "서비스 URL을 확인하려면 다음 명령어를 실행하세요:"
echo "gcloud run services describe onui-korean --region asia-northeast1 --format 'value(status.url)'"
echo ""
echo "로그를 보려면:"
echo "gcloud run services logs read onui-korean --region asia-northeast1"
