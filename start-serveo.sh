#!/bin/bash

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   오누이 AI - Serveo Tunnel 시작${NC}"
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

# ssh serveo 프로세스 종료
if pgrep -f "ssh.*serveo" > /dev/null; then
    pkill -f "ssh.*serveo"
    echo -e "${GREEN}✓ serveo 프로세스 종료됨${NC}"
else
    echo -e "${YELLOW}• serveo 프로세스 없음${NC}"
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

# 4. Serveo Tunnel 시작
echo -e "${YELLOW}[4/4] Serveo Tunnel 시작 중...${NC}"
echo -e "${GREEN}요청된 고정 서브도메인: https://onui-ai.serveo.net${NC}"
echo ""

# Serveo 터널 시작 (백그라운드로 실행)
# -N: 원격 명령 실행 없이 포워딩만 수행
# -o StrictHostKeyChecking=no: 호스트키 확인 건너뜀
# nohup으로 백그라운드 실행 및 로그 저장
mkdir -p logs
nohup ssh -o StrictHostKeyChecking=no -N -R onui-ai:80:localhost:9000 serveo.net > logs/serveo.log 2>&1 &
SERVEO_PID=$!

# 터널 연결 대기
sleep 3

# Serveo URL 추출
if [ -f "logs/serveo.log" ]; then
    SERVEO_URL=$(grep -o 'https://[a-zA-Z0-9.-]*\.serveousercontent.com' logs/serveo.log | tail -1)
    if [ ! -z "$SERVEO_URL" ]; then
        echo -e "${GREEN}✓ Serveo Tunnel 시작됨 (PID: $SERVEO_PID)${NC}"
        echo -e "${GREEN}  → ${SERVEO_URL}${NC}"
    else
        echo -e "${YELLOW}⚠ Serveo URL을 찾을 수 없습니다. logs/serveo.log를 확인하세요.${NC}"
    fi
else
    echo -e "${RED}✗ Serveo 로그 파일이 생성되지 않았습니다${NC}"
fi
