# Fantasy lineup checker: build brief

## Goal
A local Python tool on my Mac that checks my Sleeper fantasy football lineup a few times a week and tells me what to change. Sleeper's API is read-only, so the tool only reports; I make the changes in the app myself.

## League
- Platform: Sleeper, 12-team PPR
- League ID: `1397700718688804864`
- My username: `drewsaenz`

## Starting point
`sleeper_check.py` is already in this folder. It works against mock data but hasn't been run against the live API yet. Each run it reports:
1. Starters who are Out / IR / Doubtful / suspended, projected 0 (probably a bye), or empty slots, plus Questionable starters to watch
2. The highest-projected lineup vs. what's currently set, with the point difference
3. Free agents who beat my weakest eligible starter by at least 1.5 points
4. My opponent's projected total and any empty or injured slots on their side

APIs it uses:
- Official, documented at docs.sleeper.app: `https://api.sleeper.app/v1/...` (state, league, users, rosters, matchups, players)
- Undocumented: projections at `https://api.sleeper.app/projections/nfl/{season}/{week}?season_type=regular&position[]=QB`. This is the most likely part to break.

## Tasks
1. **Set up the project.** Create `.venv`, a `requirements.txt` containing `requests`, and a `.gitignore` covering `.venv/`, `__pycache__/`, `.env`, and `*.log`. No GitHub; everything runs locally.
2. **Run it live and fix what breaks.** Run `python sleeper_check.py`. Specifically verify:
   - my user is found (it matches on `display_name`)
   - the projections endpoint still returns data in the expected shape (`player_id`, `stats.pts_ppr`)
   - `state/nfl` returns the right week; if `week` is off early in the week, try `display_week`
   - the output makes sense against my actual roster
3. **Add a `--notify` flag** that shows a macOS notification via `osascript` when there's something to fix (an alert, a lineup change, or a free-agent pickup). Keep it short, e.g. "3 lineup issues. Run sleeper_check.py". Keep the existing `--slack` flag, but treat it as optional.
4. **Schedule it with launchd, not cron**, so a run missed while the Mac is asleep still happens on wake.
   - Plist: `~/Library/LaunchAgents/com.drew.sleepercheck.plist`
   - Run the venv's Python with absolute paths, using `--notify`
   - Schedule (local time): Wednesday 8:00 AM (after waivers), Thursday 4:00 PM (before Thursday Night Football locks), Sunday 10:00 AM (final injury check)
   - Log stdout and stderr to `~/fantasy-bot/last_run.log`
   - Load it with `launchctl bootstrap gui/$(id -u) ...`, test with `launchctl kickstart`, and show me the log
5. **Write a short README** covering how to run it manually, how to change the schedule, and how to unload the job.

## Constraints
- Keep it to one script plus the plist; no frameworks.
- Cache `/players/nfl` for 24 hours (it's about 5MB, and Sleeper asks that it be fetched at most once a day). The script already does this.
- No secrets in code. If a Slack webhook is used, it goes in the plist's EnvironmentVariables or a `.env` file.

## Later (not now)
- Add my ESPN league (leagueId `904472`, teamId `25`, season 2026) via the `espn-api` Python package. It needs the `espn_s2` and `SWID` cookies from my browser, stored in `.env`.
- Detect games that have already kicked off, so the tool doesn't suggest swapping a locked player.
