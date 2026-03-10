#!/usr/bin/env bash
# ============================================================
# QFL Platform — Point-in-Time Recovery Script
# ============================================================

set -euo pipefail

BACKUP_TIMESTAMP="${1:-}"
S3_BUCKET="${QFL_S3_BACKUP_BUCKET:-s3://qfl-backups}"
RESTORE_DIR="/tmp/qfl_restore_${BACKUP_TIMESTAMP}"
PG_HOST="${POSTGRES_HOST:-postgres}"
PG_USER="${POSTGRES_USER:-qfl}"
PG_DB="${POSTGRES_DB:-qfldb}"

if [ -z "${BACKUP_TIMESTAMP}" ]; then
    echo "Usage: $0 <BACKUP_TIMESTAMP (YYYYMMDD_HHMMSS)>"
    exit 1
fi

log() { echo "[$(date -Iseconds)] $*"; }

mkdir -p "${RESTORE_DIR}"

log "Downloading backup: ${S3_BUCKET}/backups/${BACKUP_TIMESTAMP}/"
aws s3 sync \
    "${S3_BUCKET}/backups/${BACKUP_TIMESTAMP}/" \
    "${RESTORE_DIR}/"

log "Decrypting backups..."
for f in "${RESTORE_DIR}"/*.gpg; do
    gpg --batch --yes \
        --passphrase "${QFL_BACKUP_PASSPHRASE:-changeme}" \
        --output "${f%.gpg}" \
        --decrypt "${f}"
    rm "${f}"
done

# ---- Restore PostgreSQL ----
DUMP="${RESTORE_DIR}/postgres_${BACKUP_TIMESTAMP}.dump"
if [ -f "${DUMP}" ]; then
    log "Restoring PostgreSQL from ${DUMP}..."
    PGPASSWORD="${POSTGRES_PASSWORD}" pg_restore \
        -h "${PG_HOST}" \
        -U "${PG_USER}" \
        -d "${PG_DB}" \
        --clean \
        --if-exists \
        --no-owner \
        "${DUMP}"
    log "PostgreSQL restored successfully"
fi

rm -rf "${RESTORE_DIR}"
log "Restore complete"
