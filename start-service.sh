#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   오누이 AI 한국어 학습 서비스 시작 (PM2)${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

cd /home/scottk/Projects/onui-ai

# 로그 디렉토리 생성
mkdir -p logs data/tmp

# PM2로 서비스 시작
echo -e "${YELLOW}[1/2] PM2로 서비스 시작 중...${NC}"
pm2 start ecosystem.config.js

sleep 3
echo ""

# 상태 확인
if pm2 show onui-ai | grep -q "online"; then
    echo -e "${GREEN}✓ onui-ai 서버 시작됨${NC}"
    echo -e "${GREEN}  → http://localhost:9002${NC}"
else
    echo -e "${RED}✗ onui-ai 서버 시작 실패${NC}"
    pm2 logs onui-ai --lines 20 --nostream
    exit 1
fi

if pm2 show onui-ngrok | grep -q "online"; then
    echo -e "${GREEN}✓ ngrok 터널 시작됨${NC}"
    echo -e "${GREEN}  → https://onui-ai.ngrok.app${NC}"
else
    echo -e "${YELLOW}⚠ ngrok 상태 확인 필요 (pm2 logs onui-ngrok)${NC}"
fi

echo ""
echo -e "${BLUE}================================================${NC}"
echo -e "${GREEN}✓ 서비스가 성공적으로 시작되었습니다!${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""
echo -e "${YELLOW}주요 명령어:${NC}"
echo -e "  • 상태 확인:   ${GREEN}pm2 status${NC}"
echo -e "  • 로그 보기:   ${GREEN}pm2 logs onui-ai${NC}"
echo -e "  • 재시작:      ${GREEN}pm2 restart onui-ai${NC}"
echo -e "  • 서비스 종료: ${GREEN}./stop-service.sh${NC}"
echo ""
