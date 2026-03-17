#!/bin/bash

# Синхронизация футболок из Яндекс.Диска через rclone (WebDAV напрямую).
# На этом сервере rsync по davfs2-монту зависает на листинге; rclone отрабатывает за ~3 мин.

TARGET_DIR="/root/photomaker/data/shirts/original/"
LOG_FILE="/root/photomaker/logs/sync_yadisk_rsync.log"
LOCK_FILE="/root/photomaker/data/sync_state/yadisk_rsync.lock"
RCLONE_REMOTE="yadisk:_Футболки Грязь/_Наложение/"

touch "$LOG_FILE"
mkdir -p "$(dirname "$LOCK_FILE")"

exec 9>>"$LOCK_FILE"
if ! flock -n 9; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Пропуск: предыдущая синхронизация ещё выполняется" >> "$LOG_FILE"
    exit 0
fi

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

log "=== Начало синхронизации (rclone) ==="

if [ ! -d "$TARGET_DIR" ]; then
    log "Создание целевой директории: $TARGET_DIR"
    mkdir -p "$TARGET_DIR"
fi

log "Выполнение rclone sync..."
rclone sync "$RCLONE_REMOTE" "$TARGET_DIR" --transfers 8 --checkers 8 >> "$LOG_FILE" 2>&1
RCLONE_EXIT=$?

if [ $RCLONE_EXIT -eq 0 ]; then
    log "Синхронизация успешно завершена"
else
    log "ОШИБКА: rclone завершился с кодом $RCLONE_EXIT"
fi

log "=== Конец синхронизации ==="
tail -n 1000 "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"

exit $RCLONE_EXIT
