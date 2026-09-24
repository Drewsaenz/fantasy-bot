"""ESPN adapter (espn-api package): turns the league into a core.Snapshot.

Needs ESPN_S2 and SWID cookies from a logged-in espn.com browser session, in .env.
"""
import os
import sys

from core import BYE_LOOKAHEAD, POSITIONS, Player, Snapshot, Team
from nfl import espn_kickoffs, espn_teams_playing, norm_team

SLOT_MAP = {"RB/WR/TE": "FLEX", "RB/WR": "WRRB_FLEX", "WR/TE": "REC_FLEX", "OP": "SUPER_FLEX",
            "D/ST": "DEF", "BE": "BN"}
STATUS_MAP = {"OUT": "Out", "INJURY_RESERVE": "IR", "DOUBTFUL": "Doubtful",
              "SUSPENSION": "Sus", "QUESTIONABLE": "Questionable"}
ESPN_POS = {"DEF": "D/ST"}  # core position -> espn free_agents position arg
GAMES_PER_SEASON = 17
FA_PAGE = 40


def slot(name):
    return SLOT_MAP.get(name, name)


def pos_of(p):
    pos = getattr(p, "position", "") or ""
    return "DEF" if pos == "D/ST" else pos


def status_of(p):
    return STATUS_MAP.get(getattr(p, "injuryStatus", None) or "")


def week_proj(p, week):
    return float((getattr(p, "stats", {}) or {}).get(week, {}).get("projected_points") or 0)


def mk(p, week, pts=None, bye=False):
    """core.Player from an espn-api Player/BoxPlayer."""
    tot = float(getattr(p, "projected_total_points", 0) or 0)
    avg = float(getattr(p, "projected_avg_points", 0) or 0) or (tot / GAMES_PER_SEASON if tot else 0.0)
    own = getattr(p, "percent_owned", None)
    return Player(
        pid=str(p.playerId), name=p.name, pos=pos_of(p), team=norm_team(p.proTeam) or "FA",
        status=status_of(p),
        pts=float(pts if pts is not None else week_proj(p, week)),
        season_avg=avg,
        bye=bye or bool(getattr(p, "on_bye_week", False)),
        owned_pct=None if own in (None, -1) else float(own),
    )


def build(mode="check", week=None) -> Snapshot:
    from espn_api.football import League
    from espn_api.requests.espn_requests import ESPNAccessDenied

    league_id = int(os.environ.get("ESPN_LEAGUE_ID", "904472"))
    team_id = int(os.environ.get("ESPN_TEAM_ID", "25"))
    season = int(os.environ.get("ESPN_SEASON", "2026"))
    s2, swid = os.environ.get("ESPN_S2") or None, os.environ.get("SWID") or None
    if not (s2 and swid):
        raise RuntimeError("ESPN_S2 and SWID are missing from .env (see README, ESPN league)")
    try:
        lg = League(league_id=league_id, year=season, espn_s2=s2, swid=swid)
    except ESPNAccessDenied as e:
        raise RuntimeError(f"ESPN refused the cookies ({e}). Grab fresh espn_s2 and SWID from the browser.") from e

    week = week or lg.current_week
    slots = []
    for name, n in lg.settings.position_slot_counts.items():
        s = slot(name)
        if s not in ("BN", "IR"):
            slots += [s] * int(n)

    kickoffs = espn_kickoffs(lg, week)
    playing_now = set(kickoffs)
    byes = {}
    for w in range(week + 1, week + BYE_LOOKAHEAD + 1):
        playing = espn_teams_playing(lg, w)
        if playing:
            for t in playing_now - playing:
                byes.setdefault(t, w)

    players, teams, me = {}, [], None
    for t in lg.teams:
        pids = []
        for p in t.roster:
            cp = mk(p, week, bye=bool(playing_now) and norm_team(p.proTeam) not in playing_now)
            players[cp.pid] = cp
            if getattr(p, "lineupSlot", "") != "IR":
                pids.append(cp.pid)
        extra = f"{t.playoff_pct:.0f}% playoffs" if getattr(t, "playoff_pct", None) else ""
        team = Team(tid=str(t.team_id), name=t.team_name, players=pids, starters=[None] * len(slots),
                    record=f"{t.wins}-{t.losses}" + (f"-{t.ties}" if t.ties else ""), extra=extra)
        teams.append(team)
        if t.team_id == team_id:
            me = team
    if not me:
        raise RuntimeError(f"Team {team_id} not found in ESPN league {league_id}")

    def lineup_to_starters(lineup):
        by_slot = {}
        for p in lineup:
            cp = mk(p, week, pts=p.projected_points)
            prev = players.get(cp.pid)  # roster view has season avg and ownership; box score has freshest projection
            if prev:
                cp.season_avg = cp.season_avg or prev.season_avg
                cp.owned_pct = cp.owned_pct if cp.owned_pct is not None else prev.owned_pct
            cp.actual = float(getattr(p, "points", 0) or 0)  # live points so far this week
            players[cp.pid] = cp
            by_slot.setdefault(slot(p.slot_position), []).append(cp.pid)
        return [by_slot[s].pop(0) if by_slot.get(s) else None for s in slots]

    def side(box):
        def tid(t):
            return t if isinstance(t, int) else getattr(t, "team_id", None)
        if tid(box.home_team) == team_id:
            return box.home_lineup, box.away_team, box.away_lineup
        if tid(box.away_team) == team_id:
            return box.away_lineup, box.home_team, box.home_lineup
        return None

    snap = Snapshot(key="espn", name=lg.settings.name, week=week, slots=slots, players=players,
                    teams=teams, me=me, kickoffs=kickoffs, byes=byes)

    boxes = lg.box_scores(week)
    mine = next((s for s in (side(b) for b in boxes) if s), None)
    if mine:
        my_lineup, opp_team, opp_lineup = mine
        me.starters = lineup_to_starters(my_lineup)
        opp_id = opp_team if isinstance(opp_team, int) else getattr(opp_team, "team_id", None)
        snap.opp = next((t for t in teams if t.tid == str(opp_id)), None)
        if snap.opp and opp_lineup:
            snap.opp.starters = lineup_to_starters(opp_lineup)
    else:
        snap.warnings.append(f"ESPN: no box score for week {week} (bye week or playoffs?)")
        me.starters = [None] * len(slots)

    # free agents: this week's projection for check, next week's for waivers.
    # ESPN's K and D/ST queries return rostered players too, so filter against the rosters we just read.
    rostered = {pid for t in teams for pid in t.players} | {pid for t in teams for pid in t.starters if pid}
    fa_week = week + 1 if mode == "waivers" else week
    for pos in POSITIONS:
        try:
            fas = lg.free_agents(week=fa_week, size=FA_PAGE, position=ESPN_POS.get(pos, pos))
        except Exception as e:  # noqa: BLE001
            print(f"warning: ESPN free agents {pos} failed: {e}", file=sys.stderr)
            continue
        for p in fas:
            if str(p.playerId) in rostered or getattr(p, "onTeamId", 0):
                continue
            cp = mk(p, week, pts=p.projected_points)
            if mode == "waivers":
                cp.pts_next, cp.pts = cp.pts, 0.0
            players[cp.pid] = cp
            snap.free_agents.append(cp.pid)

    if mode == "waivers":
        # next-week projections for rostered players come from reloading rosters for that scoring period
        try:
            lg.load_roster_week(week + 1)
            for t in lg.teams:
                for p in t.roster:
                    if str(p.playerId) in players:
                        players[str(p.playerId)].pts_next = week_proj(p, week + 1)
        except Exception as e:  # noqa: BLE001
            print(f"warning: ESPN next-week roster load failed: {e}", file=sys.stderr)

    if mode == "dashboard":
        for t, team in zip(lg.teams, teams):
            snap.standings.append({"name": team.name, "record": team.record, "pf": float(t.points_for or 0),
                                   "extra": team.extra, "is_me": team.tid == me.tid})
        snap.standings.sort(key=lambda d: (-int(d["record"].split("-")[0]), -d["pf"]))
        mine_t = next(t for t in lg.teams if t.team_id == team_id)
        if len(mine_t.schedule) > week:
            snap.next_opp = getattr(mine_t.schedule[week], "team_name", "")
        for i in range(min(week - 1, len(mine_t.scores))):
            opp_t = mine_t.schedule[i] if i < len(mine_t.schedule) else None
            opp_scores = getattr(opp_t, "scores", [])
            snap.history.append({"week": i + 1, "mine": float(mine_t.scores[i] or 0),
                                 "theirs": float(opp_scores[i]) if i < len(opp_scores) else None,
                                 "opp": getattr(opp_t, "team_name", "bye")})

    if mode == "recap" and week > 1:
        lw = week - 1
        try:
            last = next((s for s in (side(b) for b in lg.box_scores(lw)) if s), None)
            if last:
                my_lineup, opp_team, opp_lineup = last
                snap.last_week = lw
                by_slot, pool, pts = {}, [], {}
                for p in my_lineup:
                    cp = mk(p, lw, pts=p.projected_points)
                    players.setdefault(cp.pid, cp)
                    pool.append(cp.pid)
                    pts[cp.pid] = (float(p.points or 0), float(p.projected_points or 0))
                    if slot(p.slot_position) not in ("BN", "IR"):
                        by_slot.setdefault(slot(p.slot_position), []).append(cp.pid)
                snap.last_starters = [by_slot[s].pop(0) if by_slot.get(s) else None for s in slots]
                snap.last_pool = pool
                snap.last_pts = pts
                mine_pts = sum(a for a, _ in (pts[p] for p in snap.last_starters if p))
                theirs = sum(float(p.points or 0) for p in opp_lineup if slot(p.slot_position) not in ("BN", "IR"))
                opp_name = getattr(opp_team, "team_name", f"team {opp_team}")
                snap.last_score = (mine_pts, theirs, opp_name)
        except Exception as e:  # noqa: BLE001
            snap.warnings.append(f"ESPN recap unavailable: {e}")
    return snap
