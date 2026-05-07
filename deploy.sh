#!/bin/bash
# ============================================================
# MOEX Bond Platform — Ручной деплой на VPS
# ============================================================
# Запускать на сервере: bash deploy.sh
# Предварительно загрузите файлы проекта на сервер:
#   scp -r moex-bond-platform/ root@45.67.230.123:/opt/
#   scp 12_02_2026.xlsx root@45.67.230.123:/opt/moex-bond-platform/
# ============================================================

set -e

APP_DIR="/opt/moex-bond-platform"
DB_NAME="moex_bonds"
DB_USER="moex"
DB_PASS="moex123"

echo "========================================="
echo "  MOEX Bond Platform — Установка на VPS"
echo "========================================="

# 1. Системные пакеты
echo "[1/8] Установка системных пакетов..."
apt-get update -qq
apt-get install -y -qq python3.12 python3.12-venv python3.12-dev \
    postgresql postgresql-contrib nginx git curl 2>/dev/null

# 2. PostgreSQL
echo "[2/8] Настройка PostgreSQL..."
systemctl enable postgresql
systemctl start postgresql

sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1 || \
    sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';"

sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw ${DB_NAME} || \
    sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"

sudo -u postgres psql -d ${DB_NAME} -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" 2>/dev/null || true

# 3. Схема БД
echo "[3/8] Создание схемы БД..."
sudo -u postgres psql -d ${DB_NAME} -f ${APP_DIR}/schema.sql

# 4. Python venv
echo "[4/8] Создание Python-окружения..."
python3.12 -m venv ${APP_DIR}/venv
source ${APP_DIR}/venv/bin/activate
pip install --upgrade pip -q
pip install -r ${APP_DIR}/requirements.txt -q

# 5. Импорт начальных данных из Excel
echo "[5/8] Импорт данных из Excel..."
if [ -f "${APP_DIR}/initial_data.xlsx" ]; then
    python3.12 ${APP_DIR}/data_collector.py ${APP_DIR}/initial_data.xlsx
    echo "  Импорт завершён"
else
    echo "  Файл initial_data.xlsx не найден — пропускаем"
fi

# 6. Systemd service
echo "[6/8] Настройка systemd service..."
cat > /etc/systemd/system/moex-bond-screener.service << 'SVCEOF'
[Unit]
Description=MOEX Bond Screener (Streamlit)
After=network.target postgresql.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/moex-bond-platform
Environment=DATABASE_URL=postgresql://moex:moex123@localhost:5432/moex_bonds
Environment=PATH=/opt/moex-bond-platform/venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/opt/moex-bond-platform/venv/bin/streamlit run /opt/moex-bond-platform/streamlit_app.py \
    --server.port 8501 \
    --server.address 127.0.0.1 \
    --server.headless true \
    --server.enableCORS false \
    --server.enableXsrfProtection false \
    --browser.gatherUsageStats false
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable moex-bond-screener
systemctl start moex-bond-screener
echo "  Service started"

# 7. Nginx
echo "[7/8] Настройка Nginx..."
cat > /etc/nginx/sites-available/moex-bond-screener << 'NGINXEOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }

    client_max_body_size 50M;
}
NGINXEOF

ln -sf /etc/nginx/sites-available/moex-bond-screener /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx
echo "  Nginx configured"

# 8. Cron (ежедневный сбор в 02:00)
echo "[8/8] Настройка cron..."
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/moex-bond-platform/venv/bin/python3.12 /opt/moex-bond-platform/data_collector.py >> /var/log/moex-collector.log 2>&1") | crontab -

echo ""
echo "========================================="
echo "  ✅ УСТАНОВКА ЗАВЕРШЕНА"
echo "========================================="
echo ""
echo "  Веб-интерфейс: http://45.67.230.123/"
echo "  Streamlit:     http://45.67.230.123:8501/"
echo ""
echo "  Команды управления:"
echo "    systemctl status moex-bond-screener"
echo "    systemctl restart moex-bond-screener"
echo "    journalctl -u moex-bond-screener -f"
echo "    tail -f /var/log/moex-collector.log"
echo ""
echo "  SSL (Let's Encrypt):"
echo "    apt install certbot python3-certbot-nginx"
echo "    certbot --nginx -d your-domain.com"
