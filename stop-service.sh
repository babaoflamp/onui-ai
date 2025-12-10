#!/bin/bash

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   오누이 AI 서비스 종료${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# uvicorn 프로세스 종료
echo -e "${YELLOW}uvicorn 프로세스 종료 중...${NC}"
if pgrep -f "uvicorn main:app" > /dev/null; then
    pkill -f "uvicorn main:app"
    echo -e "${GREEN}✓ uvicorn 프로세스 종료됨${NC}"
else
    echo -e "${YELLOW}• uvicorn 프로세스 없음${NC}"
fi

# ngrok 프로세스 종료
echo -e "${YELLOW}ngrok 프로세스 종료 중...${NC}"
if pgrep -f "ngrok" > /dev/null; then
    pkill -f "ngrok"
    echo -e "${GREEN}✓ ngrok 프로세스 종료됨${NC}"
else
    echo -e "${YELLOW}• ngrok 프로세스 없음${NC}"
fi

echo ""
echo -e "${GREEN}✓ 모든 서비스가 종료되었습니다.${NC}"
echo ""
