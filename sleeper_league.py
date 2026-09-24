"""Sleeper adapter: turns the league into a core.Snapshot."""
import json
import os
import sys
import time
from pathlib import Path

import requests

from core import BYE_LOOKAHEAD, POSITIONS, Player, Snapshot, Team
from nfl import byes_from, norm_team, sleeper_schedule

BASE = "https://api.sleeper.app/v1"
PROJ_BASE = "https://api.sleeper.app/projections/nfl"  # undocumented, may change
CACHE_DIR = Path(os.environ.get("SLEEPER_CACHE_DIR", Path.home() / ".cache" / "sleeper_check"))
GAMES_PER_SEASON = 17


def get(url, params=None):
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def load_players():
    """Full NFL player DB (~5MB). Sleeper asks you to fetch it at most once a day."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / "players_nfl.json"
    if path.exists() and time.time() - path.stat().st_mtime < 86400:
        return json.loads(path.read_text())
    data = get(f"{BASE}/players/nfl")
    path.write_text(json.dumps(data))
    return data


def load_projections(season, week, key):
    """player_id -> projected points. week=None gives season totals."""
    out = {}
    url = f"{PROJ_BASE}/{season}" + (f"/{week}" if week else "")
    for pos in POSITIONS:
        try:
            rows = get(url, {"season_type": "regular", "position[]": pos})
        except requests.RequestException as e:
            print(f"warning: Sleeper projections {week or 'season'} {pos} failed: {e}", file=sys.stderr)
            continue
        for row in rows or []:
            stats = row.get("stats") or {}
            pts = stats.get(key)
            if pts is None:
                pts = stats.get("pts_ppr", stats.get("pts_half_ppr", stats.get("pts_std")))
            if pts is not None and row.get("player_id"):
                out[str(row["player_id"])] = float(pts)
    return out


def team_label(owner, roster_id):
    """'Team Name (username)' so custom team names stay recognizable; just the username when there is no team name."""
    team = (owner.get("metadata") or {}).get("team_name")
    user = owner.get("display_name")
    if team and user and team.strip().lower() != user.strip().lower():
        return f"{team} ({user})"
    return team or user or f"roster {roster_id}"


def current_week(state):
    dw, w = state.get("display_week"), state.get("week")
    if dw and w and dw != w:
        print(f"note: Sleeper state week={w} display_week={dw}; using {dw}", file=sys.stderr)
    return dw or w


def build(mode="check", week=None) -> Snapshot:
    league_id = os.environ.get("SLEEPER_LEAGUE_ID", "1397700718688804864")
    username = os.environ.get("SLEEPER_USERNAME", "drewsaenz")

    state = get(f"{BASE}/state/nfl")
    season = state["season"]
    week = week or current_week(state)

    league = get(f"{BASE}/league/{league_id}")
    rec = (league.get("scoring_settings") or {}).get("rec", 0)
    key = "pts_ppr" if rec >= 1 else "pts_half_ppr" if rec >= 0.5 else "pts_std"
    slots = [s for s in league["roster_positions"] if s not in ("BN", "IR", "TAXI")]

    users = get(f"{BASE}/league/{league_id}/users")
    users_by_id = {u["user_id"]: u for u in users}
    me_user = next((u for u in users if (u.get("display_name") or "").lower() == username.lower()), None)
    if not me_user:
        raise RuntimeError(f"Couldn't find user '{username}' in Sleeper league {league_id}")
    rosters = get(f"{BASE}/league/{league_id}/rosters")

    db = load_players()
    proj = load_projections(season, week, key)
    want_next = mode in ("waivers", "dashboard")
    proj_next = load_projections(season, week + 1, key) if want_next else {}
    proj_season = load_projections(season, None, key) if want_next else {}

    sched = sleeper_schedule(season)
    this_week = sched.get(week, {})
    game_status = {t: g["status"] for t, g in this_week.items()}
    byes = byes_from(sched, week, BYE_LOOKAHEAD)

    def mk(pid):
        pid = str(pid)
        p = db.get(pid, {})
        pos = p.get("position") or (p.get("fantasy_positions") or ["?"])[0]
        team = norm_team(p.get("team")) or "FA"
        name = p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip() or f"player {pid}"
        return Player(
            pid=pid, name=name, pos=pos, team=team,
            status=p.get("injury_status") or None,
            pts=proj.get(pid, 0.0),
            pts_next=proj_next.get(pid, 0.0),
            season_avg=proj_season.get(pid, 0.0) / GAMES_PER_SEASON,
            bye=bool(this_week) and team not in this_week and team != "FA",
            note=" ".join(x for x in (p.get("injury_body_part"), p.get("injury_notes")) if x),
        )

    players = {}
    rostered = set()
    teams, me, mine_roster = [], None, None
    for r in rosters:
        parked = set(r.get("reserve") or []) | set(r.get("taxi") or [])
        pids = [p for p in (r.get("players") or []) if p not in parked]
        rostered |= set(r.get("players") or [])
        for pid in r.get("players") or []:
            players[pid] = mk(pid)
        s = r.get("settings") or {}
        owner = users_by_id.get(r.get("owner_id"), {})
        t = Team(
            tid=str(r["roster_id"]),
            name=team_label(owner, r["roster_id"]),
            players=pids,
            starters=[(p if p and p != "0" else None) for p in (r.get("starters") or [])],
            record=f"{s.get('wins', 0)}-{s.get('losses', 0)}" + (f"-{s['ties']}" if s.get("ties") else ""),
        )
        t.starters += [None] * (len(slots) - len(t.starters))
        teams.append(t)
        if r.get("owner_id") == me_user["user_id"] or me_user["user_id"] in (r.get("co_owners") or []):
            me, mine_roster = t, r
    if not me:
        raise RuntimeError("Couldn't find your Sleeper roster")

    fa_source = proj_next if mode == "waivers" else {**proj_next, **proj} if mode == "dashboard" else proj
    free_agents = [pid for pid in fa_source if pid not in rostered]
    for pid in free_agents:
        players[pid] = mk(pid)

    snap = Snapshot(key="sleeper", name=league.get("name", "Sleeper"), week=week, slots=slots,
                    players=players, teams=teams, me=me, free_agents=free_agents,
                    kickoffs={}, game_status=game_status, byes=byes,
                    games={t: {"opp": g["opp"], "home": g.get("home"), "date": g.get("date")} for t, g in this_week.items()})

    # opponent
    try:
        matchups = get(f"{BASE}/league/{league_id}/matchups/{week}")
        my_m = next(m for m in matchups if str(m["roster_id"]) == me.tid)
        opp_m = next(m for m in matchups
                     if m.get("matchup_id") == my_m.get("matchup_id") and str(m["roster_id"]) != me.tid)
        snap.opp = next(t for t in teams if t.tid == str(opp_m["roster_id"]))
        # the matchup carries that week's lineups, which matters when --week points at a past week
        for m, t in ((my_m, me), (opp_m, snap.opp)):
            if m.get("starters"):
                t.starters = [(p if p and p != "0" else None) for p in m["starters"]]
                t.starters += [None] * (len(slots) - len(t.starters))
        # live / actual points so far this week
        for m in (my_m, opp_m):
            for pid, pts in (m.get("players_points") or {}).items():
                players.setdefault(pid, mk(pid)).actual = float(pts or 0)
    except (StopIteration, requests.RequestException):
        snap.opp = None

    if mode == "dashboard":
        for r, t in zip(rosters, teams):
            s = r.get("settings") or {}
            snap.standings.append({"name": t.name, "record": t.record,
                                   "pf": float(s.get("fpts", 0)) + float(s.get("fpts_decimal", 0)) / 100,
                                   "extra": "", "is_me": t.tid == me.tid})
        snap.standings.sort(key=lambda d: (-int(d["record"].split("-")[0]), -d["pf"]))
        try:
            ms = get(f"{BASE}/league/{league_id}/matchups/{week + 1}")
            mm = next(m for m in ms if str(m["roster_id"]) == me.tid)
            om = next((m for m in ms if m.get("matchup_id") == mm.get("matchup_id") and str(m["roster_id"]) != me.tid), None)
            ot = next((t for t in teams if om and t.tid == str(om["roster_id"])), None)
            snap.next_opp = ot.name if ot else ""
        except (StopIteration, requests.RequestException):
            pass
        weekly = {}  # pid -> {week: pts} for every player rostered by anyone that week
        for w in range(1, week):
            try:
                ms = get(f"{BASE}/league/{league_id}/matchups/{w}")
                for m in ms:
                    for pid, pts in (m.get("players_points") or {}).items():
                        weekly.setdefault(pid, {})[w] = float(pts or 0)
                mm = next(m for m in ms if str(m["roster_id"]) == me.tid)
                om = next((m for m in ms if m.get("matchup_id") == mm.get("matchup_id") and str(m["roster_id"]) != me.tid), None)
                ot = next((t for t in teams if om and t.tid == str(om["roster_id"])), None)
                snap.history.append({"week": w, "mine": float(mm.get("points") or 0),
                                     "theirs": float(om.get("points") or 0) if om else None,
                                     "opp": ot.name if ot else "bye"})
            except (StopIteration, requests.RequestException):
                continue
        for pid, byweek in weekly.items():
            if pid in players:
                players[pid].trend = [byweek.get(w) for w in range(1, week)]

    # recap: last week
    if mode == "recap" and week > 1:
        lw = week - 1
        try:
            matchups = get(f"{BASE}/league/{league_id}/matchups/{lw}")
            my_m = next(m for m in matchups if str(m["roster_id"]) == me.tid)
            opp_m = next((m for m in matchups
                          if m.get("matchup_id") == my_m.get("matchup_id") and str(m["roster_id"]) != me.tid), None)
            proj_last = load_projections(season, lw, key)
            pts_map = my_m.get("players_points") or {}
            for pid in pts_map:
                players.setdefault(pid, mk(pid))
            snap.last_week = lw
            snap.last_starters = [(p if p and p != "0" else None) for p in (my_m.get("starters") or [])]
            snap.last_pool = list(pts_map.keys())
            snap.last_pts = {pid: (float(pts_map.get(pid, 0.0)), proj_last.get(pid, 0.0)) for pid in pts_map}
            if opp_m:
                opp_t = next((t for t in teams if t.tid == str(opp_m["roster_id"])), None)
                snap.last_score = (float(my_m.get("points") or 0), float(opp_m.get("points") or 0),
                                   opp_t.name if opp_t else f"roster {opp_m['roster_id']}")
        except (StopIteration, requests.RequestException) as e:
            snap.warnings.append(f"Sleeper recap unavailable: {e}")
    return snap
