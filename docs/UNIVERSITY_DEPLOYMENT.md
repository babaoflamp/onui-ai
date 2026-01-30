# 대학 환경 배포 가이드

오누이 한국어를 대학교 서버에 구축하기 위한 스펙 및 설치 방법입니다.

---

## 1. 서버 하드웨어 스펙

### 최소 사양 (개발/테스트용)
```
CPU:      4 cores (Intel i5/AMD Ryzen 5 이상)
RAM:      8 GB
Storage:  50 GB SSD
Network:  100 Mbps 이상
```

### 권장 사양 (50~200명 동시 사용)
```
CPU:      8 cores (Intel i7/AMD Ryzen 7 이상)
RAM:      16 GB
Storage:  100 GB SSD
Network:  1 Gbps
```

### 대규모 사양 (500명 이상 동시 사용)
```
CPU:      16+ cores (Xeon E5 이상)
RAM:      32 GB 이상
Storage:  500 GB SSD + 100 GB HDD (백업)
Network:  10 Gbps 또는 다중 대역폭
데이터베이스: 별도 서버 (PostgreSQL 권장)
```

---

## 2. 소프트웨어 환경

### 운영 체제
- **Linux**: Ubuntu 20.04 LTS / 22.04 LTS (권장)
- **CentOS**: 7.x 이상
- **Windows Server**: 2019 이상

### 필수 소프트웨어

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y \
  python3.8 python3-pip python3-venv \
  ffmpeg libsndfile1 \
  curl wget \
  git \
  nginx \
  postgresql postgresql-contrib \
  supervisor

# CentOS/RHEL
sudo yum install -y \
  python3 python3-pip python3-virtualenv \
  ffmpeg libsndfile \
  curl wget \
  git \
  nginx \
  postgresql-server postgresql-contrib \
  supervisor
```

---

## 3. 애플리케이션 설치 가이드

### 3.1 저장소 클론

```bash
cd /opt  # 또는 대학 표준 경로
git clone https://github.com/your-org/onui-ai.git
cd onui-ai
```

### 3.2 Python 가상환경 설정

```bash
python3.8 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

### 3.3 데이터베이스 초기화

#### SQLite (소규모)
```bash
python create_admin.py  # 기본 관리자 생성
```

#### PostgreSQL (대규모)
```bash
# 데이터베이스 생성
sudo -u postgres createdb onui_korean
sudo -u postgres psql -c "CREATE USER onui WITH PASSWORD 'strong_password';"
sudo -u postgres psql -c "ALTER ROLE onui SET client_encoding TO 'utf8';"

# .env 업데이트
echo "DATABASE_URL=postgresql://onui:strong_password@localhost:5432/onui_korean" >> .env
```

### 3.4 환경 변수 설정 (.env 파일)

```bash
# 모델 백엔드
MODEL_BACKEND=ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=exaone3.5:2.4b

# STT/TTS
STT_BACKEND=google  # 또는 openai, local
TTS_BACKEND=gemini  # 또는 openai, mztts

# Google Cloud (STT/TTS용)
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# OpenAI (선택)
# OPENAI_API_KEY=sk-...
# OPENAI_MODEL=gpt-4o-mini

# Gemini (선택)
# GEMINI_API_KEY=...
# GEMINI_MODEL=gemini-2.0-flash-exp

# MzTTS (한국어 TTS)
MZTTS_API_URL=http://112.220.79.218:56014

# 로컬 STT (대체 옵션)
LOCAL_STT=vosk
VOSK_MODEL_PATH=/opt/models/vosk-model-small-ko-0.22

# 웹 서비스 설정
NGROK_AUTHTOKEN=your_token  # (선택, 공개 접근용)
NGROK_DOMAIN=your-domain.ngrok.app

# 로깅 및 캐시
TTS_CACHE_DIR=/var/cache/onui_korean/tts
TTS_CACHE_MAX=1000
ONUI_TMP_DIR=/tmp/onui_korean
```

---

## 4. Ollama 로컬 모델 서버 설정

### 4.1 설치

```bash
# Ubuntu/Debian
curl -fsSL https://ollama.ai/install.sh | sh

# macOS
# https://ollama.ai 에서 다운로드

# 또는 Docker
docker pull ollama/ollama
docker run -d -p 11434:11434 -v ollama:/root/.ollama ollama/ollama
```

### 4.2 모델 다운로드

```bash
ollama pull exaone3.5:2.4b
ollama pull llama2:7b  # 백업 모델

# 실행 확인
curl http://localhost:11434/v1/models
```

### 4.3 systemd 서비스 등록 (자동 시작)

```bash
# Ubuntu/Debian
sudo systemctl enable ollama
sudo systemctl start ollama

# 상태 확인
sudo systemctl status ollama
```

---

## 5. Nginx 리버스 프록시 설정

### 5.1 `/etc/nginx/sites-available/onui-korean`

```nginx
upstream onui_app {
    server 127.0.0.1:9000;
    server 127.0.0.1:9001;  # 로드 밸런싱 (선택)
}

server {
    listen 80;
    server_name korean.example.edu;

    # HTTPS 리다이렉트 (선택)
    # return 301 https://$server_name$request_uri;

    client_max_body_size 20M;

    location / {
        proxy_pass http://onui_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_request_buffering off;
    }

    location /static/ {
        alias /opt/onui-ai/static/;
        expires 7d;
    }

    location /uploads/ {
        alias /opt/onui-ai/uploads/;
        expires 1d;
    }
}
```

### 5.2 Nginx 활성화

```bash
sudo ln -s /etc/nginx/sites-available/onui-korean /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## 6. 애플리케이션 자동 시작 (Supervisor/systemd)

### 6.1 Supervisor 설정

`/etc/supervisor/conf.d/onui-korean.conf`:

```ini
[program:onui-korean]
directory=/opt/onui-ai
command=/opt/onui-ai/.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 9000
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/onui-korean.log
environment=PATH="/opt/onui-ai/.venv/bin",HOME="/opt/onui-ai"
```

### 6.2 활성화

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start onui-korean
sudo supervisorctl status onui-korean
```

### 6.3 systemd 대체 방식

`/etc/systemd/system/onui-korean.service`:

```ini
[Unit]
Description=Onui Korean Learning Platform
After=network.target ollama.service

[Service]
Type=notify
User=www-data
WorkingDirectory=/opt/onui-ai
ExecStart=/opt/onui-ai/.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 9000
Restart=always
RestartSec=10
Environment="PATH=/opt/onui-ai/.venv/bin"
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 6.4 systemd 활성화

```bash
sudo systemctl daemon-reload
sudo systemctl enable onui-korean
sudo systemctl start onui-korean
sudo systemctl status onui-korean
```

---

## 7. SSL/TLS 인증서 설정 (HTTPS)

### Let's Encrypt + Certbot

```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot certonly --nginx -d korean.example.edu

# Nginx 설정 업데이트
sudo nano /etc/nginx/sites-available/onui-korean
```

Nginx에 다음 추가:

```nginx
server {
    listen 443 ssl;
    server_name korean.example.edu;

    ssl_certificate /etc/letsencrypt/live/korean.example.edu/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/korean.example.edu/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # ... 나머지 설정
}

# HTTP -> HTTPS 리다이렉트
server {
    listen 80;
    server_name korean.example.edu;
    return 301 https://$server_name$request_uri;
}
```

---

## 8. 백업 및 복구

### 8.1 데이터베이스 백업

```bash
# SQLite
cp data/users.db /backup/users.db.$(date +%Y%m%d)

# PostgreSQL
pg_dump onui_korean | gzip > /backup/onui_korean_$(date +%Y%m%d).sql.gz
```

### 8.2 자동 백업 (cron)

```bash
# crontab 편집
crontab -e

# 매일 자정 백업
0 0 * * * /opt/onui-ai/scripts/backup.sh
```

`/opt/onui-ai/scripts/backup.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/backup/onui-korean"
mkdir -p $BACKUP_DIR
pg_dump onui_korean | gzip > $BACKUP_DIR/db_$(date +%Y%m%d_%H%M%S).sql.gz
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete  # 30일 이상 파일 삭제
```

---

## 9. 성능 최적화

### 9.1 동시 연결 한계 증가

`/etc/security/limits.conf`:

```
www-data soft nofile 65535
www-data hard nofile 65535
```

### 9.2 Nginx 연결 최적화

```nginx
worker_processes auto;
worker_connections 4096;
keepalive_timeout 65;
```

### 9.3 데이터베이스 연결 풀링 (PostgreSQL)

`pgBouncer` 설치:

```bash
sudo apt-get install pgbouncer

# /etc/pgbouncer/pgbouncer.ini 설정
```

### 9.4 Redis 캐싱 (선택)

```bash
sudo apt-get install redis-server
redis-cli ping  # "PONG" 응답 확인
```

---

## 10. 모니터링 및 로깅

### 10.1 로그 위치

```
- 애플리케이션: /var/log/onui-korean.log
- Nginx: /var/log/nginx/access.log, /var/log/nginx/error.log
- Ollama: ~/.ollama/ollama.log
```

### 10.2 실시간 모니터링

```bash
# 애플리케이션 로그
tail -f /var/log/onui-korean.log

# 시스템 리소스
top -b -n1 | head -20
```

### 10.3 모니터링 도구 (선택)

- **Prometheus + Grafana**: 메트릭 수집 및 시각화
- **ELK Stack**: 로그 분석
- **Sentry**: 에러 추적

---

## 11. API 비용 추정 (월 기준)

| 서비스 | 월 활성 사용자 | 예상 비용 | 비고 |
|--------|--|--|--|
| OpenAI Whisper (STT) | 500 | $200 | 50,000 요청 기준 |
| OpenAI TTS | 500 | $250 | 25MB 오디오 생성 |
| Google Cloud STT | 500 | $150 | 할인 적용 시 |
| Google Cloud TTS | 500 | $100 | 영어 기준 |
| Gemini API | 500 | $50 | 무료 티어 포함 |
| 자체 호스팅 (Ollama) | 500 | $0 | 서버 전기료 제외 |

**권장**: 대학 규모면 **Ollama(로컬 LLM) + Google Cloud STT/TTS** 조합으로 비용 최소화

---

## 12. 보안 체크리스트

- [ ] 방화벽 설정 (SSH 22, HTTP 80, HTTPS 443만 허용)
- [ ] HTTPS 활성화
- [ ] 정기적 보안 패치 (Ubuntu: `sudo apt-get update && sudo apt-get upgrade`)
- [ ] 데이터베이스 암호 변경
- [ ] API 키/토큰 환경변수로 관리 (git에 커밋 금지)
- [ ] 관리자 계정 비활성화 또는 강한 비밀번호 설정
- [ ] 로그 접근 제한
- [ ] 정기적 백업 테스트

---

## 13. 초기 배포 체크리스트

```bash
# 1. 저장소 클론
git clone ... && cd onui-ai

# 2. 가상환경 생성
python3.8 -m venv .venv && source .venv/bin/activate

# 3. 의존성 설치
pip install -r requirements.txt

# 4. .env 파일 생성
cp .env.example .env
nano .env  # 환경변수 수정

# 5. 데이터베이스 초기화
python create_admin.py

# 6. Ollama 시작
ollama serve &

# 7. 애플리케이션 시작
python -m uvicorn main:app --host 0.0.0.0 --port 9000

# 8. http://localhost:9000 접속 확인
```

---

## 14. 문제 해결

### Ollama 연결 실패

```bash
# Ollama 상태 확인
curl http://localhost:11434/v1/models

# Ollama 재시작
systemctl restart ollama
```

### 높은 메모리 사용량

```bash
# 프로세스 확인
ps aux | grep python
ps aux | grep ollama

# 모델 언로드
curl -X POST http://localhost:11434/api/generate -d '{"model":"exaone3.5:2.4b","stream":false}' -H "Content-Type: application/json"
```

### STT 오류 ("credentials not found")

```bash
# Google 자격증명 확인
echo $GOOGLE_APPLICATION_CREDENTIALS

# 설정
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

---

## 15. 지원 및 문의

- 기술 문서: 프로젝트 `docs/` 폴더
- 이슈 리포트: GitHub Issues
- 커뮤니티: 대학 내 LMS 공지사항

---

**마지막 업데이트**: 2026-01-19
