#!/bin/bash
# Дневной цикл ВЭД-канала. Ставится в cron.
#
#   ~/dayfacto/daily.sh posts     - собрать и отправить посты
#   ~/dayfacto/daily.sh reminders - напоминания о дедлайнах
#   ~/dayfacto/daily.sh digest    - дайджест недели (по понедельникам)
#
# Логи: ~/dayfacto/logs/daily.log

set -u
cd "$(dirname "$0")" || exit 1

MODE="${1:-posts}"
MOUNT="-v $(pwd)/outbox:/app/outbox"
LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/daily.log"

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

# --- защита от параллельных запусков ---------------------------------
exec 9>"$LOG_DIR/.lock"
if ! flock -n 9; then
    log "$MODE: пропуск, предыдущий запуск ещё идёт"
    exit 0
fi

log "=== $MODE: старт"

# Синхронизация с репозиторием: Actions мог очистить очередь
git pull --rebase --autostash -q 2>>"$LOG" || {
    log "git pull не прошёл, продолжаю на локальной версии"
}

case "$MODE" in
  posts)
    docker compose run --rm $MOUNT ingestion \
        python tools/build_outbox.py --limit 30 --max-posts 3 2>&1 | tee -a "$LOG"
    docker compose run --rm $MOUNT ingestion python tools/publish_outbox.py 2>&1 | tee -a "$LOG"
    ;;
  reminders)
    docker compose run --rm $MOUNT ingestion \
        python tools/build_reminders.py 2>&1 | tee -a "$LOG"
    ;;
  digest)
    docker compose run --rm $MOUNT ingestion \
        python tools/build_reminders.py --digest 2>&1 | tee -a "$LOG"
    ;;
  *)
    log "неизвестный режим: $MODE"
    exit 1
    ;;
esac

# --- отправка, если в очереди что-то есть ----------------------------
QUEUE="outbox/pending.json"
if [ ! -s "$QUEUE" ] || [ "$(tr -d '[:space:]' < "$QUEUE")" = "[]" ]; then
    log "$MODE: очередь пуста, публиковать нечего"
    exit 0
fi

COUNT=$(python3 -c "import json;print(len(json.load(open('$QUEUE'))))" 2>/dev/null || echo "?")

git add "$QUEUE" 2>>"$LOG"
if git diff --cached --quiet; then
    log "$MODE: изменений в очереди нет"
    exit 0
fi

git commit -q -m "outbox: $MODE $(date '+%d.%m %H:%M')" 2>>"$LOG"
if git push -q 2>>"$LOG"; then
    log "$MODE: отправлено в публикацию, постов в очереди: $COUNT"
else
    log "$MODE: ОШИБКА push — проверь токен в git remote"
    exit 1
fi
