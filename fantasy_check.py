#!/usr/bin/env python3
"""
Fantasy lineup checker for the Sleeper and ESPN leagues. Read-only: it tells you what to change.

Modes:
  check     (default) starters with problems, optimal lineup vs set (kickoff-locked players respected),
            this week's free agents, opponent, byes in the next 2 weeks, cross-league exposure and
            Sleeper-vs-ESPN projection disagreements
  waivers   waiver targets for next week ranked against your drop candidate, plus trade ideas and byes
  recap     last week: result, starters vs projection, points left on the bench, boom and bust
  live      during games: big plays (+6 or more since the last poll) by your starters or your opponent's,
            your starters' finals vs projection, and the result once your week is done. Silent otherwise.
  dashboard writes a self-contained HTML page (both leagues: lineups with live points, opponent, results,
            standings, full check report) to --out
  watch     injury-status changes and projection drops of 30%+ for your roster and the opponent's starters
            since the last poll. Silent otherwise. Meant to run every couple of hours Thu-Sun.

Usage:
  python fantasy_check.py                       # check, both leagues
  python fantasy_check.py --mode waivers
  python fantasy_check.py --mode recap
  python fantasy_check.py --mode live           # meant to run every 10 minutes from launchd
  python fantasy_check.py --leagues sleeper     # one league
  python fantasy_check.py --week 4
  python fantasy_check.py --notify              # macOS notification when there's something to act on
  python fantasy_check.py --telegram            # also send the report to your Telegram DM
  python fantasy_check.py --slack               # also post the report to SLACK_WEBHOOK_URL

Config via env vars or a .env file next to this script:
  SLEEPER_LEAGUE_ID, SLEEPER_USERNAME, ESPN_LEAGUE_ID, ESPN_TEAM_ID, ESPN_SEASON, ESPN_S2, SWID,
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SLACK_WEBHOOK_URL
"""
import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

import requests

import core
from core import plural

HERE = Path(__file__).resolve().parent


def load_dotenv(path=HERE / ".env"):
    """Minimal KEY=VALUE loader; real environment wins over the file."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def notify(title, message):
    """macOS notification via osascript. Shows under 'Script Editor' in System Settings > Notifications."""
    def q(s):
        return s.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run(["osascript", "-e", f'display notification "{q(message)}" with title "{q(title)}"'],
                   check=False, timeout=15)


def post_slack(text):
    hook = os.environ.get("SLACK_WEBHOOK_URL")
    if not hook:
        print("warning: --slack set but SLACK_WEBHOOK_URL is missing; skipped", file=sys.stderr)
        return
    # Slack caps a single message around 40k chars; split on section breaks if needed
    chunks, cur = [], ""
    for para in text.split("\n\n"):
        if len(cur) + len(para) > 3500 and cur:
            chunks.append(cur)
            cur = ""
        cur = f"{cur}\n\n{para}" if cur else para
    chunks.append(cur)
    for c in chunks:
        requests.post(hook, json={"text": c}, timeout=15).raise_for_status()


def post_telegram(text):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print("warning: --telegram set but TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing; skipped", file=sys.stderr)
        return
    # Telegram HTML mode: escape, then turn the report's *bold* headers into <b>
    import html
    import re
    body = re.sub(r"\*(.+?)\*", r"<b>\1</b>", html.escape(text, quote=False))
    chunks, cur = [], ""
    for para in body.split("\n\n"):
        if len(cur) + len(para) > 3800 and cur:  # Telegram caps a message at 4096 chars
            chunks.append(cur)
            cur = ""
        cur = f"{cur}\n\n{para}" if cur else para
    chunks.append(cur)
    for c in chunks:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": c, "parse_mode": "HTML",
                                "disable_web_page_preview": True}, timeout=15)
        r.raise_for_status()


def live_gate(state):
    """Cheap check before loading leagues: is any game in progress, or finished since the last poll?"""
    import nfl
    st = requests.get("https://api.sleeper.app/v1/state/nfl", timeout=30).json()
    week = st.get("display_week") or st.get("week")
    statuses = {t: g["status"] for t, g in nfl.sleeper_schedule(st["season"]).get(week, {}).items()}
    in_progress = any(s not in ("pre_game", "complete") for s in statuses.values())
    complete = {t for t, s in statuses.items() if s == "complete"}
    new_finals = complete - set(state.get("final_teams", []))
    return (in_progress or bool(new_finals)), week, complete


def load_state(path, week):
    try:
        state = json.loads(path.read_text())
    except (OSError, ValueError):
        state = {}
    if week is not None and state.get("week") != week:
        state = {"week": week}
    return state


def load(name, mode, week):
    if name == "sleeper":
        import sleeper_league as mod
    elif name == "espn":
        import espn_league as mod
    else:
        raise SystemExit(f"unknown league '{name}'")
    return mod.build(mode=mode, week=week)


def main():
    load_dotenv()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["check", "waivers", "recap", "live", "dashboard", "watch"], default="check")
    ap.add_argument("--out", default=str(HERE / "dashboard.html"), help="dashboard mode: output HTML path")
    ap.add_argument("--leagues", default="espn,sleeper", help="comma list, in report order: espn,sleeper")
    ap.add_argument("--week", type=int, help="NFL week (default: current)")
    ap.add_argument("--state", default=None, help="live/watch mode: where to remember the last poll (default live_state.json / watch_state.json)")
    ap.add_argument("--force", action="store_true", help="live mode: run even when no game is in progress")
    ap.add_argument("--notify", action="store_true", help="macOS notification when there's something to act on")
    ap.add_argument("--telegram", action="store_true", help="send report via TELEGRAM_BOT_TOKEN to TELEGRAM_CHAT_ID")
    ap.add_argument("--slack", action="store_true", help="post report to SLACK_WEBHOOK_URL")
    args = ap.parse_args()

    state_path = Path(args.state) if args.state else HERE / ("watch_state.json" if args.mode == "watch" else "live_state.json")
    state, complete = None, set()
    if args.mode == "watch":
        state = load_state(state_path, None)  # re-keyed to the week once we know it
    if args.mode == "live":
        try:
            prior = load_state(state_path, None)
            active, week, complete = live_gate(prior)
        except Exception as e:  # noqa: BLE001
            print(f"warning: live gate failed, running anyway: {e}", file=sys.stderr)
            active, week = True, args.week
        week = args.week or week
        state = load_state(state_path, week)
        if not active and not args.force:
            return  # nothing happening; stay quiet
        args.week = week

    snaps, lines, issues, failures, recaps = [], [], {}, [], []
    for name in [n.strip() for n in args.leagues.split(",") if n.strip()]:
        try:
            snaps.append(load(name, "check" if args.mode == "watch" else args.mode, args.week))
        except Exception as e:  # noqa: BLE001
            failures.append(f"{name}: {type(e).__name__}: {e}")
            traceback.print_exc()

    # Sleeper's schedule has dates but no kickoff times; borrow ESPN's if we have them
    kick = next((s.kickoffs for s in snaps if s.kickoffs), {})
    status = next((s.game_status for s in snaps if s.game_status), {})
    games = next((s.games for s in snaps if s.games), {})
    for snap in snaps:
        if not snap.kickoffs and kick:
            snap.kickoffs = kick
        if not snap.game_status and status:  # ESPN has no game-complete signal; Sleeper's schedule does
            snap.game_status = status
        if not snap.games and games:
            snap.games = games

    if args.mode == "dashboard":
        import dashboard
        reports = {s.key: core.report_check(s) for s in snaps}  # (lines, issues)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(dashboard.render(snaps, reports, failures))
        print(f"{time.strftime('%Y-%m-%d %H:%M')} mode=dashboard wrote {out} failures={len(failures)}", file=sys.stderr)
        for f in failures:
            print(f"❌ {f}", file=sys.stderr)
        sys.exit(1 if failures and not snaps else 0)

    if args.mode == "watch" and snaps:
        wk = snaps[0].week
        if state.get("week") != wk:
            state = {"week": wk}

    for snap in snaps:
        if args.mode == "live":
            l, n, state[snap.key] = core.section_live(snap, state.get(snap.key, {}))
            i = [f"{n} updates"] if n else []
        elif args.mode == "watch":
            l, n, state[snap.key] = core.section_watch(snap, state.get(snap.key, {}))
            i = [plural(n, "status change")] if n else []
        elif args.mode == "check":
            l, i = core.report_check(snap)
        elif args.mode == "waivers":
            l, i = core.section_waivers(snap)
            l += core.section_trades(snap)
            l += core.section_byes(snap)
        else:
            l, summary = core.section_recap(snap)
            i = []
            if summary:
                recaps.append(f"{snap.key} {summary}")
        lines += l
        if i:
            issues[snap.key] = i
        for w in snap.warnings:
            lines.append(f"⚠️ {w}")
    if args.mode == "check":
        lines += core.section_exposure(snaps)
        lines += core.section_projection_gaps(snaps)
    for f in failures:
        lines.append(f"❌ {f}")

    if args.mode == "live":
        state["final_teams"] = sorted(complete | set(state.get("final_teams", [])))
    if args.mode in ("live", "watch"):
        state_path.write_text(json.dumps(state))
        if not any(l.strip() for l in lines):
            return  # polled, nothing new

    report = "\n".join(lines).rstrip() + "\n"
    stamp = time.strftime("%Y-%m-%d %H:%M")
    n_issues = sum(len(v) for v in issues.values())
    print(f"{stamp} mode={args.mode} issues={n_issues} failures={len(failures)}", file=sys.stderr)
    print(report)

    if args.notify:
        title = {"check": "Fantasy check", "waivers": "Waiver targets", "recap": "Weekly recap", "live": "Live", "watch": "Status change"}[args.mode]
        if issues:
            body = "; ".join(f"{k}: {', '.join(v)}" for k, v in issues.items())
            notify(title, f"{body}. Run fantasy_check.py --mode {args.mode}")
        elif args.mode == "recap" and recaps:
            notify(title, ", ".join(recaps))
        if failures:
            notify(f"{title} failed", failures[0][:200])

    for flag, fn, label in ((args.telegram, post_telegram, "Telegram"), (args.slack, post_slack, "Slack")):
        if flag:
            try:
                fn(report)
            except requests.RequestException as e:
                print(f"warning: {label} post failed: {e}", file=sys.stderr)
                if args.notify:
                    notify(f"{label} post failed", str(e)[:200])
    sys.exit(1 if failures and not snaps else 0)


if __name__ == "__main__":
    main()
