#!/bin/bash
# ================================================================
# МОИНИМАЛЬНЫЙ ДЕПЛОЙ — вставить в терминал ISPmanager
# ================================================================
# 1. Откройте https://45.67.230.123:1500 в браузере
# 2. Войдите: root / tC1yR9hI8z
# 3. Откройте Терминал (или SSH-консоль)
# 4. Вставьте весь этот скрипт одной строкой:
#      bash <(curl -sL https://raw.githubusercontent.com/YOUR/moex_install.sh)
#    ИЛИ скопируйте содержимое moex_install.sh и вставьте в терминал
# ================================================================

set -e

APP="/opt/moex-bond-platform"
mkdir -p $APP/.streamlit

echo "=== [1/7] System packages ==="
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3.12 python3.12-venv python3.12-dev postgresql postgresql-contrib nginx git curl

echo "=== [2/7] PostgreSQL ==="
systemctl enable --now postgresql
su - postgres -c "psql -c \"SELECT 1 FROM pg_roles WHERE rolname='moex'\"" | grep -q 1 || su - postgres -c "psql -c \"CREATE USER moex WITH PASSWORD 'moex123';\""
su - postgres -c "psql -lqt" | cut -d\| -f1 | grep -qw moex_bonds || su - postgres -c "psql -c \"CREATE DATABASE moex_bonds OWNER moex;\""
su - postgres -c "psql -d moex_bonds -c 'CREATE EXTENSION IF NOT EXISTS pg_trgm;'" 2>/dev/null || true

echo "=== [3/7] Write files ==="
