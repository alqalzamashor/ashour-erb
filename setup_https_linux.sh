#!/usr/bin/env bash
# تجهيز HTTPS للبوابة على Ubuntu/Debian:  sudo ./setup_https_linux.sh erp.example.com you@mail.com
# قبلها: سجّل في الـ DNS سجلّين A لنفس IP السيرفر:  erp.example.com  و  *.erp.example.com
# وافتح بورتات 80 و 443 بس (بورتات الشركات 9100+ بتبقى داخلية).
set -e
DOMAIN="$1"; EMAIL="$2"
[ -z "$DOMAIN" ] && { echo "الاستخدام: sudo $0 الدومين [الإيميل]"; exit 1; }
DIR="$(cd "$(dirname "$0")" && pwd)"
if ! command -v caddy >/dev/null; then
  apt-get update && apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update && apt-get install -y caddy
fi
mkdir -p /etc/erp
cat > /etc/erp/portal.env <<ENV
ERP_PUBLIC_DOMAIN=$DOMAIN
ERP_ACME_EMAIL=$EMAIL
ERP_CADDYFILE=/etc/caddy/Caddyfile
ERP_CADDY_RELOAD=1
ENV
echo "تم. شغّل البوابة بالمتغيرات دي:  set -a; . /etc/erp/portal.env; set +a; $DIR/start_portal_linux.sh"
echo "البوابة هتكتب /etc/caddy/Caddyfile وتعمل reload لـ Caddy تلقائيًا مع كل شركة جديدة. لازم تشغّلها بصلاحية تكتب فيه (root أو chown)."
