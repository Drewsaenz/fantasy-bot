"""Self-contained HTML dashboard for both leagues. No external assets, works as a local file or on GitHub Pages."""
import html
from datetime import datetime
from zoneinfo import ZoneInfo

import core

LOCAL_TZ = ZoneInfo("America/Chicago")

CSS = """
:root { --bg:#f6f7f9; --card:#fff; --ink:#1c1e21; --muted:#6b7280; --line:#e5e7eb; --good:#15803d; --bad:#b91c1c; --warn:#b45309; --live:#2563eb; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif; }
header { padding:18px 20px 6px; display:flex; flex-wrap:wrap; gap:8px 16px; align-items:baseline; }
header h1 { margin:0; font-size:20px; }
header .muted { color:var(--muted); font-size:13px; }
main { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,440px),1fr)); gap:16px; padding:12px 20px 32px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px 18px; min-width:0; }
.scroll { overflow-x:auto; }
.card h2 { margin:0 0 2px; font-size:17px; }
.card .sub { color:var(--muted); font-size:13px; margin-bottom:12px; }
.score { display:flex; justify-content:space-between; align-items:center; gap:12px; margin:10px 0 14px; padding:10px 12px; background:var(--bg); border-radius:8px; }
.score .side { flex:1; }
.score .side.them { text-align:right; }
.score .big { font-size:26px; font-weight:600; }
.score .proj { color:var(--muted); font-size:12px; }
.score .vs { color:var(--muted); font-size:12px; }
table { width:100%; border-collapse:collapse; font-size:14px; }
th, td { text-align:left; padding:5px 6px; border-bottom:1px solid var(--line); white-space:nowrap; }
td:nth-child(2) { white-space:normal; }
th { color:var(--muted); font-weight:500; font-size:12px; }
td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
tr.bench td { color:var(--muted); }
tr.live td { background:#eff6ff; }
tr.live td.num.pts { color:var(--live); font-weight:600; }
tr.done td { color:var(--muted); }
tr.done td:nth-child(2) { color:var(--ink); }
tr.me td { font-weight:600; }
.tag { display:inline-block; font-size:11px; padding:1px 6px; border-radius:999px; background:var(--line); color:var(--ink); margin-left:4px; vertical-align:middle; }
.tag.bad { background:#fee2e2; color:var(--bad); }
.tag.warn { background:#fef3c7; color:var(--warn); }
.tag.live { background:#dbeafe; color:var(--live); }
.tag.final { background:#dcfce7; color:var(--good); }
.tag.bye { background:#f3f4f6; color:var(--muted); }
.game { color:var(--muted); font-size:12px; white-space:normal; }
svg.spark { width:56px; height:18px; display:block; }
.game.live { color:var(--live); font-weight:600; }
.issues { margin:0 0 10px; padding:8px 12px; border-radius:8px; background:#fef3c7; color:#7c2d12; font-size:13px; }
.issues.ok { background:#dcfce7; color:#14532d; }
.pos, .neg { font-variant-numeric:tabular-nums; }
.pos { color:var(--good); } .neg { color:var(--bad); }
h3 { font-size:13px; color:var(--muted); font-weight:500; margin:16px 0 6px; text-transform:uppercase; letter-spacing:.03em; }
svg.hist { width:100%; height:auto; display:block; }
details { margin-top:14px; }
summary { cursor:pointer; color:var(--muted); font-size:13px; }
pre { font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace; white-space:pre-wrap; background:var(--bg); padding:10px 12px; border-radius:8px; margin:8px 0 0; }
.wide { grid-column:1 / -1; }
@media (max-width:480px) { main, header { padding-left:12px; padding-right:12px; } .card { padding:14px; } }
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


def lineup_table(snap, team, bench=True):
    rows = [player_row(snap, s, pid) for s, pid in zip(snap.slots, team.starters)]
    if bench:
        starters = set(p for p in team.starters if p)
        for pid in sorted((p for p in team.players if p not in starters), key=snap.pts, reverse=True):
            rows.append(player_row(snap, "BN", pid, bench=True))
    return ('<div class="scroll"><table><thead><tr><th>Slot</th><th>Player</th><th>Trend</th><th>Game</th><th class="num">Proj</th><th class="num">Pts</th><th class="num">+/-</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def history_svg(hist):
    if not hist:
        return '<div class="sub">No completed weeks yet.</div>'
    W, H, base = 600, 120, 100
    n = len(hist)
    slot = W / n
    bar = min(40, slot * 0.35)
    top = max([x["mine"] for x in hist] + [x["theirs"] or 0 for x in hist] + [1]) * 1.15
    parts = []
    for i, x in enumerate(hist):
        cx = i * slot + slot / 2
        mh = x["mine"] / top * (base - 16)
        th = (x["theirs"] or 0) / top * (base - 16)
        win = x["theirs"] is not None and x["mine"] > x["theirs"]
        color = "var(--good)" if win else "var(--bad)" if x["theirs"] is not None else "var(--muted)"
        parts.append(f'<rect x="{cx - bar - 2:.1f}" y="{base - mh:.1f}" width="{bar:.1f}" height="{mh:.1f}" fill="{color}" rx="3"/>')
        parts.append(f'<rect x="{cx + 2:.1f}" y="{base - th:.1f}" width="{bar:.1f}" height="{th:.1f}" fill="var(--line)" rx="3"/>')
        parts.append(f'<text x="{cx - bar / 2 - 2:.1f}" y="{base - mh - 4:.1f}" font-size="11" text-anchor="middle" fill="var(--ink)">{x["mine"]:.0f}</text>')
        if x["theirs"] is not None:
            parts.append(f'<text x="{cx + bar / 2 + 2:.1f}" y="{base - th - 4:.1f}" font-size="11" text-anchor="middle" fill="var(--muted)">{x["theirs"]:.0f}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{H - 4}" font-size="11" text-anchor="middle" fill="var(--muted)">Wk {x["week"]} · {esc(x["opp"])[:14]}</text>')
    return f'<svg class="hist" viewBox="0 0 {W} {H}" role="img" aria-label="weekly scores, you vs opponent">{"".join(parts)}</svg>'


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
    parts.append(
        '<div class="score">'
        f'<div class="side"><div class="big">{my_act:.1f}</div><div class="proj">you · proj {my_proj:.1f}{playing(snap.me)}</div></div>'
        '<div class="vs">vs</div>'
        f'<div class="side them"><div class="big">{opp_act:.1f}</div><div class="proj">{esc(opp.name) if opp else "no matchup"} · proj {opp_proj:.1f}{playing(opp)}</div></div>'
        '</div>')
    parts.append(lineup_table(snap, snap.me))
    if opp:
        parts.append(f"<h3>{esc(opp.name)}</h3>" + lineup_table(snap, opp, bench=False))
    parts.append(waivers_block(snap))
    parts.append("<h3>Results</h3>" + history_svg(snap.history))
    if snap.standings:
        parts.append("<h3>Standings</h3>" + standings_table(snap.standings))
    if report_text:
        parts.append(f"<details><summary>Full check report</summary><pre>{esc(report_text)}</pre></details>")
    parts.append("</section>")
    return "".join(parts)


def render(snaps, reports, failures=()):
    now = datetime.now(LOCAL_TZ)
    cards = "".join(league_card(s, reports.get(s.key)) for s in snaps)
    cross = core.section_exposure(snaps) + core.section_projection_gaps(snaps)
    extra = ""
    if cross:
        extra += f'<section class="card wide"><h2>Across leagues</h2><pre>{esc(chr(10).join(cross))}</pre></section>'
    for f in failures:
        extra += f'<section class="card wide"><h2>Problem</h2><div class="neg">{esc(f)}</div></section>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="300"><title>Fantasy dashboard</title><style>{CSS}</style></head>
<body><header><h1>Fantasy dashboard</h1><span class="muted">updated {now.strftime("%a %b %-d, %-I:%M %p")} Central · refreshes every 5 min</span></header>
<main>{cards}{extra}</main></body></html>"""
