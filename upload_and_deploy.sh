#!/bin/bash
# ================================================================
# MOEX Bond Platform — Deploy Script
# ================================================================
# Выполните на СВОЁМ компьютере (откуда есть SSH доступ к VPS):
#   bash upload_and_deploy.sh
# ================================================================

SERVER="45.67.230.123"
USER="root"
REMOTE_DIR="/opt/moex-bond-platform"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "========================================="
echo "  MOEX Bond Platform — Upload & Deploy"
echo "========================================="
echo ""
echo "  Server:   ${USER}@${SERVER}"
echo "  Project:  ${LOCAL_DIR}"
echo ""

# 1. Create remote directory
echo "[1/4] Creating remote directory..."
ssh ${USER}@${SERVER} "mkdir -p ${REMOTE_DIR}/.streamlit" || { echo "SSH failed!"; exit 1; }

# 2. Upload project files
echo "[2/4] Uploading project files..."
scp ${LOCAL_DIR}/schema.sql ${USER}@${SERVER}:${REMOTE_DIR}/
scp ${LOCAL_DIR}/requirements.txt ${USER}@${SERVER}:${REMOTE_DIR}/
scp ${LOCAL_DIR}/data_collector.py ${USER}@${SERVER}:${REMOTE_DIR}/
scp ${LOCAL_DIR}/streamlit_app.py ${USER}@${SERVER}:${REMOTE_DIR}/
scp ${LOCAL_DIR}/.streamlit/config.toml ${USER}@${SERVER}:${REMOTE_DIR}/.streamlit/
scp ${LOCAL_DIR}/initial_data.xlsx ${USER}@${SERVER}:${REMOTE_DIR}/
scp ${LOCAL_DIR}/deploy.sh ${USER}@${SERVER}:${REMOTE_DIR}/

# 3. Run deploy on server
echo "[3/4] Running deploy script on server..."
ssh ${USER}@${SERVER} "bash ${REMOTE_DIR}/deploy.sh" || { echo "Deploy failed!"; exit 1; }

# 4. Import initial data
echo "[4/4] Importing initial Excel data..."
ssh ${USER}@${SERVER} "${REMOTE_DIR}/venv/bin/python3.12 ${REMOTE_DIR}/data_collector.py ${REMOTE_DIR}/initial_data.xlsx" || { echo "Import failed!"; exit 1; }

echo ""
echo "========================================="
echo "  ✅ DEPLOY COMPLETE!"
echo "========================================="
echo ""
echo "  Web: http://${SERVER}/"
echo "  Direct: http://${SERVER}:8501/"
