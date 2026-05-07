#!/bin/bash
set -e

APP_DIR="/opt/moex-bond-platform"
DB_NAME="moex_bonds"
DB_USER="moex"
DB_PASS="moex123"

echo "=== MOEX Bond Platform — VPS Setup ==="

apt-get update
apt-get install -y python3.12 python3.12-venv python3-pip python3.12-dev \
    postgresql postgresql-contrib nginx git curl unzip

systemctl enable postgresql
systemctl start postgresql

sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASS}';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};" 2>/dev/null || true
sudo -u postgres psql -d ${DB_NAME} -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;" 2>/dev/null || true

sudo -u postgres psql -d ${DB_NAME} -f ${APP_DIR}/schema.sql

mkdir -p ${APP_DIR}
cd ${APP_DIR}

python3.12 -m venv /opt/moex-bond-platform/venv
source /opt/moex-bond-platform/venv/bin/activate
pip install --upgrade pip
pip install -r ${APP_DIR}/requirements.txt

if [ -f "/tmp/12_02_2026.xlsx" ]; then
    echo "Importing initial Excel data..."
    python3.12 ${APP_DIR}/data_collector.py /tmp/12_02_2026.xlsx
fi

cat > /etc/systemd/system/moex-bond-screener.service << 'EOF'
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
EOF

systemctl daemon-reload
systemctl enable moex-bond-screener
systemctl start moex-bond-screener

cat > /etc/nginx/sites-available/moex-bond-screener << 'EOF'
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

    location /_stcore/streamlit_wsgi/v1/media {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    client_max_body_size 50M;
}
EOF

ln -sf /etc/nginx/sites-available/moex-bond-screener /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

(crontab -l 2>/dev/null; echo "0 2 * * * /opt/moex-bond-platform/venv/bin/python3.12 /opt/moex-bond-platform/data_collector.py >> /var/log/moex-collector.log 2>&1") | crontab -

echo ""
echo "=== Setup Complete ==="
echo "App: http://YOUR_SERVER_IP/"
echo "Direct Streamlit: http://YOUR_SERVER_IP:8501/"
echo ""
echo "Useful commands:"
echo "  systemctl status moex-bond-screener"
echo "  journalctl -u moex-bond-screener -f"
echo "  tail -f /var/log/moex-collector.log"
