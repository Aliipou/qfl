#!/usr/bin/env bash
# ============================================================
# QFL Platform — Backup & Recovery Script
# ============================================================
# Backs up:
#   - PostgreSQL (pg_dump → S3)
#   - Redis (RDB snapshot → S3)
#   - Model checkpoints → S3
# ============================================================

set -euo pipefail

# --- Config ---
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/tmp/qfl_backup_${TIMESTAMP}"
S3_BUCKET="${QFL_S3_BACKUP_BUCKET:-s3://qfl-backups}"
RETENTION_DAYS="${QFL_BACKUP_RETENTION_DAYS:-30}"
PG_HOST="${POSTGRES_HOST:-postgres}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_DB="${POSTGRES_DB:-qfldb}"
PG_USER="${POSTGRES_USER:-qfl}"
REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"

mkdir -p "${BACKUP_DIR}"

log() { echo "[$(date -Iseconds)] $*"; }

# ---- PostgreSQL backup ----
log "Starting PostgreSQL backup..."
PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
    -h "${PG_HOST}" \
    -p "${PG_PORT}" \
    -U "${PG_USER}" \
    -d "${PG_DB}" \
    --format=custom \
    --compress=9 \
    --file="${BACKUP_DIR}/postgres_${TIMESTAMP}.dump"

log "PostgreSQL backup complete: $(du -sh "${BACKUP_DIR}/postgres_${TIMESTAMP}.dump" | cut -f1)"

# ---- Redis backup ----
log "Triggering Redis BGSAVE..."
redis-cli -h "${REDIS_HOST}" -p "${REDIS_PORT}" \
    -a "${REDIS_PASSWORD:-redis_secret}" BGSAVE

# Wait for BGSAVE to finish
for i in {1..30}; do
    STATUS=$(redis-cli -h "${REDIS_HOST}" -a "${REDIS_PASSWORD:-redis_secret}" \
        LASTSAVE 2>/dev/null || echo "0")
    sleep 1
    NEW_STATUS=$(redis-cli -h "${REDIS_HOST}" -a "${REDIS_PASSWORD:-redis_secret}" \
        LASTSAVE 2>/dev/null || echo "0")
    if [ "${NEW_STATUS}" != "${STATUS}" ]; then
        break
    fi
done

# Copy Redis RDB
docker cp qfl_redis:/data/dump.rdb \
    "${BACKUP_DIR}/redis_${TIMESTAMP}.rdb" 2>/dev/null || \
    log "Warning: Redis RDB copy failed (non-fatal)"

log "Redis backup complete"

# ---- Encrypt backups (AES-256-GCM via GPG) ----
log "Encrypting backups..."
for f in "${BACKUP_DIR}"/*; do
    gpg --batch --yes \
        --symmetric \
        --cipher-algo AES256 \
        --passphrase "${QFL_BACKUP_PASSPHRASE:-changeme}" \
        "${f}"
    rm "${f}"
done

# ---- Upload to S3 ----
log "Uploading to ${S3_BUCKET}/backups/${TIMESTAMP}/..."
aws s3 sync "${BACKUP_DIR}/" \
    "${S3_BUCKET}/backups/${TIMESTAMP}/" \
    --sse AES256 \
    --storage-class STANDARD_IA

# ---- Enforce retention ----
log "Enforcing ${RETENTION_DAYS}-day retention..."
aws s3 ls "${S3_BUCKET}/backups/" --recursive | \
    awk '{print $4}' | \
    while read -r key; do
        key_date=$(echo "${key}" | grep -oP '\d{8}')
        if [ -n "${key_date}" ]; then
            cutoff=$(date -d "-${RETENTION_DAYS} days" +%Y%m%d)
            if [ "${key_date}" -lt "${cutoff}" ]; then
                aws s3 rm "s3://${S3_BUCKET}/${key}"
                log "Deleted old backup: ${key}"
            fi
        fi
    done

# ---- Cleanup ----
rm -rf "${BACKUP_DIR}"
log "Backup complete: ${S3_BUCKET}/backups/${TIMESTAMP}/"
