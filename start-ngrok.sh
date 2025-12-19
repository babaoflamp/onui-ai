#!/bin/bash

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   오누이 AI - ngrok Tunnel 시작${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# 0. 환경변수(.env) 로드 (안전 파싱)
if [ -f ".env" ]; then
  while IFS= read -r line; do
    # 주석/빈 줄 건너뛰기
    case "$line" in
      \#*|'' ) continue ;;
    esac
    # key=value 형식만 처리
    if printf "%s" "$line" | grep -q '='; then
      key="${line%%=*}"
      val="${line#*=}"
      # 양쪽 공백 제거
      key="$(printf "%s" "$key" | sed 's/^\s*//;s/\s*$//')"
      val="$(printf "%s" "$val" | sed 's/^\s*//;s/\s*$//')"
      # 따옴표 제거
      val="${val%"\""}"
      val="${val#"\""}"
      val="${val%\'}"
      val="${val#\'}"
      export "$key=$val"
    fi
  done < ./.env
fi

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
mkdir -p logs
source .venv/bin/activate

echo -e "${YELLOW}[3/4] FastAPI 서버 시작 중...${NC}"
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

# 환경 변수에서 고정 도메인(optional)
NGROK_DOMAIN=${NGROK_DOMAIN:-}
NGROK_AUTHTOKEN=${NGROK_AUTHTOKEN:-}

# ngrok 인증 토큰 설정 (유료/로그인 계정용)
if [ -n "$NGROK_AUTHTOKEN" ]; then
  ./ngrok config add-authtoken "$NGROK_AUTHTOKEN" >/dev/null 2>&1 || true
fi

# ngrok 시작
if [ -n "$NGROK_DOMAIN" ]; then
  nohup ./ngrok http --domain="$NGROK_DOMAIN" 9000 > logs/ngrok.log 2>&1 &
  NGROK_PID=$!
  sleep 5
  # 예약 도메인 실패 시 동적 도메인으로 재시도
  if ! pgrep -f "ngrok http" >/dev/null; then
    echo -e "${YELLOW}⚠ 예약 도메인(${NGROK_DOMAIN}) 시작 실패. 동적 도메인으로 재시도합니다.${NC}"
    nohup ./ngrok http 9000 > logs/ngrok.log 2>&1 &
    NGROK_PID=$!
    sleep 5
  fi
else
  nohup ./ngrok http 9000 > logs/ngrok.log 2>&1 &
  NGROK_PID=$!
  sleep 5
fi

# 퍼블릭 URL 추출
TUNNEL_URL=""
# ngrok API에서 public_url 파싱 (jq 없이)
if curl -s http://localhost:4040/api/tunnels > /tmp/ngrok_tunnels.json 2>/dev/null; then
  TUNNEL_URL=$(grep -o '"public_url":"https[^"]*"' /tmp/ngrok_tunnels.json | head -1 | sed 's/.*"public_url":"\(https[^\"]*\)".*/\1/')
fi

# 상태 출력
if pgrep -f "ngrok" > /dev/null; then
    echo -e "${GREEN}✓ ngrok 터널 시작됨 (PID: $NGROK_PID)${NC}"
    if [ -n "$TUNNEL_URL" ]; then
      echo -e "${GREEN}  → ${TUNNEL_URL}${NC}"
    else
      echo -e "${YELLOW}⚠ 퍼블릭 URL을 확인하지 못했습니다. ngrok 대시보드 또는 로그를 확인하세요.${NC}"
    fi
    if [ -n "$NGROK_DOMAIN" ]; then
      echo -e "${GREEN}  → Reserved Domain: ${NGROK_DOMAIN}${NC}"
    fi
    echo -e "${GREEN}  → Dashboard: http://localhost:4040${NC}"
else
    echo -e "${RED}✗ ngrok 터널 시작 실패${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}================================================${NC}"
echo -e "${GREEN}✓ 모든 서비스가 시작되었습니다!${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""
echo -e "${YELLOW}▶ 서비스 URL:${NC}"
if [ -n "$TUNNEL_URL" ]; then
  echo -e "  • Public: ${GREEN}${TUNNEL_URL}${NC}"
fi
echo -e "  • Local:  ${GREEN}http://localhost:9000${NC}"
echo ""
echo -e "${YELLOW}▶ 로그 확인:${NC}"
echo -e "  • uvicorn 로그: ${GREEN}tail -f logs/uvicorn.log${NC}"
echo -e "  • ngrok 로그: ${GREEN}tail -f logs/ngrok.log${NC}"
echo ""
echo -e "${YELLOW}▶ 서비스 중지:${NC}"
echo -e "  • 스크립트 실행: ${GREEN}./stop-service.sh${NC}"
echo ""
