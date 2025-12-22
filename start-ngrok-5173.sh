#!/bin/bash

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PORT=5173
WEB_PORT=${NGROK_5173_WEB_PORT:-4041}
LOG_DIR="logs"
LOG_FILE="$LOG_DIR/ngrok-5173.log"

echo -e "${BLUE}===============================================${NC}"
echo -e "${BLUE}   오누이 AI - ngrok (port $PORT) 시작${NC}"
echo -e "${BLUE}===============================================${NC}"

mkdir -p "$LOG_DIR"

# 기존 5173 ngrok 프로세스 종료
if pgrep -f "ngrok http .*${PORT}" >/dev/null; then
  echo -e "${YELLOW}기존 ngrok(${PORT}) 프로세스를 종료합니다...${NC}"
  pkill -f "ngrok http .*${PORT}"
  sleep 2
  echo -e "${GREEN}✓ 기존 ngrok 종료${NC}"
else
  echo -e "${YELLOW}기존 ngrok(${PORT}) 프로세스 없음${NC}"
fi

# ngrok 바이너리 확인
if [ ! -x ./ngrok ]; then
  echo -e "${RED}✗ ./ngrok 파일이 없습니다. README의 설치 단계를 참고하세요.${NC}"
  exit 1
fi

# 환경 변수에서 도메인 / 토큰 로드
if [ -f ".env" ]; then
  export $(grep -E '^NGROK_5173_DOMAIN=' .env | xargs)
  export $(grep -E '^NGROK_AUTHTOKEN=' .env | xargs)
fi

if [ -n "$NGROK_AUTHTOKEN" ]; then
  ./ngrok config add-authtoken "$NGROK_AUTHTOKEN" >/dev/null 2>&1 || true
fi

DOMAIN_ARG=()
if [ -n "$NGROK_5173_DOMAIN" ]; then
  DOMAIN_ARG=(--domain="$NGROK_5173_DOMAIN")
  echo -e "${YELLOW}예약 도메인 ${NGROK_5173_DOMAIN}으로 시작합니다.${NC}"
else
  echo -e "${YELLOW}동적 도메인으로 ngrok을 시작합니다.${NC}"
fi

nohup ./ngrok http "${DOMAIN_ARG[@]}" --web-port $WEB_PORT $PORT > "$LOG_FILE" 2>&1 &
NGROK_PID=$!

echo -e "${YELLOW}ngrok 초기화 중...${NC}"
sleep 5

if ! ps -p $NGROK_PID >/dev/null; then
  echo -e "${RED}✗ ngrok 실행에 실패했습니다. 로그를 확인하세요: $LOG_FILE${NC}"
  exit 1
fi

PUBLIC_URL=""
if command -v curl >/dev/null; then
  TUNNEL_JSON=$(curl -s "http://localhost:${WEB_PORT}/api/tunnels" 2>/dev/null)
  PUBLIC_URL=$(echo "$TUNNEL_JSON" | grep -o '"public_url":"https[^"]*"' | head -1 | sed 's/.*"public_url":"\(https[^\"]*\)".*/\1/')
fi

if [ -n "$PUBLIC_URL" ]; then
  echo -e "${GREEN}✓ ngrok (PID: $NGROK_PID) → ${PUBLIC_URL}${NC}"
else
  echo -e "${GREEN}✓ ngrok (PID: $NGROK_PID)${NC}"
  echo -e "${YELLOW}  ※ 퍼블릭 URL은 http://localhost:${WEB_PORT} 대시보드에서 확인하세요.${NC}"
fi

echo ""
echo -e "${YELLOW}로그 파일:${NC} $LOG_FILE"
echo -e "${YELLOW}웹 대시보드:${NC} http://localhost:${WEB_PORT}"
echo -e "${YELLOW}프로세스 종료:${NC} pkill -f 'ngrok http .*${PORT}'"
