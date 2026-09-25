"""
Platform-neutral model and report sections shared by the Sleeper and ESPN adapters.

Slot vocabulary is Sleeper's: QB RB WR TE K DEF FLEX WRRB_FLEX REC_FLEX SUPER_FLEX.
"""
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"]
FLEX_ELIGIBILITY = {
    "REC_FLEX": {"WR", "TE"},
    "WRRB_FLEX": {"RB", "WR"},
    "FLEX": {"RB", "WR", "TE"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
}
BAD_STATUSES = {"Out", "IR", "Doubtful", "Sus", "PUP", "NA", "COV", "DNR"}
FA_MIN_GAIN = 1.5      # this-week pickup must beat your weakest eligible starter by this much
SWAP_MIN_GAIN = 0.5    # ignore lineup swaps worth less than this (projection noise)
WAIVER_MIN_GAIN = 1.5  # waiver target must beat your drop candidate's season average by this much
PROJ_DISAGREE = 3.0    # flag Sleeper vs ESPN projection gaps of this size
PROJ_DROP = 0.30       # watch mode: projection fell by this fraction since the last poll
MOVES_HOURS = 24       # check mode: league transactions this recent
BYE_LOOKAHEAD = 2      # weeks

# Depth that matters for trade value in a 2RB/2WR/2FLEX format
TRADE_DEPTH = {"QB": 1, "RB": 3, "WR": 3, "TE": 1}


@dataclass
class Player:
    pid: str
    name: str
    pos: str
    team: str
    status: Optional[str] = None      # Out / IR / Doubtful / Sus / Questionable / None
    pts: float = 0.0                  # projected this week
    pts_next: float = 0.0             # projected next week (waivers)
    season_avg: float = 0.0           # season projection per game (trade value)
    actual: Optional[float] = None    # actual points (recap)
    bye: bool = False                 # on bye this week
    owned_pct: Optional[float] = None
    note: str = ""                    # injury detail when the platform has it
    trend: list = field(default_factory=list)  # actual points by week, None where unrostered / no data (dashboard)

    def positions(self):
        return {self.pos}


@dataclass
class Team:
    tid: str
    name: str
    players: list = field(default_factory=list)   # all rostered pids (excluding IR)
    starters: list = field(default_factory=list)  # by slot, None for empty
    record: str = ""
    extra: str = ""                                # e.g. playoff odds


@dataclass
class Snapshot:
    key: str                     # "sleeper" / "espn"
    name: str                    # league name
    week: int
    slots: list
    players: dict                # pid -> Player (everyone we know about)
    teams: list                  # all Teams
    me: Team
    opp: Optional[Team] = None
    free_agents: list = field(default_factory=list)   # pids
    kickoffs: dict = field(default_factory=dict)      # team -> datetime or None
    game_status: dict = field(default_factory=dict)   # team -> pre_game / in_game / complete / bye
    byes: dict = field(default_factory=dict)          # team -> next bye week within lookahead
    games: dict = field(default_factory=dict)         # team -> {opp, home, date} this week
    moves: list = field(default_factory=list)         # league transactions: dicts ts, team, action, pid, mine, status, bid
    next_opp: str = ""                                # next week's opponent (dashboard)
    # recap (last week)
    last_week: Optional[int] = None
    last_starters: list = field(default_factory=list)   # pids
    last_pool: list = field(default_factory=list)       # pids
    last_pts: dict = field(default_factory=dict)        # pid -> (actual, projected)
    last_score: Optional[tuple] = None                  # (mine, theirs, opp name)
    warnings: list = field(default_factory=list)
    # dashboard
    standings: list = field(default_factory=list)   # dicts: name, record, pf, extra, is_me
    history: list = field(default_factory=list)     # dicts: week, mine, theirs, opp

    # ---- helpers ----
    def p(self, pid) -> Player:
        return self.players.get(pid) or Player(pid=str(pid), name=f"player {pid}", pos="?", team="FA")

    def pts(self, pid):
        return self.p(pid).pts if pid else 0.0

    def locked(self, pid, now=None):
        """Game already kicked off (or finished) for this player's team."""
        if not pid:
            return False
        team = self.p(pid).team
        ko = self.kickoffs.get(team)
        if ko:
            return (now or _now(ko)) >= ko
        return self.game_status.get(team) in ("in_game", "complete")

    def label(self, pid):
        p = self.p(pid)
        if p.pos == "DEF":
            return f"{p.team} D/ST"
        return f"{p.name} ({p.pos}-{p.team})"

    def fmt(self, pid, key=None):
        p = self.p(pid)
        tags = "".join(f" [{t}]" for t in (p.status, "BYE" if p.bye else None, "LOCKED" if self.locked(pid) else None) if t)
        val = key(pid) if key else p.pts
        return f"{self.label(pid)}{tags} {val:.1f}"


def _now(like=None):
    """Current time, timezone-aware when the datetime we compare against is."""
    return datetime.now(like.tzinfo) if like is not None and like.tzinfo else datetime.now()


# ---------- lineup math ----------

def slot_eligible(slot):
    return FLEX_ELIGIBILITY.get(slot, {slot})


def slot_order(slots):
    """Fixed positions first, then flex slots from most to least restrictive."""
    flex = list(FLEX_ELIGIBILITY)
    return sorted(range(len(slots)),
                  key=lambda i: (slots[i] in flex, flex.index(slots[i]) if slots[i] in flex else 0))


def startable(snap: Snapshot, pid):
    p = snap.p(pid)
    return p.status not in BAD_STATUSES and not p.bye


def optimize(snap: Snapshot, pool, slots, key: Callable = None, fixed: dict = None, exclude=frozenset(), healthy_only=True):
    """Greedy best lineup. `fixed` = {slot_index: pid} kept as-is (locked starters);
    `exclude` = pids that can't enter (locked bench). `key` overrides the value function (e.g. actual points)."""
    key = key or snap.pts
    lineup, used = [None] * len(slots), set()
    for i, pid in (fixed or {}).items():
        if pid:
            lineup[i] = pid
            used.add(pid)
    cands = [p for p in pool if p not in used and p not in exclude and (not healthy_only or startable(snap, p))]
    ranked = sorted(cands, key=key, reverse=True)
    for i in slot_order(slots):
        if lineup[i]:
            continue
        elig = slot_eligible(slots[i])
        for pid in ranked:
            if pid not in used and snap.p(pid).positions() & elig:
                lineup[i] = pid
                used.add(pid)
                break
    return lineup


def total(snap: Snapshot, lineup, key=None):
    key = key or snap.pts
    return sum(key(p) for p in lineup if p)


def plural(n, word, suffix=""):
    """Pluralize the head noun, not the tail: plural(2, "dropped player", " worth a look")."""
    return f"{n} {word}" + ("" if n == 1 else "s") + suffix


# ---------- check-mode sections ----------

def section_alerts(snap: Snapshot):
    lines, issues, alerts, watch, locked_bad = [], [], [], [], []
    for slot, pid in zip(snap.slots, snap.me.starters):
        if not pid:
            alerts.append(f"{slot}: EMPTY slot")
            continue
        p = snap.p(pid)
        problem = None
        if p.status in BAD_STATUSES:
            problem = f"is {p.status}"
        elif p.bye:
            problem = "is on BYE"
        elif p.pts == 0:
            problem = "projects 0 (no game?)"
        if problem:
            (locked_bad if snap.locked(pid) else alerts).append(f"{slot}: {snap.fmt(pid)} {problem}")
        elif p.status == "Questionable":
            watch.append(f"{slot}: {snap.fmt(pid)}")
    if alerts:
        lines += ["🚨 Fix these:"] + [f"  - {a}" for a in alerts] + [""]
        issues.append(plural(len(alerts), "starter alert"))
    if locked_bad:
        lines += ["🔒 Too late to fix (already kicked off):"] + [f"  - {a}" for a in locked_bad] + [""]
    if watch:
        lines += ["👀 Questionable, check before kickoff:"] + [f"  - {w}" for w in watch] + [""]
    return lines, issues


def effective(snap: Snapshot):
    """Value function that counts Out / IR / bye players as zero, so benching them reads as a gain."""
    return lambda pid: snap.pts(pid) if pid and startable(snap, pid) else 0.0


def section_lineup(snap: Snapshot):
    lines, issues = [], []
    starters = snap.me.starters
    eff = effective(snap)
    fixed = {i: pid for i, pid in enumerate(starters) if pid and snap.locked(pid)}
    locked_bench = {p for p in snap.me.players if p not in starters and snap.locked(p)}
    best = optimize(snap, snap.me.players, snap.slots, fixed=fixed, exclude=locked_bench)
    cur_total, best_total = total(snap, starters, key=eff), total(snap, best, key=eff)
    gain = best_total - cur_total
    to_start = [p for p in best if p and p not in starters]
    to_sit = [p for p in starters if p and p not in best]
    if (to_start or to_sit) and gain >= SWAP_MIN_GAIN:
        lines.append(f"🔁 Lineup changes (+{gain:.1f} proj):")
        lines += [f"  - START {snap.fmt(p)}" for p in to_start]
        lines += [f"  - SIT   {snap.fmt(p)}" for p in to_sit]
        issues.append(f"lineup +{gain:.1f}")
    else:
        note = f" (+{gain:.1f} available, below threshold)" if to_start else ""
        lines.append("✅ Lineup matches projections." + note)
    holes = [s for s, p in zip(snap.slots, best) if not p]
    if holes:
        lines.append(f"  ⚠️ No healthy player for {', '.join(holes)}. Pick one up (see free agents).")
        issues.append(plural(len(holes), "empty slot"))
    if fixed:
        lines.append(f"  {plural(len(fixed), 'locked starter')} kept in place.")
    lines += [f"Projected: {cur_total:.1f} as set, {best_total:.1f} optimal", ""]
    return lines, issues, best


def section_free_agents(snap: Snapshot, best):
    lines, issues, fa_lines = [], [], []
    for pos in POSITIONS:
        elig_slots = [(s, p) for s, p in zip(snap.slots, best) if pos in slot_eligible(s)]
        if not elig_slots:
            continue
        empty = [s for s, p in elig_slots if not p]
        filled = [p for _, p in elig_slots if p]
        floor = None if empty else min(filled, key=snap.pts)
        floor_val = 0.0 if empty else snap.pts(floor)
        fas = sorted((p for p in snap.free_agents if snap.p(p).pos == pos and startable(snap, p) and not snap.locked(p)),
                     key=snap.pts, reverse=True)[:2]
        for fa in fas:
            if snap.pts(fa) - floor_val >= FA_MIN_GAIN:
                target = f"your empty {empty[0]}" if empty else f"your {snap.label(floor)} ({floor_val:.1f})"
                fa_lines.append(f"  - {snap.fmt(fa)} > {target}")
    if fa_lines:
        lines += ["➕ Free agents worth a look this week:"] + fa_lines
        bench = [p for p in snap.me.players if p not in best]
        if bench:
            weakest = min(bench, key=lambda p: snap.p(p).season_avg or snap.pts(p))
            avg = snap.p(weakest).season_avg
            lines.append(f"  Drop candidate: {snap.fmt(weakest)}" + (f" (season avg {avg:.1f})" if avg else ""))
        lines.append("")
        issues.append(plural(len(fa_lines), "FA pickup"))
    return lines, issues


def section_opponent(snap: Snapshot, best_total):
    lines = []
    if not snap.opp:
        return ["🆚 No matchup found this week.", ""]
    opp_total = total(snap, snap.opp.starters)
    rec = f" ({snap.opp.record}" + (f", {snap.opp.extra}" if snap.opp.extra else "") + ")" if snap.opp.record else ""
    lines.append(f"🆚 {snap.opp.name}{rec}: {opp_total:.1f} proj vs your {best_total:.1f} optimal")
    for slot, pid in zip(snap.slots, snap.opp.starters):
        if not pid:
            lines.append(f"  - their {slot} is EMPTY")
        else:
            p = snap.p(pid)
            if p.status in BAD_STATUSES | {"Questionable"} or p.bye:
                lines.append(f"  - their {slot}: {snap.fmt(pid)}")
    return lines + [""]


def section_byes(snap: Snapshot):
    """Starters and depth on bye in the next BYE_LOOKAHEAD weeks."""
    lines = []
    by_week = {}
    for pid in snap.me.players:
        w = snap.byes.get(snap.p(pid).team)
        if w:
            by_week.setdefault(w, []).append(pid)
    for w in sorted(by_week):
        pids = sorted(by_week[w], key=snap.pts, reverse=True)
        out_pos = {}
        for pid in pids:
            out_pos[snap.p(pid).pos] = out_pos.get(snap.p(pid).pos, 0) + 1
        left = []
        for pos, n in out_pos.items():
            have = sum(1 for p in snap.me.players if snap.p(p).pos == pos and startable(snap, p)) - n
            need = sum(1 for s in snap.slots if s == pos)
            if have < need:
                left.append(f"only {have} {pos} left for {need} slots")
        names = ", ".join(snap.label(p) for p in pids)
        lines.append(f"  - Week {w}: {names}" + (f"  ⚠️ {'; '.join(left)}" if left else ""))
    if lines:
        lines = ["📅 Byes coming up:"] + lines + [""]
    return lines


def report_check(snap: Snapshot):
    lines = [f"*{snap.name} - Week {snap.week} check*", ""]
    issues = []
    a, i = section_alerts(snap)
    lines += a
    issues += i
    l, i, best = section_lineup(snap)
    lines += l
    issues += i
    f, i = section_free_agents(snap, best)
    lines += f
    issues += i
    lines += section_opponent(snap, total(snap, best))
    lines += section_byes(snap)
    m, i = section_moves(snap)
    lines += m
    issues += i
    return lines, issues


def section_moves(snap: Snapshot, hours=MOVES_HOURS):
    """Your own transactions and other teams' drops that beat your bench, from the last `hours`."""
    since = time.time() - hours * 3600
    recent = sorted((m for m in snap.moves if m.get("ts", 0) >= since), key=lambda m: m["ts"])
    if not recent:
        return [], []
    lines, issues = [f"🔄 League moves (last {hours}h):"], []
    starters = {p for p in snap.me.starters if p}
    bench = [p for p in snap.me.players if p not in starters and snap.p(p).pos not in ("K", "DEF")]
    floor = min(bench, key=snap.pts) if bench else None
    mine = [m for m in recent if m["mine"]]
    for m in mine:
        verb = {"add": "added", "drop": "dropped", "waiver add": "claimed", "trade": "traded"}.get(m["action"], m["action"])
        st = f" ({m['status']})" if m.get("status") and m["status"] != "complete" else ""
        bid = f" for ${m['bid']}" if m.get("bid") else ""
        lines.append(f"  - you {verb} {snap.fmt(m['pid'])}{bid}{st}")
    notable, other = [], 0
    for m in recent:
        if m["mine"]:
            continue
        if m["action"] == "drop" and floor and startable(snap, m["pid"]) and snap.pts(m["pid"]) >= snap.pts(floor) + 1.0:
            notable.append(f"  💡 {m['team']} dropped {snap.fmt(m['pid'])}, beats your {snap.label(floor)} ({snap.pts(floor):.1f})")
        else:
            other += 1
    lines += notable
    if other:
        lines.append(f"  {other} other move{'s' if other != 1 else ''} around the league")
    if notable:
        issues.append(plural(len(notable), "dropped player", " worth a look"))
    return lines + [""], issues


# ---------- watch mode: status and projection changes ----------

def section_watch(snap: Snapshot, state: dict):
    """Events since the last poll for your roster and the opponent's starters. Returns (lines, count, new_state)."""
    prev = state.get("players", {})
    first = "players" not in state
    watch = [(pid, "starter") for pid in snap.me.starters if pid]
    watch += [(pid, "bench") for pid in snap.me.players if pid not in {p for p, _ in watch}]
    watch += [(pid, "their starter") for pid in (snap.opp.starters if snap.opp else []) if pid]
    events, new = [], {}
    for pid, role in watch:
        p = snap.p(pid)
        new[pid] = {"status": p.status, "pts": p.pts}
        if first or pid not in prev or snap.locked(pid):
            continue
        old = prev[pid]
        if old.get("status") != p.status:
            arrow = f"{old.get('status') or 'Healthy'} → {p.status or 'Healthy'}"
            icon = "🚑" if p.status in BAD_STATUSES else "🩺" if p.status else "💪"
            events.append(f"  {icon} {snap.label(pid)} ({role}): {arrow}" + (f". {p.note}" if p.note and p.status else ""))
        elif old.get("pts", 0) > 0 and p.pts < old["pts"] * (1 - PROJ_DROP):
            events.append(f"  📉 {snap.label(pid)} ({role}): projection {old['pts']:.1f} → {p.pts:.1f}")
    lines = [f"*{snap.name}*"] + events if events else []
    return lines, len(events), {"players": new}


# ---------- waivers mode ----------

def waiver_value(snap: Snapshot, pid):
    """Season projection carries more weight than one week's matchup."""
    p = snap.p(pid)
    if not p.season_avg:
        return p.pts_next
    return 0.6 * p.season_avg + 0.4 * p.pts_next


def waiver_targets(snap: Snapshot, per_pos=3):
    """(drop_pid, rows). rows: dicts with pos, pid, gain, claim. A claim beats both the drop candidate
    and your worst player at that position by WAIVER_MIN_GAIN; K/DEF only ever replace your own."""
    best = optimize(snap, snap.me.players, snap.slots)
    bench = [p for p in snap.me.players if p not in best]
    if not bench:
        return None, []
    value = lambda pid: waiver_value(snap, pid)  # noqa: E731
    skill_bench = [p for p in bench if snap.p(p).pos not in ("K", "DEF")] or bench
    drop = min(skill_bench, key=value)
    rows = []
    for pos in POSITIONS:
        pool = [p for p in snap.free_agents if snap.p(p).pos == pos and snap.p(p).status not in BAD_STATUSES]
        top = sorted(pool, key=value, reverse=True)[:per_pos]
        mine_here = [p for p in snap.me.players if snap.p(p).pos == pos]
        worst_here = min(mine_here, key=value) if mine_here else drop
        baseline = worst_here if pos in ("K", "DEF") else max((drop, worst_here), key=value)
        for fa in top:
            gain = value(fa) - value(baseline)
            rows.append({"pos": pos, "pid": fa, "gain": gain, "claim": gain >= WAIVER_MIN_GAIN})
    return drop, rows


def section_waivers(snap: Snapshot):
    lines, issues = [f"*{snap.name} - Week {snap.week + 1} waiver targets*", ""], []
    drop, rows = waiver_targets(snap)
    if not drop:
        return lines + ["No bench players to drop."], issues
    d = snap.p(drop)
    lines.append(f"Drop candidate: {snap.label(drop)} (season avg {d.season_avg:.1f}, next week {d.pts_next:.1f})")
    lines.append("")
    claims = 0
    for pos in POSITIONS:
        here = [r for r in rows if r["pos"] == pos]
        if not here:
            continue
        lines.append(f"{pos}:")
        for r in here:
            p = snap.p(r["pid"])
            own = f", {p.owned_pct:.0f}% owned" if p.owned_pct is not None else ""
            byew = snap.byes.get(p.team)
            bye = f", bye wk {byew}" if byew else ""
            flag = " ⬆️ claim" if r["claim"] else ""
            lines.append(f"  - {snap.label(r['pid'])}: next wk {p.pts_next:.1f}, season avg {p.season_avg:.1f}{own}{bye}{flag}")
            claims += r["claim"]
    if claims:
        issues.append(plural(claims, "waiver target"))
    return lines + [""], issues


# ---------- trade finder ----------

def positional_strength(snap: Snapshot, team: Team):
    out = {}
    for pos, depth in TRADE_DEPTH.items():
        vals = sorted((snap.p(p).season_avg for p in team.players if snap.p(p).pos == pos), reverse=True)
        out[pos] = sum(vals[:depth])
    return out


def section_trades(snap: Snapshot):
    lines = [f"*{snap.name} - trade ideas*", ""]
    if not any(snap.p(p).season_avg for p in snap.me.players):
        return lines + ["No season projections available.", ""]
    strength = {t.tid: positional_strength(snap, t) for t in snap.teams}
    n = len(snap.teams)
    avg = {pos: sum(s[pos] for s in strength.values()) / n for pos in TRADE_DEPTH}
    mine = strength[snap.me.tid]
    diff = {pos: mine[pos] - avg[pos] for pos in TRADE_DEPTH}
    weak = sorted((p for p in diff if diff[p] < 0), key=lambda p: diff[p])[:2]
    strong = sorted((p for p in diff if diff[p] > 0), key=lambda p: -diff[p])[:2]
    lines.append("Your depth vs league average (top-" + "/".join(f"{d} {p}" for p, d in TRADE_DEPTH.items()) + ", season proj per game):")
    lines.append("  " + ", ".join(f"{pos} {diff[pos]:+.1f}" for pos in TRADE_DEPTH))
    if not weak or not strong:
        return lines + ["  Balanced roster; no obvious position to trade from or for.", ""]

    def surplus(team, pos):
        ranked = sorted((p for p in team.players if snap.p(p).pos == pos), key=lambda p: snap.p(p).season_avg, reverse=True)
        return ranked[TRADE_DEPTH[pos] - 1:]  # their last "counted" starter onward

    partners = []
    for t in snap.teams:
        if t.tid == snap.me.tid:
            continue
        s = strength[t.tid]
        gives = [pos for pos in weak if s[pos] - avg[pos] > 0]
        wants = [pos for pos in strong if s[pos] - avg[pos] < 0]
        if gives and wants:
            score = sum(s[p] - avg[p] for p in gives) + sum(avg[p] - s[p] for p in wants)
            partners.append((score, t, gives, wants))
    partners.sort(key=lambda x: -x[0])
    if not partners:
        return lines + [f"  You're thin at {'/'.join(weak)} and deep at {'/'.join(strong)}, but no team is the mirror image right now.", ""]
    lines.append(f"You're thin at {'/'.join(weak)}, deep at {'/'.join(strong)}. Teams that are the opposite:")
    for _, t, gives, wants in partners[:3]:
        rec = f" ({t.record})" if t.record else ""
        lines.append(f"  - {t.name}{rec}:")
        for pos in gives:
            names = ", ".join(f"{snap.label(p)} {snap.p(p).season_avg:.1f}" for p in surplus(t, pos)[:3])
            lines.append(f"      their {pos} depth: {names}")
        for pos in wants:
            names = ", ".join(f"{snap.label(p)} {snap.p(p).season_avg:.1f}" for p in surplus(snap.me, pos)[:3])
            lines.append(f"      they need {pos}; you could offer: {names}")
    return lines + [""]


# ---------- recap mode ----------

def section_recap(snap: Snapshot):
    lines = [f"*{snap.name} - Week {snap.last_week} recap*", ""]
    if not snap.last_week or not snap.last_pts:
        return lines + ["No completed week to recap yet.", ""], None
    act = lambda pid: (snap.last_pts.get(pid) or (0.0, 0.0))[0]  # noqa: E731
    proj = lambda pid: (snap.last_pts.get(pid) or (0.0, 0.0))[1]  # noqa: E731
    starters = [p for p in snap.last_starters if p]
    my_pts = sum(act(p) for p in starters)
    my_proj = sum(proj(p) for p in starters)
    summary = None
    if snap.last_score:
        mine, theirs, opp = snap.last_score
        wl = "W" if mine > theirs else "L" if mine < theirs else "T"
        lines.append(f"{wl} {mine:.1f} to {theirs:.1f} vs {opp}. Starters projected {my_proj:.1f}, scored {my_pts:.1f} ({my_pts - my_proj:+.1f}).")
        summary = f"{wl} {mine:.0f}-{theirs:.0f}"
    hind = optimize(snap, snap.last_pool, snap.slots, key=act, healthy_only=False)
    left = total(snap, hind, key=act) - my_pts
    if left > 0.05:
        wrong = [p for p in hind if p and p not in starters]
        lines.append(f"Left on bench: {left:.1f}. Should have started: " + ", ".join(f"{snap.label(p)} {act(p):.1f}" for p in wrong))
    else:
        lines.append("You started the optimal lineup. Nothing left on the bench.")
    diffs = sorted(starters, key=lambda p: act(p) - proj(p))
    if diffs:
        bust, boom = diffs[0], diffs[-1]
        lines.append(f"Boom: {snap.label(boom)} {act(boom):.1f} (proj {proj(boom):.1f}). Bust: {snap.label(bust)} {act(bust):.1f} (proj {proj(bust):.1f}).")
    zeros = [p for p in starters if act(p) == 0]
    if zeros:
        lines.append("Zeros in the lineup: " + ", ".join(snap.label(p) for p in zeros))
    return lines + [""], summary


# ---------- cross-league ----------

def norm_name(p: Player):
    if p.pos == "DEF":
        return f"{p.team} DEF"
    n = re.sub(r"[^a-z ]", "", p.name.lower())
    n = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", n)
    return " ".join(n.split()) + f"|{p.pos}"


def section_exposure(snaps):
    lines = []
    if len(snaps) < 2:
        return lines
    seen = {}
    for s in snaps:
        for pid in s.me.players:
            seen.setdefault(norm_name(s.p(pid)), []).append((s, pid))
    shared = [(k, v) for k, v in seen.items() if len(v) >= 2]
    if not shared:
        return lines
    lines.append("🔗 On both of your rosters:")
    for _, v in sorted(shared, key=lambda kv: -max(s.pts(pid) for s, pid in kv[1])):
        s, pid = v[0]
        p = s.p(pid)
        tag = f" [{p.status}]" if p.status else ""
        risk = "  ⚠️ one injury hits both teams" if p.status else ""
        lines.append(f"  - {s.label(pid)}{tag}: " + ", ".join(f"{ss.key} {ss.pts(pp):.1f}" for ss, pp in v) + risk)
    return lines + [""]


def section_projection_gaps(snaps):
    """Where Sleeper and ESPN disagree about your players by PROJ_DISAGREE or more."""
    lines = []
    if len(snaps) < 2:
        return lines
    by_name = {}
    for s in snaps:
        for pid, p in s.players.items():
            if p.pts and p.pos not in ("K", "DEF"):  # K/DEF scoring differs too much between leagues
                by_name.setdefault(norm_name(p), {})[s.key] = p.pts
    mine = set()
    for s in snaps:
        mine |= {norm_name(s.p(pid)) for pid in s.me.players}
    rows = []
    for key in mine:
        vals = by_name.get(key, {})
        if len(vals) < 2:
            continue
        hi, lo = max(vals, key=vals.get), min(vals, key=vals.get)
        gap = vals[hi] - vals[lo]
        if gap >= PROJ_DISAGREE:
            label = key.split("|")[0].title() if not key.endswith("DEF") else key.replace(" DEF", " D/ST")
            rows.append((gap, f"  - {label}: {hi} {vals[hi]:.1f} vs {lo} {vals[lo]:.1f} (gap {gap:.1f})"))
    if rows:
        lines += ["⚖️ Projections disagree on your players (worth a second look before trusting either):"]
        lines += [r for _, r in sorted(rows, reverse=True)[:8]]
        lines.append("")
    return lines


# ---------- live mode ----------

LIVE_JUMP = 6.0  # points gained since the last poll that count as a "big play"


def game_state(snap: Snapshot, pid, now=None):
    """pre / live / final for this player's team this week."""
    team = snap.p(pid).team
    st = snap.game_status.get(team)
    if st == "complete":
        return "final"
    if st and st != "pre_game":
        return "live"
    ko = snap.kickoffs.get(team)
    if ko and (now or _now(ko)) >= ko:
        return "live"
    return "pre"


def section_live(snap: Snapshot, state: dict):
    """Events since the last poll. Returns (lines, events_count, new_state). Lines are empty when nothing happened."""
    prev_pts = state.get("pts", {})
    reported_final = set(state.get("final", []))
    act = lambda pid: snap.p(pid).actual or 0.0  # noqa: E731
    mine = [p for p in snap.me.starters if p]
    theirs = [p for p in (snap.opp.starters if snap.opp else []) if p]
    events, finals = [], []
    first_poll = "pts" not in state  # no baseline yet (new week or reset): record, don't report jumps
    for pid in mine:
        d = act(pid) - prev_pts.get(pid, 0.0)
        if not first_poll and d >= LIVE_JUMP and game_state(snap, pid) != "pre":
            events.append(f"  🔥 {snap.label(pid)} +{d:.1f}, now {act(pid):.1f}")
    for pid in theirs:
        d = act(pid) - prev_pts.get(pid, 0.0)
        if not first_poll and d >= LIVE_JUMP and game_state(snap, pid) != "pre":
            events.append(f"  😬 their {snap.label(pid)} +{d:.1f}, now {act(pid):.1f}")
    for pid in mine:
        if game_state(snap, pid) == "final" and pid not in reported_final:
            diff = act(pid) - snap.pts(pid)
            finals.append(f"  ✅ {snap.label(pid)} final {act(pid):.1f} (proj {snap.pts(pid):.1f}, {diff:+.1f})")
            reported_final.add(pid)
    my_left = [p for p in mine if game_state(snap, p) != "final"]
    opp_left = [p for p in theirs if game_state(snap, p) != "final"]
    new_state = {"pts": {pid: act(pid) for pid in mine + theirs}, "final": sorted(reported_final),
                 "done": state.get("done", False), "left": len(my_left) + len(opp_left)}
    endgame = 0 < len(my_left) + len(opp_left) <= 4
    left_changed = endgame and state.get("left") is not None and state["left"] != new_state["left"]
    lines = []
    if events or finals or left_changed:
        my_total, opp_total = sum(act(p) for p in mine), sum(act(p) for p in theirs)
        played = sum(1 for p in mine if game_state(snap, p) == "final")
        live_n = sum(1 for p in mine if game_state(snap, p) == "live")
        opp = snap.opp.name if snap.opp else "opponent"
        lines.append(f"*{snap.name}*: you {my_total:.1f}, {opp} {opp_total:.1f}  ({played}/{len(mine)} final, {live_n} playing)")
        lines += events + finals
        if endgame:
            diff = my_total - opp_total
            def left_txt(pids):
                return ", ".join(f"{snap.label(p)} (proj {snap.pts(p):.1f}{', live' if game_state(snap, p) == 'live' else ''})" for p in pids) or "nobody"
            lead = f"Up {diff:.1f}" if diff > 0 else f"Down {-diff:.1f}" if diff < 0 else "Tied"
            lines.append(f"  📊 {lead}. Left: you {left_txt(my_left)}; them {left_txt(opp_left)}.")
    all_done = mine and all(game_state(snap, p) == "final" for p in mine)
    if all_done and not state.get("done"):
        my_total, opp_total = sum(act(p) for p in mine), sum(act(p) for p in theirs)
        wl = "W" if my_total > opp_total else "L" if my_total < opp_total else "T"
        if not lines:
            lines.append(f"*{snap.name}*")
        opp_left = sum(1 for p in theirs if game_state(snap, p) != "final")
        tail = f" ({opp_left} of theirs still to play)" if opp_left else ""
        lines.append(f"  🏁 Your week is done: {wl} {my_total:.1f} to {opp_total:.1f}{tail}")
        new_state["done"] = True
    return lines, len(events) + len(finals), new_state
