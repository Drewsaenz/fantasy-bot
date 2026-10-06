#!/usr/bin/env bash
# Post a one-line failure notice to Telegram. The workflows call this with `if: failure()` so a red run
# is not silent: the jobs are the only thing watching, and from the phone a run that died before its
# report posted looks exactly like a quiet day.
set -euo pipefail
what=${1:-job}
url="${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-}/actions/runs/${GITHUB_RUN_ID:-}"
curl -sS --fail-with-body -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
  --data-urlencode "chat_id=$TELEGRAM_CHAT_ID" \
  --data-urlencode "disable_web_page_preview=true" \
  --data-urlencode "text=❌ The $what run failed before it could report. Log: $url"
