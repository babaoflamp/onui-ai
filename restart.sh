#!/bin/bash
# onui-ai 서비스 재시작 (PM2)

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "PM2로 onui-ai / onui-ai-ngrok 재시작 중..."
pm2 restart onui-ai onui-ai-ngrok

sleep 3
echo ""
pm2 status onui-ai onui-ai-ngrok
