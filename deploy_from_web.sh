#!/bin/bash
# ================================================================
# MOEX Bond Platform — Деплой на VPS через ISPmanager
# ================================================================
# ВСТАВТЕ ЭТО В ТЕРМИНАЛ ISPmanager (https://45.67.230.123:1500)
# Или по SSH:  ssh root@45.67.230.123
# Затем:       bash deploy_from_web.sh
# ================================================================
set -e

APP="/opt/moex-bond-platform"
echo "=========================================="
echo "  MOEX Bond Platform — Auto-Deploy"
echo "=========================================="

# --- 1. System packages ---
echo "[1/8] System packages..."
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    python3.12 python3.12-venv python3.12-dev \
    postgresql postgresql-contrib nginx curl 2>/dev/null

# --- 2. PostgreSQL ---
echo "[2/8] PostgreSQL..."
systemctl enable --now postgresql

su - postgres -c "psql -tc \"SELECT 1 FROM pg_roles WHERE rolname='moex'\"" | grep -q 1 || \
    su - postgres -c "psql -c \"CREATE USER moex WITH PASSWORD 'moex123';\""

su - postgres -c "psql -lqt" | cut -d\| -f1 | grep -qw moex_bonds || \
    su - postgres -c "psql -c \"CREATE DATABASE moex_bonds OWNER moex;\""

su - postgres -c "psql -d moex_bonds -c 'CREATE EXTENSION IF NOT EXISTS pg_trgm;'" 2>/dev/null || true

# --- 3. Download project files ---
echo "[3/8] Download project..."
mkdir -p $APP/.streamlit

curl -sL "https://store1.gofile.io/download/jGU5ne/moex-project-only.tar.gz" -o /tmp/moex-project.tar.gz
tar xzf /tmp/moex-project.tar.gz -C $APP/
mv $APP/moex-bond-platform/.streamlit/config.toml $APP/.streamlit/ 2>/dev/null || true
# Files are extracted; move if nested
if [ -d "$APP/moex-bond-platform" ]; then
    cp $APP/moex-bond-platform/* $APP/ 2>/dev/null || true
    cp -r $APP/moex-bond-platform/.streamlit $APP/ 2>/dev/null || true
fi

echo "  Files downloaded and extracted"

# --- 4. Database schema ---
echo "[4/8] Database schema..."
su - postgres -c "psql -d moex_bonds -f $APP/schema.sql"

# --- 5. Download and import initial data ---
echo "[5/8] Import initial data..."
curl -sL "https://store1.gofile.io/download/PhXWe7/initial_data.xlsx" -o $APP/initial_data.xlsx

# --- 6. Python venv ---
echo "[6/8] Python environment..."
python3.12 -m venv $APP/venv
source $APP/venv/bin/activate
pip install --upgrade pip -q
pip install -r $APP/requirements.txt -q 2>&1 | tail -5

# Import Excel data into PostgreSQL
echo "  Importing Excel data into PostgreSQL..."
$APP/venv/bin/python3.12 $APP/data_collector.py $APP/initial_data.xlsx

# --- 7. Systemd ---
echo "[7/8] Systemd service..."
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
    --server.address 0.0.0.0 \
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
echo "  Service started"

# --- 8. Nginx + Firewall ---
echo "[8/8] Nginx..."
cat > /etc/nginx/sites-available/moex-bond << 'EOF'
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
EOF

ln -sf /etc/nginx/sites-available/moex-bond /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t 2>/dev/null && systemctl restart nginx

# Open firewall ports
ufw allow 80/tcp 2>/dev/null || true
ufw allow 8501/tcp 2>/dev/null || true
iptables -I INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || true
iptables -I INPUT -p tcp --dport 8501 -j ACCEPT 2>/dev/null || true

# Cron — ежедневный сбор в 02:00
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/moex-bond-platform/venv/bin/python3.12 /opt/moex-bond-platform/data_collector.py >> /var/log/moex-collector.log 2>&1") | crontab -

echo ""
echo "=========================================="
echo "  DEPLOY COMPLETE!"
echo "=========================================="
echo ""
echo "  Web:      http://45.67.230.123/"
echo "  Direct:   http://45.67.230.123:8501/"
echo ""
echo "  Check:    systemctl status moex-bond-screener"
echo "  Logs:     journalctl -u moex-bond-screener -f"
echo "  Restart:  systemctl restart moex-bond-screener"
echo ""
echo "  SSL:      apt install certbot python3-certbot-nginx && certbot --nginx -d your-domain.com"
