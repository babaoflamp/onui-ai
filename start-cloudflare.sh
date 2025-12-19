#!/bin/bash

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   오누이 AI - Cloudflare Tunnel 시작${NC}"
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

# cloudflared 프로세스 종료
if pgrep -f "cloudflared" > /dev/null; then
    pkill -f "cloudflared"
    echo -e "${GREEN}✓ cloudflared 프로세스 종료됨${NC}"
else
    echo -e "${YELLOW}• cloudflared 프로세스 없음${NC}"
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

# 4. Cloudflare Tunnel 시작
echo -e "${YELLOW}[4/4] Cloudflare Tunnel 시작 중...${NC}"

# cloudflared 실행 파일 확인
if [ ! -f "./cloudflared" ]; then
    echo -e "${RED}✗ cloudflared 파일이 없습니다${NC}"
    exit 1
fi

# Cloudflare Tunnel 시작 (백그라운드)
nohup ./cloudflared tunnel --url http://localhost:9000 > logs/cloudflare.log 2>&1 &
CLOUDFLARE_PID=$!

# 터널이 시작될 때까지 대기
sleep 5

# Cloudflare URL 추출
if [ -f "logs/cloudflare.log" ]; then
    TUNNEL_URL=$(grep -o 'https://[a-zA-Z0-9.-]*\.trycloudflare.com' logs/cloudflare.log | head -1)
    if [ ! -z "$TUNNEL_URL" ]; then
        echo -e "${GREEN}✓ Cloudflare Tunnel 시작됨 (PID: $CLOUDFLARE_PID)${NC}"
        echo -e "${GREEN}  → ${TUNNEL_URL}${NC}"
    else
        echo -e "${YELLOW}⚠ Cloudflare URL을 찾을 수 없습니다. logs/cloudflare.log를 확인하세요.${NC}"
    fi
else
    echo -e "${RED}✗ Cloudflare 로그 파일이 생성되지 않았습니다${NC}"
fi

echo ""
echo -e "${BLUE}================================================${NC}"
echo -e "${GREEN}✓ 모든 서비스가 시작되었습니다!${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""
echo -e "${YELLOW}▶ 서비스 URL:${NC}"
if [ ! -z "$TUNNEL_URL" ]; then
    echo -e "  • Public: ${GREEN}${TUNNEL_URL}${NC}"
fi
echo -e "  • Local:  ${GREEN}http://localhost:9000${NC}"
echo ""
echo -e "${YELLOW}▶ 로그 확인:${NC}"
echo -e "  • uvicorn 로그: ${GREEN}tail -f logs/uvicorn.log${NC}"
echo -e "  • cloudflare 로그: ${GREEN}tail -f logs/cloudflare.log${NC}"
echo ""
echo -e "${YELLOW}▶ 서비스 중지:${NC}"
echo -e "  • 스크립트 실행: ${GREEN}./stop-service.sh${NC}"
echo ""
