"""NFL schedule helpers shared by both adapters: game status, kickoff times, byes."""
import sys
from datetime import datetime, timezone

import requests

SLEEPER_SCHEDULE = "https://api.sleeper.app/schedule/nfl/regular/{season}"  # undocumented
TEAM_ALIASES = {"WSH": "WAS", "JAC": "JAX", "LA": "LAR", "OAK": "LV", "SD": "LAC"}


def norm_team(abbr):
    return TEAM_ALIASES.get(abbr, abbr) if abbr else abbr


def sleeper_schedule(season):
    """{week: {team: {"opp": str, "status": str, "date": str}}}. Empty on failure."""
    try:
        games = requests.get(SLEEPER_SCHEDULE.format(season=season), timeout=30).json()
    except Exception as e:  # noqa: BLE001
        print(f"warning: Sleeper schedule failed: {e}", file=sys.stderr)
        return {}
    out = {}
    for g in games or []:
        w = int(g.get("week") or 0)
        home, away = norm_team(g.get("home")), norm_team(g.get("away"))
        for t, o, is_home in ((home, away, True), (away, home, False)):
            out.setdefault(w, {})[t] = {"opp": o, "home": is_home, "status": g.get("status"), "date": g.get("date")}
    return out


def byes_from(schedule_by_week, week, lookahead, teams=None):
    """team -> first bye week in (week, week+lookahead]. `teams` defaults to all teams seen in `week`."""
    teams = set(teams or schedule_by_week.get(week, {}).keys())
    byes = {}
    for w in range(week + 1, week + lookahead + 1):
        playing = set(schedule_by_week.get(w, {}).keys())
        if not playing:
            continue
        for t in teams - playing:
            byes.setdefault(t, w)
    return byes


def espn_kickoffs(league, week):
    """team -> kickoff datetime (local) from ESPN's pro schedule. Empty dict on failure."""
    try:
        from espn_api.football.constant import PRO_TEAM_MAP
        sched = league._get_pro_schedule(week)  # noqa: SLF001 (no public accessor)
    except Exception as e:  # noqa: BLE001
        print(f"warning: ESPN pro schedule failed: {e}", file=sys.stderr)
        return {}
    out = {}
    for tid, (opp, ms) in sched.items():
        abbr = norm_team(PRO_TEAM_MAP.get(int(tid)))
        if abbr and ms:
            out[abbr] = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)  # aware, so it renders right on any host
    return out


def espn_teams_playing(league, week):
    try:
        from espn_api.football.constant import PRO_TEAM_MAP
        return {norm_team(PRO_TEAM_MAP.get(int(t))) for t in league._get_pro_schedule(week)}  # noqa: SLF001
    except Exception:  # noqa: BLE001
        return set()
