"""Self-contained HTML dashboard for both leagues. No external assets, works as a local file or on GitHub Pages."""
import html
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import core

LOCAL_TZ = ZoneInfo("America/Chicago")

# Football, shaped to still read at 16px: fat oval, one lace bar, heavy strokes.
ICON_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
    "<rect width='64' height='64' rx='14' fill='#1c1e21'/>"
    "<g transform='rotate(-35 32 32)'>"
    "<ellipse cx='32' cy='32' rx='28' ry='17' fill='#b8571f'/>"
    "<path d='M8 32 H56' stroke='#f6f7f9' stroke-width='4' stroke-linecap='round'/>"
    "<g stroke='#f6f7f9' stroke-width='4' stroke-linecap='round'>"
    "<path d='M22 26 V38'/><path d='M32 25 V39'/><path d='M42 26 V38'/>"
    "</g></g></svg>"
)
FAVICON = "data:image/svg+xml," + quote(ICON_SVG, safe="")

CSS = """
:root {
  color-scheme:light dark;
  --bg:#f4f5f7; --card:#fff; --ink:#15171a; --muted:#6b7280; --line:#e4e6ea; --rule:#eceef1;
  --good:#15803d; --bad:#b91c1c; --warn:#b45309; --live:#1d4ed8;
  --good-bg:#dcfce7; --bad-bg:#fee2e2; --warn-bg:#fef3c7; --live-bg:#eaf1ff; --chip:#eef0f3;
  --good-ink:#14532d; --warn-ink:#7c2d12;
  --shadow:0 1px 2px rgba(16,20,28,.05);
}
@media (prefers-color-scheme:dark) {
  :root {
    --bg:#0f1115; --card:#171a20; --ink:#e8eaee; --muted:#9aa2ae; --line:#272c34; --rule:#22262d;
    --good:#4ade80; --bad:#f87171; --warn:#fbbf24; --live:#7aa7ff;
    --good-bg:#12291c; --bad-bg:#2c1618; --warn-bg:#2b2010; --live-bg:#151e33; --chip:#232830;
    --good-ink:#a7f3c4; --warn-ink:#fcd9a8;
    --shadow:none;
  }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; -webkit-text-size-adjust:100%; }
header { position:sticky; top:0; z-index:5; padding:14px 20px 12px; display:flex; flex-wrap:wrap; gap:4px 14px; align-items:baseline;
         background:color-mix(in srgb, var(--bg) 88%, transparent); backdrop-filter:saturate(1.4) blur(8px); border-bottom:1px solid var(--line); }
header h1 { margin:0; font-size:17px; font-weight:650; letter-spacing:-.01em; }
header .muted { color:var(--muted); font-size:12.5px; font-variant-numeric:tabular-nums; }
main { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,440px),1fr)); gap:16px; padding:16px 20px 40px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px 18px; min-width:0; box-shadow:var(--shadow); }
.scroll { overflow-x:auto; }
.card h2 { margin:0 0 2px; font-size:17px; letter-spacing:-.01em; }
.card .sub { color:var(--muted); font-size:13px; margin-bottom:12px; }
.score { display:flex; justify-content:space-between; align-items:center; gap:12px; margin:10px 0 14px; padding:12px 14px; background:var(--bg); border-radius:10px; }
.score .side { flex:1; min-width:0; }
.score .side.them { text-align:right; }
.score .big { font-size:28px; font-weight:640; letter-spacing:-.02em; font-variant-numeric:tabular-nums; }
.score .side.lead .big { color:var(--good); }
.score .proj { color:var(--muted); font-size:12px; }
.score .vs { color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.08em; }
table { width:100%; border-collapse:collapse; font-size:14px; }
th, td { text-align:left; padding:6px; border-bottom:1px solid var(--rule); white-space:nowrap; }
tbody tr:last-child td { border-bottom:0; }
td:nth-child(2) { white-space:normal; }
th { color:var(--muted); font-weight:500; font-size:11px; text-transform:uppercase; letter-spacing:.05em; border-bottom-color:var(--line); }
td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
tr.bench td { color:var(--muted); }
tr.live td { background:var(--live-bg); }
tr.live td.num.pts { color:var(--live); font-weight:600; }
tr.done td { color:var(--muted); }
tr.done td:nth-child(2) { color:var(--ink); }
tr.me td { font-weight:600; }
.tag { display:inline-block; font-size:11px; padding:1px 6px; border-radius:999px; background:var(--chip); color:var(--ink); margin-left:4px; vertical-align:middle; }
.tag.bad { background:var(--bad-bg); color:var(--bad); }
.tag.warn { background:var(--warn-bg); color:var(--warn); }
.tag.live { background:var(--live-bg); color:var(--live); }
.tag.final { background:var(--good-bg); color:var(--good); }
.tag.bye { background:var(--chip); color:var(--muted); }
.game { color:var(--muted); font-size:12px; white-space:normal; }
svg.spark { width:56px; height:18px; display:block; }
.game.live { color:var(--live); font-weight:600; }
.issues { margin:0 0 10px; padding:8px 12px; border-radius:8px; background:var(--warn-bg); color:var(--warn-ink); font-size:13px; }
.issues.ok { background:var(--good-bg); color:var(--good-ink); }
.pos, .neg { font-variant-numeric:tabular-nums; }
.pos { color:var(--good); } .neg { color:var(--bad); }
h3 { font-size:11px; color:var(--muted); font-weight:600; margin:18px 0 6px; text-transform:uppercase; letter-spacing:.07em; }
details { margin-top:14px; }
summary { cursor:pointer; color:var(--muted); font-size:13px; }
summary:focus-visible { outline:2px solid var(--live); outline-offset:2px; border-radius:4px; }
pre { font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace; white-space:pre-wrap; background:var(--bg); padding:10px 12px; border-radius:8px; margin:8px 0 0; }
.wide { grid-column:1 / -1; }
/* agenda: the week as a list of deadlines, soonest first */
.agenda h2 { margin-bottom:12px; }
.agenda td, .agenda th { vertical-align:top; }
.agenda td.when { white-space:nowrap; font-weight:600; }
.agenda td.rel { white-space:nowrap; color:var(--muted); font-variant-numeric:tabular-nums; }
.agenda td.todo { white-space:normal; }
.agenda tr.past td { color:var(--muted); font-weight:400; }
.agenda tr.act td.when { color:var(--warn); }
.agenda .lg { display:inline-block; font-size:10.5px; letter-spacing:.04em; text-transform:uppercase;
              color:var(--muted); border:1px solid var(--line); border-radius:4px; padding:0 4px; margin-right:6px; }
.agenda ul { margin:2px 0 0; padding-left:16px; }
.agenda li { margin:1px 0; }
/* head to head: my starter and theirs on one row, slot down the middle */
.h2h td, .h2h th { white-space:nowrap; }
.h2h td.p { white-space:normal; }
.h2h td.r, .h2h th.r { text-align:right; }
.h2h td.slot, .h2h th.slot { text-align:center; color:var(--muted); font-size:11px; letter-spacing:.04em;
                             background:var(--bg); width:1%; padding-left:10px; padding-right:10px; }
.h2h .ko { display:block; color:var(--muted); font-size:11.5px; font-weight:400; }
.h2h .nm.live { color:var(--live); font-weight:600; }
.h2h .nm.done { color:var(--muted); }
/* results: one row per week, bar for the margin */
.hist td.bar { width:40%; min-width:120px; padding-right:0; }
.hist .track { display:flex; flex-direction:column; gap:2px; }
.hist .track i { display:block; height:6px; border-radius:3px; min-width:2px; }
.hist .track i.me { background:var(--good); }
.hist .track i.me.l { background:var(--bad); }
.hist .track i.them { background:var(--line); }
@media (max-width:480px) { main, header { padding-left:12px; padding-right:12px; } .card { padding:14px; } .score .big { font-size:24px; } }
"""


def esc(s):
    return html.escape(str(s), quote=True)


def signed(x):
    cls = "pos" if x > 0 else "neg" if x < 0 else ""
    return f'<span class="{cls}">{x:+.1f}</span>'


def game_cell(snap, pid):
    """When and who: 'Sun 12:00 PM vs LAC', 'LIVE @ BUF', 'Final vs NYJ', 'BYE'."""
    p = snap.p(pid)
    if p.bye:
        return '<span class="game">BYE</span>'
    g = snap.games.get(p.team, {})
    opp = g.get("opp")
    vs = ("vs\u00a0" if g.get("home") else "@\u00a0") + opp if opp else ""
    gs = core.game_state(snap, pid)
    if gs == "live":
        return f'<span class="game live">LIVE {esc(vs)}</span>'
    if gs == "final":
        return f'<span class="game">Final {esc(vs)}</span>'
    ko = snap.kickoffs.get(p.team)
    if ko:
        when = (ko.astimezone(LOCAL_TZ) if ko.tzinfo else ko).strftime("%a\u00a0%-I:%M\u00a0%p")
    elif g.get("date"):
        when = datetime.strptime(g["date"], "%Y-%m-%d").strftime("%a")
    else:
        when = ""
    return f'<span class="game">{esc((when + " " + vs).strip())}</span>'


def spark(p, proj):
    """Tiny bar chart of weekly actuals; bar height relative to the best week, grey below projection, dark at/above."""
    vals = p.trend
    if not vals or all(v is None for v in vals):
        return ""
    n = len(vals)
    top = max([v for v in vals if v is not None] + [proj, 1.0])
    W, H = 56, 18
    bw = max(2, min(6, (W - (n - 1) * 2) / n))  # left-aligned, fills in as the season goes
    bars, tips = [], []
    for i, v in enumerate(vals):
        x = i * (bw + 2)
        if v is None:
            bars.append(f'<rect x="{x:.1f}" y="{H - 2}" width="{bw:.1f}" height="2" fill="var(--line)"/>')
            tips.append(f"W{i + 1} –")
            continue
        h = max(1.5, v / top * (H - 1))
        fill = "var(--ink)" if v >= proj else "var(--muted)"
        bars.append(f'<rect x="{x:.1f}" y="{H - h:.1f}" width="{bw:.1f}" height="{h:.1f}" fill="{fill}" opacity="0.85" rx="1"/>')
        tips.append(f"W{i + 1} {v:.1f}")
    return f'<svg class="spark" viewBox="0 0 {W} {H}"><title>{esc(", ".join(tips))}</title>{"".join(bars)}</svg>'


def player_row(snap, slot, pid, bench=False):
    if not pid:
        return f'<tr class="{"bench" if bench else ""}"><td>{esc(slot)}</td><td colspan="6" class="neg">EMPTY</td></tr>'
    p = snap.p(pid)
    tags = ""
    title = f' title="{esc(p.note)}"' if p.note else ""
    if p.status in core.BAD_STATUSES:
        tags += f'<span class="tag bad"{title}>{esc(p.status)}</span>'
    elif p.status:
        tags += f'<span class="tag warn"{title}>{esc(p.status)}</span>'
    if p.bye:
        tags += '<span class="tag bad">BYE</span>'
    elif snap.byes.get(p.team):
        tags += f'<span class="tag bye">bye wk {snap.byes[p.team]}</span>'
    gs = core.game_state(snap, pid)
    actual = p.actual if (p.actual is not None and gs != "pre") else None
    act_html = f"{actual:.1f}" if actual is not None else '<span style="color:var(--muted)">–</span>'
    diff_html = signed(actual - p.pts) if actual is not None and gs == "final" else ""
    name = f"{p.team} D/ST" if p.pos == "DEF" else f"{p.name} <span style='color:var(--muted)'>{p.pos}-{p.team}</span>"
    cls = " ".join(c for c in ("bench" if bench else "", "live" if gs == "live" else "done" if gs == "final" else "") if c)
    return (f'<tr class="{cls}"><td>{esc(slot)}</td><td>{name}{tags}</td><td>{spark(p, p.pts)}</td><td>{game_cell(snap, pid)}</td>'
            f'<td class="num">{p.pts:.1f}</td><td class="num pts">{act_html}</td><td class="num">{diff_html}</td></tr>')


def _h2h_name(snap, pid):
    """Name, tags and kickoff for one side of the matchup row."""
    if not pid:
        return '<span class="nm neg">EMPTY</span>'
    p = snap.p(pid)
    gs = core.game_state(snap, pid)
    tags = ""
    title = f' title="{esc(p.note)}"' if p.note else ""
    if p.status in core.BAD_STATUSES:
        tags += f'<span class="tag bad"{title}>{esc(p.status)}</span>'
    elif p.status:
        tags += f'<span class="tag warn"{title}>{esc(p.status)}</span>'
    if p.bye:
        tags += '<span class="tag bad">BYE</span>'
    nm = f"{p.team} D/ST" if p.pos == "DEF" else f"{p.name} <span style='color:var(--muted)'>{p.pos}-{p.team}</span>"
    cls = " live" if gs == "live" else " done" if gs == "final" else ""
    return f'<span class="nm{cls}">{nm}</span>{tags}{game_cell(snap, pid)}'


def _h2h_pts(snap, pid):
    if not pid:
        return '<span style="color:var(--muted)">–</span>'
    p = snap.p(pid)
    gs = core.game_state(snap, pid)
    if p.actual is None or gs == "pre":
        return '<span style="color:var(--muted)">–</span>'
    return f"{p.actual:.1f}"


def h2h_table(snap, opp):
    """My starters and the opponent's on the same row, slot down the middle, so the matchup reads across."""
    rows = []
    for slot, mine, theirs in zip(snap.slots, snap.me.starters, opp.starters):
        rows.append(
            "<tr>"
            f'<td class="p">{_h2h_name(snap, mine)}</td>'
            f'<td class="num">{snap.pts(mine):.1f}</td><td class="num pts">{_h2h_pts(snap, mine)}</td>'
            f'<td class="slot">{esc(slot)}</td>'
            f'<td class="num pts">{_h2h_pts(snap, theirs)}</td><td class="num">{snap.pts(theirs):.1f}</td>'
            f'<td class="p r">{_h2h_name(snap, theirs)}</td>'
            "</tr>")
    head = (f'<thead><tr><th>{esc(snap.me.name)}</th><th class="num">Proj</th><th class="num">Pts</th>'
            f'<th class="slot">Slot</th><th class="num">Pts</th><th class="num">Proj</th>'
            f'<th class="r">{esc(opp.name)}</th></tr></thead>')
    return f'<div class="scroll"><table class="h2h">{head}<tbody>{"".join(rows)}</tbody></table></div>'


def lineup_table(snap, team, bench=True, starters=True):
    rows = [player_row(snap, s, pid) for s, pid in zip(snap.slots, team.starters)] if starters else []
    if bench:
        on = set(p for p in team.starters if p)
        for pid in sorted((p for p in team.players if p not in on), key=snap.pts, reverse=True):
            rows.append(player_row(snap, "BN", pid, bench=True))
    if not rows:
        return ""
    return ('<div class="scroll"><table><thead><tr><th>Slot</th><th>Player</th><th>Trend</th><th>Game</th><th class="num">Proj</th><th class="num">Pts</th><th class="num">+/-</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def history_table(hist):
    """One row per week. The two bars share a scale across the season, so a blowout looks like one."""
    if not hist:
        return '<div class="sub">No completed weeks yet.</div>'
    top = max([x["mine"] for x in hist] + [x["theirs"] or 0 for x in hist] + [1])
    rows = []
    for x in hist:
        them = x["theirs"]
        played = them is not None
        win = played and x["mine"] > them
        cls = "pos" if win else "neg" if played else ""
        bar = (f'<span class="track"><i class="me{"" if win else " l"}" style="width:{x["mine"] / top * 100:.0f}%"></i>'
               f'<i class="them" style="width:{(them or 0) / top * 100:.0f}%"></i></span>')
        rows.append(
            f'<tr><td>Wk {x["week"]}</td><td>{esc(x["opp"])}</td>'
            f'<td class="num">{x["mine"]:.1f}</td>'
            f'<td class="num">{f"{them:.1f}" if played else "–"}</td>'
            f'<td class="num {cls}">{f"{x["mine"] - them:+.1f}" if played else ""}</td>'
            f'<td class="{cls}">{"W" if win else "L" if played else "–"}</td>'
            f'<td class="bar">{bar}</td></tr>')
    return ('<div class="scroll"><table class="hist"><thead><tr><th>Week</th><th>Opponent</th>'
            '<th class="num">You</th><th class="num">Them</th><th class="num">Margin</th><th>Result</th><th></th>'
            f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def standings_table(st):
    rows = "".join(
        f'<tr class="{"me" if d["is_me"] else ""}"><td>{i + 1}</td><td>{esc(d["name"])}</td><td class="num">{esc(d["record"])}</td>'
        f'<td class="num">{d["pf"]:.1f}</td><td>{esc(d["extra"])}</td></tr>' for i, d in enumerate(st))
    return f'<div class="scroll"><table><thead><tr><th>#</th><th>Team</th><th class="num">W-L</th><th class="num">PF</th><th></th></tr></thead><tbody>{rows}</tbody></table></div>'


def waivers_block(snap):
    drop, rows = core.waiver_targets(snap, per_pos=2)
    if not drop or not rows:
        return ""
    d = snap.p(drop)
    trs = []
    for r in rows:
        p = snap.p(r["pid"])
        own = f"{p.owned_pct:.0f}%" if p.owned_pct is not None else ""
        bye = f'<span class="tag bye">bye wk {snap.byes[p.team]}</span>' if snap.byes.get(p.team) else ""
        flag = '<span class="tag final">claim</span>' if r["claim"] else ""
        name = f"{p.team} D/ST" if p.pos == "DEF" else f"{p.name} <span style='color:var(--muted)'>{p.team}</span>"
        trs.append(f'<tr><td>{r["pos"]}</td><td>{name}{bye}{flag}</td><td class="num">{p.pts_next:.1f}</td>'
                   f'<td class="num">{p.season_avg:.1f}</td><td class="num">{own}</td></tr>')
    return (f"<h3>Waiver targets · week {snap.week + 1}</h3>"
            f'<div class="sub">Drop candidate: {esc(snap.label(drop))} (season avg {d.season_avg:.1f}, next week {d.pts_next:.1f}). '
            f'"claim" beats both your drop and your worst at that position.</div>'
            '<div class="scroll"><table><thead><tr><th>Pos</th><th>Player</th><th class="num">Next wk</th><th class="num">Season</th><th class="num">Owned</th></tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table></div>')


def _decision(snap, slot, pid):
    """Why this starter still needs a look before his game locks, or None if he is fine."""
    p = snap.p(pid)
    if p.bye:
        return "on BYE"
    if p.status in core.BAD_STATUSES:
        return f"is {p.status}"
    if p.pts == 0:
        return "projects 0, check he has a game"
    if p.status:
        return f"is {p.status}"
    on = {x for x in snap.me.starters if x}
    alts = [b for b in snap.me.players
            if b not in on and not snap.locked(b) and core.startable(snap, b)
            and snap.p(b).positions() & core.slot_eligible(slot)]
    best = max(alts, key=snap.pts, default=None)
    if best and snap.pts(best) - p.pts >= core.SWAP_MIN_GAIN:
        return f"projects {p.pts:.1f}; bench has {snap.label(best)} at {snap.pts(best):.1f}"
    return None


def _rel(delta_s):
    if delta_s < 0:
        return "locked"
    m = delta_s / 60
    if m < 90:
        return f"{m:.0f} min"
    h = m / 60
    return f"{h:.0f} h" if h < 36 else f"{h / 24:.0f} d"


def agenda_card(snaps, now):
    """The week as a list of deadlines: every kickoff that locks part of a lineup, soonest first,
    with the starters that still need a decision before it."""
    slates, loose = {}, []
    for snap in snaps:
        for slot, pid in zip(snap.slots, snap.me.starters):
            if not pid:
                loose.append((snap, slot, None, "empty slot, nobody is in it"))
                continue
            ko = snap.kickoffs.get(snap.p(pid).team)
            why = _decision(snap, slot, pid)
            if snap.p(pid).bye or not ko:
                loose.append((snap, slot, pid, why or "no kickoff time"))
                continue
            slates.setdefault(ko.astimezone(LOCAL_TZ) if ko.tzinfo else ko, []).append((snap, slot, pid, why))
    if not slates and not loose:
        return ""
    rows = []
    if loose:
        items = "".join(f'<li><span class="lg">{esc(sn.key)}</span>{esc(sl)}: '
                        f'{esc(sn.label(pid) + " " if pid else "")}{esc(w)}</li>' for sn, sl, pid, w in loose)
        rows.append(f'<tr class="act"><td class="when">Now</td><td class="rel"></td><td class="num"></td>'
                    f'<td class="todo"><ul>{items}</ul></td></tr>')
    for ko in sorted(slates):
        group = slates[ko]
        past = ko <= now
        todo = [(sn, sl, pid, w) for sn, sl, pid, w in group if w]
        leagues = sorted({sn.key for sn, _, _, _ in group})
        if past:
            what = "started" if not todo else "too late to change"
        elif todo:
            what = "".join(f'<li><span class="lg">{esc(sn.key)}</span>{esc(sn.label(pid))} ({esc(sl)}) {esc(w)}</li>'
                           for sn, sl, pid, w in todo)
            what = f"<ul>{what}</ul>"
        else:
            what = f'<span style="color:var(--muted)">set, nothing to decide ({", ".join(leagues)})</span>'
        cls = "past" if past else "act" if todo else ""
        rows.append(f'<tr class="{cls}"><td class="when">{esc(ko.strftime("%a %-I:%M %p"))}</td>'
                    f'<td class="rel">{esc(_rel((ko - now).total_seconds()))}</td>'
                    f'<td class="num">{len(group)}</td><td class="todo">{what}</td></tr>')
    return ('<section class="card wide agenda"><h2>This week</h2>'
            '<div class="scroll"><table><thead><tr><th>Kickoff</th><th>In</th><th class="num">Locks</th>'
            f'<th>To do</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></section>')


def league_card(snap, report):
    report_text, issues = ("\n".join(report[0]), report[1]) if report else ("", [])
    act = lambda pid: (snap.p(pid).actual or 0.0) if pid and core.game_state(snap, pid) != "pre" else 0.0  # noqa: E731
    my_act, my_proj = core.total(snap, snap.me.starters, key=act), core.total(snap, snap.me.starters)
    opp = snap.opp
    opp_act = core.total(snap, opp.starters, key=act) if opp else 0.0
    opp_proj = core.total(snap, opp.starters) if opp else 0.0
    me_st = next((d for d in snap.standings if d["is_me"]), None)
    sub = f"{esc(snap.me.name)} · {esc(snap.me.record)}" + (f" · {esc(snap.me.extra)}" if snap.me.extra else "")
    if me_st:
        sub += f" · #{snap.standings.index(me_st) + 1} of {len(snap.standings)}"
    if snap.next_opp:
        sub += f" · next: {esc(snap.next_opp)}"
    parts = [f'<section class="card"><h2>{esc(snap.name)}</h2><div class="sub">{sub} · Week {snap.week}</div>']
    if issues:
        parts.append(f'<div class="issues">⚠️ {esc(", ".join(issues))}. Details in the report below.</div>')
    else:
        parts.append('<div class="issues ok">✅ Lineup is set. Nothing to fix right now.</div>')
    def playing(team):
        if not team:
            return ""
        n = sum(1 for pid in team.starters if pid and core.game_state(snap, pid) == "live")
        left = sum(1 for pid in team.starters if pid and core.game_state(snap, pid) == "pre")
        bits = ([f"{n} playing"] if n else []) + ([f"{left} to play"] if left else [])
        return (" · " + ", ".join(bits)) if bits else " · all done"
    started = any(pid and core.game_state(snap, pid) != "pre"
                  for t in (snap.me, opp) if t for pid in t.starters)
    # Before kickoff the actuals are all 0.0, which reads as a scoreline that hasn't happened; show projections instead.
    my_big, opp_big = (my_act, opp_act) if started else (my_proj, opp_proj)
    my_sub = f"you · proj {my_proj:.1f}" if started else "you · projected"
    opp_sub = (f"{esc(opp.name)} · proj {opp_proj:.1f}" if started else f"{esc(opp.name)} · projected") if opp else "no matchup"
    lead = " lead" if opp and my_big > opp_big else ""
    them_lead = " lead" if opp and opp_big > my_big else ""
    parts.append(
        '<div class="score">'
        f'<div class="side{lead}"><div class="big">{my_big:.1f}</div><div class="proj">{my_sub}{playing(snap.me)}</div></div>'
        '<div class="vs">vs</div>'
        f'<div class="side them{them_lead}"><div class="big">{opp_big:.1f}</div><div class="proj">{opp_sub}{playing(opp)}</div></div>'
        '</div>')
    if opp:
        parts.append(h2h_table(snap, opp))
        bn = lineup_table(snap, snap.me, bench=True, starters=False)
        if bn:
            parts.append("<h3>Your bench</h3>" + bn)
    else:
        parts.append(lineup_table(snap, snap.me))
    parts.append(waivers_block(snap))
    parts.append("<h3>Results</h3>" + history_table(snap.history))
    if snap.standings:
        parts.append("<h3>Standings</h3>" + standings_table(snap.standings))
    if report_text:
        parts.append(f"<details><summary>Full check report</summary><pre>{esc(report_text)}</pre></details>")
    parts.append("</section>")
    return "".join(parts)


def render(snaps, reports, failures=()):
    now = datetime.now(LOCAL_TZ)
    cards = agenda_card(snaps, now) + "".join(league_card(s, reports.get(s.key)) for s in snaps)
    cross = core.section_exposure(snaps) + core.section_projection_gaps(snaps)
    extra = ""
    if cross:
        extra += f'<section class="card wide"><h2>Across leagues</h2><pre>{esc(chr(10).join(cross))}</pre></section>'
    for f in failures:
        extra += f'<section class="card wide"><h2>Problem</h2><div class="neg">{esc(f)}</div></section>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="300"><meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#f4f5f7" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0f1115" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-title" content="Fantasy"><title>Fantasy dashboard</title>
<link rel="icon" href="{FAVICON}"><link rel="apple-touch-icon" href="{FAVICON}"><style>{CSS}</style></head>
<body><header><h1>Fantasy dashboard</h1><span class="muted">updated {now.strftime("%a %b %-d, %-I:%M %p")} Central · refreshes every 5 min</span></header>
<main>{cards}{extra}</main></body></html>"""
