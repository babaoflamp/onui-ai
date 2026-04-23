#!/bin/bash
# onui-ai 서비스 재시작

PORT=9002
DIR="$(cd "$(dirname "$0")" && pwd)"

# 기존 프로세스 종료
PIDS=$(lsof -ti :$PORT)
if [ -n "$PIDS" ]; then
    echo "기존 프로세스 종료 중 (PIDs: $PIDS)..."
    kill -9 $PIDS
    
    # 포트가 완전히 반환될 때까지 대기 (최대 5초)
    for i in {1..5}; do
        if ! lsof -i :$PORT > /dev/null; then
            break
        fi
        echo "포트 $PORT 해제 대기 중... ($i/5)"
        sleep 1
    done
fi

# 재시작
echo "포트 $PORT 에서 서버 시작..."
nohup "$DIR/.venv/bin/python3" -m uvicorn main:app \
    --host 0.0.0.0 --port $PORT --reload \
    > "$DIR/logs/uvicorn.log" 2>&1 &

echo "PID: $!"
sleep 3
tail -4 "$DIR/logs/uvicorn.log"
