#!/usr/bin/env python3
"""
Waiver claim results, as soon as they process. Polled every 10 minutes overnight by the Cloudflare
trigger (claims.yml); silent until one of your claims has gone through or failed, then one Telegram
message per claim, never repeated.

ESPN: the league's transaction log (view mTransactions2) keeps every waiver claim with its outcome,
EXECUTED or FAILED_<reason>, and the processDate ESPN ran it at (2:00 Central for the Tuesday-night
batch). Sleeper: transactions/{week} lists waiver claims as complete or failed.

  python claims.py                 # print what's new
  python claims.py --telegram      # and send it
  python claims.py --hours 48      # look further back (default 8 h), e.g. to test against old claims
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fantasy_check import load_dotenv, post_telegram  # noqa: E402

FAIL_REASON = {
    "FAILED_INVALIDPLAYERSOURCE": "someone else got him first",
    "FAILED_PLAYERALREADYDROPPED": "the player you were dropping was already gone",
    "FAILED_ROSTERLIMIT": "your roster was full",
    "FAILED_INVALIDPLAYERDROPPED": "the drop wasn't allowed",
    "FAILED_AUCTIONBUDGETEXCEEDED": "not enough budget",
}


def espn_results(since_ms):
    from espn_api.football import League
    league = League(league_id=int(os.environ.get("ESPN_LEAGUE_ID", "904472")),
                    year=int(os.environ.get("ESPN_SEASON", "2026")),
                    espn_s2=os.environ.get("ESPN_S2") or None, swid=os.environ.get("SWID") or None)
    me = int(os.environ.get("ESPN_TEAM_ID", "25"))
    teams = {t.team_id: t.team_name for t in league.teams}
    sp = league.scoringPeriodId
    txs = []
    for period in {sp - 1, sp}:
        d = league.espn_request.league_get(params={"view": "mTransactions2", "scoringPeriodId": period})
        txs += d.get("transactions") or []

    winner = {}  # playerId -> team that claimed him
    for t in txs:
        if t.get("type") == "WAIVER" and t.get("status") == "EXECUTED":
            for it in t.get("items") or []:
                if it.get("type") == "ADD":
                    winner[it["playerId"]] = t.get("teamId")

    mine = [t for t in txs if t.get("type") == "WAIVER" and t.get("teamId") == me
            and t.get("status") not in ("PENDING", None)
            and (t.get("processDate") or t.get("proposedDate") or 0) >= since_ms]
    if not mine:
        return []
    ids = sorted({it["playerId"] for t in mine for it in t.get("items") or []})
    names = {}
    for pid in ids:
        names[pid] = league.player_map.get(pid) if isinstance(league.player_map.get(pid), str) else None
    try:
        info = league.player_info(playerId=[i for i in ids if i > 0]) or []
        for p in info if isinstance(info, list) else [info]:
            names[p.playerId] = f"{p.name} ({p.position}, {p.proTeam})"
    except Exception as e:  # noqa: BLE001
        print(f"warning: ESPN player names failed: {e}", file=sys.stderr)

    out = []
    for t in sorted(mine, key=lambda t: t.get("processDate") or 0):
        add = [it["playerId"] for it in t.get("items") or [] if it.get("type") == "ADD"]
        drop = [it["playerId"] for it in t.get("items") or [] if it.get("type") == "DROP"]
        nm = lambda pid: names.get(pid) or str(pid)  # noqa: E731
        who = ", ".join(nm(p) for p in add)
        if t["status"] == "EXECUTED":
            line = f"✅ Got {who}" + (f", dropped {', '.join(nm(p) for p in drop)}" if drop else "") + ". He's on your bench"
        else:
            other = next((winner[p] for p in add if winner.get(p) not in (None, me)), None)
            why = f"{teams.get(other, 'another team')} got him" if other else FAIL_REASON.get(t["status"], t["status"].lower())
            line = f"❌ Missed {who}: {why}"
        out.append((f"espn:{t['id']}", line))
    return out


def sleeper_results(since_ms):
    base = "https://api.sleeper.app/v1"
    league_id = os.environ.get("SLEEPER_LEAGUE_ID", "1397700718688804864")
    username = os.environ.get("SLEEPER_USERNAME", "drewsaenz").lower()
    get = lambda u: requests.get(f"{base}{u}", timeout=30).json()  # noqa: E731
    state = get("/state/nfl")
    users = get(f"/league/{league_id}/users")
    me_user = next(u for u in users if (u.get("display_name") or "").lower() == username)
    rosters = get(f"/league/{league_id}/rosters")
    me = next(r["roster_id"] for r in rosters if r.get("owner_id") == me_user["user_id"])
    owner = {r["roster_id"]: next((u.get("display_name") for u in users if u["user_id"] == r.get("owner_id")), f"roster {r['roster_id']}")
             for r in rosters}
    week = state.get("week") or 1
    txs = []
    for w in {max(1, week - 1), week}:
        txs += get(f"/league/{league_id}/transactions/{w}") or []
    mine = [t for t in txs if t.get("type") == "waiver" and me in (t.get("roster_ids") or [])
            and t.get("status") in ("complete", "failed") and (t.get("status_updated") or 0) >= since_ms]
    if not mine:
        return []
    import sleeper_league
    db = sleeper_league.load_players()
    nm = lambda pid: (lambda p: f"{p.get('full_name') or pid} ({p.get('position')}, {p.get('team')})")(db.get(pid, {}))  # noqa: E731
    winner = {pid: rid for t in txs if t.get("type") == "waiver" and t.get("status") == "complete"
              for pid, rid in (t.get("adds") or {}).items()}
    out = []
    for t in mine:
        add = list((t.get("adds") or {}).keys())
        drop = list((t.get("drops") or {}).keys())
        who = ", ".join(nm(p) for p in add)
        if t["status"] == "complete":
            line = f"✅ Got {who}" + (f", dropped {', '.join(nm(p) for p in drop)}" if drop else "")
        else:
            other = next((winner[p] for p in add if winner.get(p) not in (None, me)), None)
            why = f"{owner.get(other)} got him" if other else ((t.get("metadata") or {}).get("notes") or "failed")
            line = f"❌ Missed {who}: {why}"
        out.append((f"sleeper:{t['transaction_id']}", line))
    return out


def main():
    load_dotenv()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hours", type=float, default=8, help="only claims processed in the last N hours")
    ap.add_argument("--state", default=str(HERE / "claims_state.json"))
    ap.add_argument("--telegram", action="store_true")
    args = ap.parse_args()

    path = Path(args.state)
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        saved = {}
    reported, warned = saved.get("reported", []), saved.get("warned", {})
    since = int((time.time() - args.hours * 3600) * 1000)
    night = datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d")

    sections, failures = [], []
    for label, fn in (("ESPN", espn_results), ("Sleeper", sleeper_results)):
        try:
            new = [(k, line) for k, line in fn(since) if k not in reported]
        except Exception as e:  # noqa: BLE001
            failures.append((label, f"{type(e).__name__}: {e}"))
            continue
        if new:
            sections.append((label, new))

    stamp = time.strftime("%Y-%m-%d %H:%M")
    print(f"{stamp} mode=claims new={sum(len(s[1]) for s in sections)} failures={len(failures)}", file=sys.stderr)
    for label, err in failures:
        print(f"warning: {label}: {err}", file=sys.stderr)

    lines = []
    for label, new in sections:
        lines.append(f"*{label}*")
        lines += [line for _, line in new]
    if lines:
        lines.insert(0, "*Waivers ran*")
    # A league that can't be read is said once per night, not on every 10-minute poll; the run itself
    # stays green so the workflow's failure step doesn't repeat it either.
    new_warn = [(label, err) for label, err in failures if warned.get(label) != night]
    for label, err in new_warn:
        hint = (" Your ESPN cookies (ESPN_S2 / SWID) probably expired: refresh them in the repo secrets."
                if label == "ESPN" and any(w in err for w in ("AccessDenied", "401", "403", "Unauthorized")) else "")
        lines.append(f"⚠️ Couldn't read {label} waiver results ({err[:200]}).{hint} Still checking every 10 min until 8am.")
    if not lines:
        return

    report = "\n".join(lines) + "\n"
    print(report)
    if args.telegram:
        try:
            post_telegram(report)
        except requests.RequestException as e:
            print(f"error: Telegram post failed: {e}", file=sys.stderr)
            sys.exit(1)  # state not saved, so the next poll tries again
    reported += [k for _, new in sections for k, _ in new]
    warned.update({label: night for label, _ in new_warn})
    path.write_text(json.dumps({"reported": reported[-200:], "warned": warned}))

if __name__ == "__main__":
    main()
