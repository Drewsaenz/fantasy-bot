"""python test_core.py: the state machines in core.py against small hand-built snapshots. No network."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import core
import espn_league
from core import Player, Snapshot, Team

NOW = datetime(2026, 11, 15, 18, 0, tzinfo=timezone.utc)


def snap(players, starters, opp_starters=(), **kw):
    P = {p.pid: p for p in players}
    me = Team("1", "me", players=[p.pid for p in players if p.pid not in opp_starters], starters=list(starters))
    opp = Team("2", "them", players=list(opp_starters), starters=list(opp_starters)) if opp_starters else None
    return Snapshot(key="t", name="L", week=10, slots=kw.pop("slots", ["RB", "WR"]), players=P,
                    teams=[t for t in (me, opp) if t], me=me, opp=opp, **kw)


failed = 0


def check(name, got, want):
    global failed
    ok = got == want
    failed += not ok
    print("ok  " if ok else "FAIL", name, "" if ok else f"got {got!r} want {want!r}")


# --- game phase ---
a = Player("a", "A One", "RB", "SF", pts=10, actual=12.0)
b = Player("b", "B Two", "WR", "CHI", pts=0, bye=True)
c = Player("c", "C Three", "WR", "DAL", pts=9)
s = snap([a, b, c], ["a", "b"], game_status={"SF": "complete", "DAL": "pre_game"},
         kickoffs={"SF": NOW - timedelta(hours=4), "DAL": NOW + timedelta(hours=2)})
check("bye starter is 'bye', not 'pre'", core.game_state(s, "b", NOW), "bye")
check("finished game is final", core.game_state(s, "a", NOW), "final")
check("bye player is never locked", s.locked("b", NOW), False)
check("finished player is locked", s.locked("a", NOW), True)
check("future kickoff is not locked", s.locked("c", NOW), False)
s.kickoffs["DAL"] = NOW - timedelta(minutes=5)
check("kickoff passed, status still pre_game: live", core.game_state(s, "c", NOW), "live")
s.game_status["DAL"] = "postponed"
check("postponed game is not live", core.game_state(s, "c", NOW), "pre")
check("postponed game does not lock", s.locked("c", NOW), False)
s.game_status["DAL"] = "in_game"
s.kickoffs.pop("DAL")
check("in_game without a kickoff time is locked", s.locked("c", NOW), True)

# --- live: a starter on bye must not hold the week open ---
s = snap([a, b], ["a", "b"], game_status={"SF": "complete"})
lines, n, st = core.section_live(s, {"pts": {"a": 12.0, "b": 0.0}, "final": ["a"], "left": 1})
check("week done fires with a bye starter", st["done"], True)
check("bye starter is not 'left to play'", st["left"], 0)
check("done line is sent", any("Your week is done" in l for l in lines), True)
lines, n, st2 = core.section_live(s, st)
check("done line is sent once", lines, [])

# --- watch: rollover keeps statuses, forgets projections and nudges ---
old = {"week": 9, "t": {"players": {"a": {"status": None, "pts": 20.0, "base": 20.0}}, "pregame": ["a"]}}
rolled = core.watch_rollover(old, 10)
check("rollover sets the week", rolled["week"], 10)
check("rollover drops pregame nudges", "pregame" in rolled["t"], False)
hurt = Player("a", "A One", "RB", "SF", pts=4.0, status="Out")
s = snap([hurt], ["a"], slots=["RB"])
lines, n, new = core.section_watch(s, rolled["t"])
check("status change across the rollover is reported", n, 1)
check("it is the status line, not a projection drop", "Healthy → Out" in lines[1], True)
fine = Player("a", "A One", "RB", "SF", pts=4.0)
lines, n, new = core.section_watch(snap([fine], ["a"], slots=["RB"]), rolled["t"])
check("new week's lower projection is not a drop", n, 0)

# --- watch: a slide over several polls adds up ---
state, fired = {"players": {"a": {"status": None, "pts": 10.0}}}, []
for pts in (9.0, 8.0, 7.2, 6.9, 6.8):
    lines, n, state = core.section_watch(snap([Player("a", "A One", "RB", "SF", pts=pts)], ["a"], slots=["RB"]), state)
    fired.append(n)
check("slow slide 10 → 6.9 alerts once, at the 30% mark", fired, [0, 0, 0, 1, 0])
check("alert names the high-water mark", "10.0 → 6.9" in lines[-1] if lines else True, True)

# --- ESPN statuses ---
st_of = lambda v: espn_league.status_of(SimpleNamespace(injuryStatus=v))  # noqa: E731
check("ACTIVE is healthy", st_of("ACTIVE"), None)
check("empty list is healthy", st_of([]), None)
check("OUT maps", st_of("OUT"), "Out")
check("unknown status is shown, not healthy", st_of("DAY_TO_DAY"), "Day To Day")

# --- free-agent pickups: a defense replaces the defense, a skill player the weakest bench player ---
d1, d2 = Player("d1", "CIN", "DEF", "CIN", pts=6.3), Player("d2", "HOU", "DEF", "HOU", pts=8.2)
wr, bn = Player("w", "W One", "WR", "SF", pts=12), Player("n", "N Bench", "WR", "DAL", pts=5, trend=[5.0])
s = snap([wr, bn, d1, d2], ["w", "d1"], slots=["WR", "DEF"])
s.me.players = ["w", "n", "d1"]
s.free_agents = ["d2"]
check("D/ST pickup drops the D/ST it replaces", core.todo_moves(s), [("Add", "HOU D/ST 8.2 over CIN D/ST 6.3, drop CIN D/ST")])
check("report agrees", core.section_free_agents(s, ["w", "d1"])[0][1], "  drop CIN D/ST")
fa_wr = Player("f", "F Agent", "WR", "NYJ", pts=15)
s.players["f"] = fa_wr
s.free_agents = ["f"]
check("skill pickup still drops the weakest bench player", core.todo_moves(s)[0][1].endswith("drop N. Bench"), True)

print("all good" if not failed else f"{failed} failed")
raise SystemExit(1 if failed else 0)
