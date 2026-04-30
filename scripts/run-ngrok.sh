#!/bin/bash
cd /home/scottk/Projects/onui-ai

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
      val="${val%\"}"
      val="${val#\"}"
      val="${val%\'}"
      val="${val#\'}"
      export "$key=$val"
    fi
  done < ./.env
fi

# ngrok 실행 파일 확인 (시스템 경로 또는 로컬 디렉터리)
NGROK_BIN=""
if command -v ngrok >/dev/null 2>&1; then
    NGROK_BIN=$(command -v ngrok)
elif [ -f "./ngrok" ]; then
    NGROK_BIN="./ngrok"
fi

if [ -z "$NGROK_BIN" ]; then
    echo "ngrok executable not found in PATH or local directory. Downloading..."
    # 다운로드가 실패할 수 있으므로 curl 대신 wget도 고려할 수 있지만, 여기서는 curl을 유지하되 URL 체크를 강화할 수 있습니다.
    # 현재 bin.equinox.io가 500 오류를 내는 경우가 있으므로, 설치된 ngrok이 없는 경우에만 시도합니다.
    curl -Lo /tmp/ngrok.tgz https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
    if [ $? -eq 0 ]; then
        tar xzf /tmp/ngrok.tgz -C .
        chmod +x ngrok
        NGROK_BIN="./ngrok"
    else
        echo "Failed to download ngrok. Please install it manually."
        exit 1
    fi
fi

# 환경 변수에서 고정 도메인(optional)
NGROK_AUTHTOKEN=${NGROK_AUTHTOKEN:-}

# ngrok 인증 토큰 설정 (유료/로그인 계정용)
if [ -n "$NGROK_AUTHTOKEN" ]; then
  "$NGROK_BIN" config add-authtoken "$NGROK_AUTHTOKEN" --config=ngrok-config.yml >/dev/null 2>&1 || true
fi

# ngrok 시작 (NGROK_DOMAIN이 설정된 경우 해당 도메인 사용)
if [ -n "$NGROK_DOMAIN" ]; then
  echo "Starting ngrok with domain: $NGROK_DOMAIN"
  exec "$NGROK_BIN" http --config=ngrok-config.yml --url="$NGROK_DOMAIN" 9002
else
  echo "Starting ngrok with random domain"
  exec "$NGROK_BIN" http --config=ngrok-config.yml 9002
fi
