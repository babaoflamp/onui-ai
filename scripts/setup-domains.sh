#!/bin/bash
# opportunity.ai.kr 및 onui.ai.kr 도메인 연결 설정 스크립트
# 실행: sudo bash scripts/setup-domains.sh
set -e

DOMAIN="opportunity.ai.kr"
EMAIL="babaoflamp@gmail.com"
PROJECT_DIR="/home/scottk/Projects/onui-ai"
NGINX_CONF="/etc/nginx/sites-available/${DOMAIN}"

echo "=== [1/6] UFW 방화벽 포트 오픈 ==="
ufw allow 80/tcp
ufw allow 443/tcp
ufw reload || true

echo ""
echo "=== [2/6] nginx + certbot 설치 및 디렉토리 준비 ==="
apt update -q || true
apt install -y nginx certbot python3-certbot-nginx
mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled

echo ""
echo "=== [3/6] nginx 사이트 설정 (HTTP only — certbot 실행 전) ==="
cat > "$NGINX_CONF" << 'NGINX_CONF_EOF'
server {
    listen 80;
    listen [::]:80;
    server_name opportunity.ai.kr www.opportunity.ai.kr onui.ai.kr www.onui.ai.kr;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
    location / {
        return 301 https://$host$request_uri;
    }
}
NGINX_CONF_EOF

ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/
nginx -t
systemctl enable nginx
systemctl restart nginx

echo ""
echo "=== [4/6] DNS 전파 확인 ==="
SERVER_IP=$(curl -s https://api.ipify.org)
RESOLVED_IP1=$(nslookup opportunity.ai.kr 8.8.8.8 2>/dev/null | awk '/^Address: / { print $2 }' | tail -1)
RESOLVED_IP2=$(nslookup onui.ai.kr 8.8.8.8 2>/dev/null | awk '/^Address: / { print $2 }' | tail -1)
echo "  서버 공인 IP : $SERVER_IP"
echo "  DNS 조회 결과 (opportunity.ai.kr): $RESOLVED_IP1"
echo "  DNS 조회 결과 (onui.ai.kr): $RESOLVED_IP2"

if [ "$SERVER_IP" != "$RESOLVED_IP1" ] || [ "$SERVER_IP" != "$RESOLVED_IP2" ]; then
    echo ""
    echo "  ⚠️  DNS가 아직 전파되지 않았습니다. 두 도메인 모두 연결이 필요합니다."
    echo "  도메인 등록 업체에서 아래 레코드를 서버 IP($SERVER_IP)로 설정하세요:"
    echo "    A  @    (opportunity.ai.kr)"
    echo "    A  www  (opportunity.ai.kr)"
    echo "    A  @    (onui.ai.kr)"
    echo "    A  www  (onui.ai.kr)"
    echo ""
    exit 1
fi

echo ""
echo "=== [5/6] SSL 인증서 발급 (Let's Encrypt) ==="
certbot --nginx -d "opportunity.ai.kr" -d "www.opportunity.ai.kr" \
    -d "onui.ai.kr" -d "www.onui.ai.kr" \
    --email "${EMAIL}" \
    --agree-tos \
    --no-eff-email \
    --redirect \
    --non-interactive

echo ""
echo "=== [5b/6] 완전한 nginx 설정 적용 (WebSocket, static 서빙, body size) ==="
cp "${PROJECT_DIR}/nginx-domains.conf" "$NGINX_CONF"
nginx -t && systemctl reload nginx

echo ""
echo "=== [6/6] static 파일 접근 권한 (ACL) ==="
# nginx(www-data)가 프로젝트 static/uploads 폴더에 접근할 수 있도록 권한 설정
apt install -y acl || true
setfacl -R -m u:www-data:rx "${PROJECT_DIR}/static" || true
setfacl -R -m u:www-data:rx "${PROJECT_DIR}/uploads" || true
setfacl -R -m d:u:www-data:rx "${PROJECT_DIR}/uploads" || true

echo ""
echo "=== 완료! 검증 중... ==="
sleep 2
curl -s -o /dev/null -w "https://${DOMAIN}/ → HTTP %{http_code} (%{time_total}s)\n" "https://${DOMAIN}/"

echo ""
echo "✅ ${DOMAIN} 설정 완료!"
