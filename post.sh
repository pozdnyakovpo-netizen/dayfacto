#!/bin/bash
cd ~/dayfacto || exit 1
git pull --rebase --autostash -q
docker compose run --rm -v /root/dayfacto/outbox:/app/outbox \
  ingestion python tools/build_outbox.py --limit 25 --max-posts "${1:-3}"
if [ -s outbox/pending.json ] && [ "$(cat outbox/pending.json)" != "[]" ]; then
  git add outbox/pending.json
  git commit -q -m "outbox: $(date +%d.%m)"
  git push -q && echo "отправлено в публикацию"
else
  echo "готовых постов нет"
fi
