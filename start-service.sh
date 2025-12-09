#!/bin/bash

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   오누이 AI 한국어 학습 서비스 시작${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# 1. 기존 프로세스 종료
echo -e "${YELLOW}[1/4] 기존 프로세스 종료 중...${NC}"

# uvicorn 프로세스 종료
if pgrep -f "uvicorn main:app" > /dev/null; then
    pkill -f "uvicorn main:app"
    echo -e "${GREEN}✓ uvicorn 프로세스 종료됨${NC}"
else
    echo -e "${YELLOW}• uvicorn 프로세스 없음${NC}"
fi

# ngrok 프로세스 종료
if pgrep -f "ngrok" > /dev/null; then
    pkill -f "ngrok"
    echo -e "${GREEN}✓ ngrok 프로세스 종료됨${NC}"
else
    echo -e "${YELLOW}• ngrok 프로세스 없음${NC}"
fi

# 프로세스가 완전히 종료될 때까지 대기
sleep 2
echo ""

# 2. 가상환경 활성화 확인
echo -e "${YELLOW}[2/4] 가상환경 확인 중...${NC}"
if [ ! -d ".venv" ]; then
    echo -e "${RED}✗ 가상환경이 없습니다. python -m venv .venv 로 생성해주세요.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ 가상환경 확인 완료${NC}"
echo ""

# 3. FastAPI 서버 시작
echo -e "${YELLOW}[3/4] FastAPI 서버 시작 중...${NC}"
mkdir -p logs
source .venv/bin/activate
nohup python -m uvicorn main:app --host 0.0.0.0 --port 9000 --reload > logs/uvicorn.log 2>&1 &
UVICORN_PID=$!

# 서버가 시작될 때까지 대기
sleep 3

# 서버 상태 확인
if pgrep -f "uvicorn main:app" > /dev/null; then
    echo -e "${GREEN}✓ FastAPI 서버 시작됨 (PID: $UVICORN_PID)${NC}"
    echo -e "${GREEN}  → http://localhost:9000${NC}"
else
    echo -e "${RED}✗ FastAPI 서버 시작 실패${NC}"
    exit 1
fi
echo ""

# 4. ngrok 터널 시작
echo -e "${YELLOW}[4/4] ngrok 터널 시작 중...${NC}"

# ngrok 실행 파일 확인
if [ ! -f "./ngrok" ]; then
    echo -e "${RED}✗ ngrok 실행 파일이 없습니다.${NC}"
    echo -e "${YELLOW}  다음 명령어로 설치하세요:${NC}"
    echo -e "${YELLOW}  curl -Lo /tmp/ngrok.tgz https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz${NC}"
    echo -e "${YELLOW}  tar xzf /tmp/ngrok.tgz -C .${NC}"
    echo -e "${YELLOW}  chmod +x ngrok${NC}"
    exit 1
fi

# 로그 디렉토리 생성
mkdir -p logs

# ngrok 시작 (고정 도메인 사용)
nohup ./ngrok http --domain=brainlessly-unequestrian-ember.ngrok-free.dev 9000 > logs/ngrok.log 2>&1 &
NGROK_PID=$!

# ngrok이 시작될 때까지 대기
sleep 3

# ngrok 상태 확인
if pgrep -f "ngrok" > /dev/null; then
    echo -e "${GREEN}✓ ngrok 터널 시작됨 (PID: $NGROK_PID)${NC}"
    echo -e "${GREEN}  → https://brainlessly-unequestrian-ember.ngrok-free.dev${NC}"
    echo -e "${GREEN}  → Dashboard: http://localhost:4040${NC}"
else
    echo -e "${RED}✗ ngrok 터널 시작 실패${NC}"
    exit 1
fi
echo ""

# 5. 완료 메시지
echo -e "${BLUE}================================================${NC}"
echo -e "${GREEN}✓ 서비스가 성공적으로 시작되었습니다!${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""
echo -e "${YELLOW}접속 URL:${NC}"
echo -e "  • 로컬: ${GREEN}http://localhost:9000${NC}"
echo -e "  • 외부: ${GREEN}https://brainlessly-unequestrian-ember.ngrok-free.dev${NC}"
echo ""
echo -e "${YELLOW}모니터링:${NC}"
echo -e "  • ngrok 대시보드: ${GREEN}http://localhost:4040${NC}"
echo -e "  • uvicorn 로그: ${GREEN}tail -f logs/uvicorn.log${NC}"
echo -e "  • ngrok 로그: ${GREEN}tail -f logs/ngrok.log${NC}"
echo ""
echo -e "${YELLOW}서비스 종료:${NC}"
echo -e "  • ${GREEN}./stop-service.sh${NC} 또는 ${GREEN}pkill -f uvicorn && pkill -f ngrok${NC}"
echo ""
