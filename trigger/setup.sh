#!/usr/bin/env bash
# One-time wiring, run after `npx wrangler deploy` has printed the Worker's URL:
#   1. push the four secrets in .dev.vars into the Worker
#   2. point the Telegram bot's webhook at the Worker, with a shared secret the Worker checks
#   3. register the slash-command menu Telegram shows when you type "/"
# Usage: ./setup.sh https://fantasy-trigger.<subdomain>.workers.dev
set -euo pipefail
cd "$(dirname "$0")"
worker=${1:?usage: setup.sh <worker url>}
[ -f .dev.vars ] || { echo ".dev.vars is missing; see README" >&2; exit 1; }

while IFS='=' read -r k v; do
  [[ -z "$k" || "$k" == \#* ]] && continue
  v=${v%\"}; v=${v#\"}
  [[ "$v" == *PASTE* || -z "$v" ]] && { echo "$k still has a placeholder in .dev.vars" >&2; exit 1; }
  printf '%s' "$v" | npx wrangler secret put "$k" >/dev/null && echo "secret $k set"
  declare "$k=$v"
done < .dev.vars

api="https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN"
curl -sS "$api/setWebhook" \
  --data-urlencode "url=$worker/telegram" \
  --data-urlencode "secret_token=$TELEGRAM_WEBHOOK_SECRET" \
  --data-urlencode 'allowed_updates=["message"]' \
  --data-urlencode "drop_pending_updates=true"; echo
curl -sS "$api/setMyCommands" --data-urlencode 'commands=[
  {"command":"check","description":"Lineup check now"},
  {"command":"waivers","description":"Waiver targets and trade ideas"},
  {"command":"recap","description":"Last week in review"},
  {"command":"live","description":"Score update (during games)"},
  {"command":"watch","description":"Injury and projection changes"},
  {"command":"status","description":"Last run of each job"},
  {"command":"dashboard","description":"Dashboard link"}]'; echo
curl -sS "$api/getWebhookInfo"; echo
