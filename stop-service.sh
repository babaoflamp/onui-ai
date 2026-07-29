#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   OAI 한국어 학습 서비스 종료 (PM2)${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

cd /home/scottk/Projects/onui-ai

pm2 stop onui-ai 2>/dev/null
pm2 stop onui-ai-ngrok 2>/dev/null
echo -e "${GREEN}✓ 서비스가 중지되었습니다.${NC}"
echo ""
echo -e "${YELLOW}완전히 삭제하려면: ${GREEN}pm2 delete onui-ai onui-ai-ngrok${NC}"
echo -e "${YELLOW}다시 시작하려면:   ${GREEN}./start-service.sh${NC}"
echo ""
