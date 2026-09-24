# Fantasy lineup checker

Read-only checker for two leagues: TAG Fantasy Football (Sleeper, 12-team PPR) and The Austin Powers Premiere (ESPN). It reports what to change; you make the moves in the apps.

## Files

| File | What |
|---|---|
| `fantasy_check.py` | entry point: modes, notifications, Slack |
| `core.py` | shared model, lineup optimizer, report sections |
| `sleeper_league.py`, `espn_league.py` | one adapter per platform |
| `nfl.py` | schedule helpers: kickoff times, game status, byes |
| `com.drew.fantasy.*.plist` | the three launchd jobs (copies live in `~/Library/LaunchAgents/`) |
| `.env` | cookies and webhook, never committed (mode 600) |

## Modes

```sh
cd ~/Desktop/Home/fantasy-bot
.venv/bin/python fantasy_check.py                  # check (default)
.venv/bin/python fantasy_check.py --mode waivers
.venv/bin/python fantasy_check.py --mode recap
.venv/bin/python fantasy_check.py --leagues espn   # one league only
.venv/bin/python fantasy_check.py --week 4
```

Add `--notify` for a macOS banner and `--slack` to post the report to Slack.

**check** (Wed 8 AM, Thu 4 PM, Sun 10 AM, Sun 11:30 AM, Sun 6:30 PM)
1. Starters who are Out / IR / Doubtful / suspended, on bye, projected 0, or empty slots. Questionable starters listed to watch.
2. Optimal lineup vs what is set, if the gain is 0.5 or more. Players whose game has kicked off are locked: locked starters stay, locked bench players are not suggested.
3. Free agents beating your weakest eligible starter by 1.5 or more.
4. Opponent's projected total, record, and holes in their lineup.
5. Byes in the next two weeks and whether you'd be short at a position.
6. Across leagues: players on both rosters, and players where Sleeper and ESPN projections differ by 3 or more (K and D/ST excluded, their scoring differs).

**waivers** (Tue 8 PM, before waivers process overnight)
- Top three free agents per position by next-week projection and season average, with ESPN ownership where available. "claim" means it beats both your drop candidate and your worst player at that position by 1.5 on a blended value (60% season average, 40% next week).
- Trade ideas: your depth vs league average at QB / RB / WR / TE, and the teams whose surplus matches your need.
- Upcoming byes.

**recap** (Tue 9 AM)
- Last week's result, starters projected vs scored, points left on the bench with who should have started, biggest boom and bust, any zeros.

The check report also ends with **League moves (last 24h)**: your own adds, drops, and waiver results, plus any player another team dropped who projects at least a point better than your weakest skill-position bench player.

**watch** (every 2 hours, Thursday through Monday morning)
- Injury-status changes for your whole roster and the opponent's starters (Healthy → Questionable → Out and back), with Sleeper's injury note when there is one, and projection drops of 30% or more since the last poll, which usually means news broke. Locked players are skipped. Silent when nothing changed. State in `watch_state.json`.

**live** (every 10 minutes, all week)
- Exits silently unless a game is in progress or has just finished, so it costs nothing outside game windows.
- Sends a Telegram message only when something happened since the last poll: one of your starters or your opponent's gained 6 or more points, one of your starters' games went final (actual vs projected), or all your starters are done (result). Each message starts with the live score. Once four or fewer players remain across both sides, it also says who is left and by how much you lead or trail, and sends that whenever another of those players finishes.
- Remembers the last poll in `live_state.json`. Delete it to reset. `--force` runs it outside a game window, `--week N` replays a past week.

## Notifications

`--notify` shows a macOS banner only when there is something to act on: a starter alert, a lineup gain, a pickup, an empty slot, or a waiver claim. Recap always sends a one-line result. Failures send their own banner. Banners come from `osascript`, so they appear under **Script Editor** in System Settings > Notifications. Allow that if nothing shows.

`--telegram` sends the full report to your Telegram DM. It reuses the bot that powers the Claude Code Telegram channel (`TELEGRAM_BOT_TOKEN`, the same token as `~/.claude/channels/telegram/.env`) and your Telegram user id as `TELEGRAM_CHAT_ID`. To use a separate bot instead: create one with @BotFather, send it any message, then read your chat id from `https://api.telegram.org/bot<token>/getUpdates` and put both values in `.env`. The scheduled jobs use this flag.

`--slack` posts to an incoming webhook instead (`SLACK_WEBHOOK_URL` in `.env`). Optional; the jobs do not pass it. To make a webhook: api.slack.com/apps > Create New App > From scratch > Incoming Webhooks > Add New Webhook to Workspace, then pick the channel.

Either flag logs a warning and continues if its credentials are missing.

## Dashboard

```sh
.venv/bin/python fantasy_check.py --mode dashboard          # writes dashboard.html here
open dashboard.html
```

One self-contained page, both leagues: a banner with anything the check found, live score vs opponent with how many players are on the field, your lineup and bench with each player's weekly trend (hover for the numbers), game (kickoff time in Central and opponent, or LIVE / Final / BYE), projected and actual points, injury tags (hover for Sleeper's injury note), upcoming-bye tags, the opponent's lineup, next week's waiver targets with the drop candidate, weekly results, standings, next week's opponent, and the full check report folded under each card. Rows tint blue while that player's game is in progress. Sleeper teams show as "Team name (username)". Refreshes itself every 5 minutes. On GitHub it is rebuilt by the check and live workflows and served by GitHub Pages.

## GitHub Actions (runs with the Mac off)

The `.github/workflows/` folder mirrors the launchd jobs so nothing depends on this Mac being awake:

| Workflow | Schedule (Central) | Notes |
|---|---|---|
| `check.yml` | Wed 8 AM, Thu 4 PM, Sun 10 AM, 11:30 AM, 6:30 PM | also rebuilds and deploys the dashboard |
| `waivers.yml` | Tue 8 PM | |
| `recap.yml` | Tue 9 AM | |
| `live.yml` | every 10 min in game windows (Thu, Sun, Mon nights, Sunday afternoon) | remembers the last poll via the Actions cache; redeploys the dashboard while games are on |
| `watch.yml` | every 2 hours, Thu through Mon | status and projection changes; last poll via the Actions cache |

GitHub cron is UTC and ignores daylight saving, so each slot is scheduled at both offsets and a gate step keeps the one that lands at the right Central time. Saturday games in December and holiday games are not in the live windows; run the workflow by hand from the Actions tab if you want live updates for those.

Secrets (repo Settings > Secrets and variables > Actions): `ESPN_S2`, `SWID`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Pages: Settings > Pages > Source: GitHub Actions. When the ESPN cookie expires, update the `ESPN_S2` secret, not just `.env`.

Run anything now: Actions tab > pick the workflow > Run workflow, or `gh workflow run check.yml`.

With Actions live, the launchd jobs are redundant and can be unloaded (below). They are kept in the repo as a fallback.

## Sleep and shutdown

The jobs are user LaunchAgents. Asleep at the scheduled time: the run fires on wake, and several missed runs collapse into one. Shut down or logged out: nothing runs until the next slot. To wake the Mac before the morning runs:

```sh
sudo pmset repeat wakeorpoweron WRU 07:55:00
```

## Config

Environment variables or `.env` next to the scripts, `KEY=VALUE` per line:

- `SLEEPER_LEAGUE_ID` (default the TAG league), `SLEEPER_USERNAME` (default `drewsaenz`, matched on Sleeper display name)
- `ESPN_LEAGUE_ID` (904472), `ESPN_TEAM_ID` (25), `ESPN_SEASON` (2026)
- `ESPN_S2`, `SWID`: from a logged-in espn.com tab, DevTools > Application > Cookies > espn.com. Keep the braces on SWID and paste `espn_s2` as-is, URL-encoded. It expires roughly yearly or on logout; the log then says "ESPN refused the cookies".
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`: with `--telegram`
- `SLACK_WEBHOOK_URL`: only with `--slack`

Sleeper's 5 MB player list is cached in `~/.cache/sleeper_check/` for 24 hours. Projections come from undocumented endpoints on both platforms (`api.sleeper.app/projections/...`, ESPN via the `espn-api` package). If one breaks, that league's section shows a ❌ line and the other league still reports.

First-time setup if `.venv` is missing:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## launchd

Four jobs, one per mode, each logging to `check.log`, `waivers.log`, `recap.log`, or `live.log` in this folder (appended, one timestamp line per run that produced output). The live job uses `StartInterval` (every 600 seconds) instead of a calendar.

Change a schedule: edit the `StartCalendarInterval` entries in the plist (Weekday 0 = Sunday through 6 = Saturday, 24-hour clock), then reload it:

```sh
cp ~/Desktop/Home/fantasy-bot/com.drew.fantasy.check.plist ~/Library/LaunchAgents/
launchctl bootout gui/$(id -u)/com.drew.fantasy.check
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.drew.fantasy.check.plist
```

Run a job now:

```sh
launchctl kickstart -k gui/$(id -u)/com.drew.fantasy.check
tail -60 ~/Desktop/Home/fantasy-bot/check.log
```

Check it is loaded, or unload it:

```sh
launchctl print gui/$(id -u)/com.drew.fantasy.check | head -20
launchctl bootout gui/$(id -u)/com.drew.fantasy.check
```

Same for `com.drew.fantasy.waivers`, `com.drew.fantasy.recap`, and `com.drew.fantasy.live`.
