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
main { display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:16px; padding:12px 20px 32px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px 18px; }
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
th { color:var(--muted); font-weight:500; font-size:12px; }
td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
tr.bench td { color:var(--muted); }
tr.me td { font-weight:600; }
.tag { display:inline-block; font-size:11px; padding:1px 6px; border-radius:999px; background:var(--line); color:var(--ink); margin-left:4px; vertical-align:middle; }
.tag.bad { background:#fee2e2; color:var(--bad); }
.tag.warn { background:#fef3c7; color:var(--warn); }
.tag.live { background:#dbeafe; color:var(--live); }
.tag.final { background:#dcfce7; color:var(--good); }
.pos, .neg { font-variant-numeric:tabular-nums; }
.pos { color:var(--good); } .neg { color:var(--bad); }
h3 { font-size:13px; color:var(--muted); font-weight:500; margin:16px 0 6px; text-transform:uppercase; letter-spacing:.03em; }
svg.hist { width:100%; height:110px; display:block; }
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


def player_row(snap, slot, pid, bench=False):
    if not pid:
        return f'<tr class="{"bench" if bench else ""}"><td>{esc(slot)}</td><td colspan="4" class="neg">EMPTY</td></tr>'
    p = snap.p(pid)
    tags = ""
    if p.status in core.BAD_STATUSES:
        tags += f'<span class="tag bad">{esc(p.status)}</span>'
    elif p.status:
        tags += f'<span class="tag warn">{esc(p.status)}</span>'
    if p.bye:
        tags += '<span class="tag bad">BYE</span>'
    gs = core.game_state(snap, pid)
    if gs == "live":
        tags += '<span class="tag live">LIVE</span>'
    elif gs == "final":
        tags += '<span class="tag final">FINAL</span>'
    actual = p.actual if (p.actual is not None and gs != "pre") else None
    act_html = f"{actual:.1f}" if actual is not None else '<span style="color:var(--muted)">–</span>'
    diff_html = signed(actual - p.pts) if actual is not None and gs == "final" else ""
    name = f"{p.team} D/ST" if p.pos == "DEF" else f"{p.name} <span style='color:var(--muted)'>{p.pos}-{p.team}</span>"
    return (f'<tr class="{"bench" if bench else ""}"><td>{esc(slot)}</td><td>{name}{tags}</td>'
            f'<td class="num">{p.pts:.1f}</td><td class="num">{act_html}</td><td class="num">{diff_html}</td></tr>')


def lineup_table(snap, team, bench=True):
    rows = [player_row(snap, s, pid) for s, pid in zip(snap.slots, team.starters)]
    if bench:
        starters = set(p for p in team.starters if p)
        for pid in sorted((p for p in team.players if p not in starters), key=snap.pts, reverse=True):
            rows.append(player_row(snap, "BN", pid, bench=True))
    return ('<table><thead><tr><th>Slot</th><th>Player</th><th class="num">Proj</th><th class="num">Pts</th><th class="num">+/-</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def history_svg(hist):
    if not hist:
        return '<div class="sub">No completed weeks yet.</div>'
    w, h, pad = 100.0 / max(len(hist), 1), 100, 4
    top = max([x["mine"] for x in hist] + [x["theirs"] or 0 for x in hist] + [1])
    parts = []
    for i, x in enumerate(hist):
        x0 = i * w
        mh = x["mine"] / top * (h - 24)
        th = (x["theirs"] or 0) / top * (h - 24)
        win = x["theirs"] is not None and x["mine"] > x["theirs"]
        color = "var(--good)" if win else "var(--bad)" if x["theirs"] is not None else "var(--muted)"
        parts.append(f'<rect x="{x0 + pad:.1f}%" width="{w / 2 - pad:.1f}%" y="{h - 18 - mh:.1f}" height="{mh:.1f}" fill="{color}" rx="2"/>')
        parts.append(f'<rect x="{x0 + w / 2:.1f}%" width="{w / 2 - pad:.1f}%" y="{h - 18 - th:.1f}" height="{th:.1f}" fill="var(--line)" rx="2"/>')
        parts.append(f'<text x="{x0 + w / 2:.1f}%" y="{h - 4}" font-size="10" text-anchor="middle" fill="var(--muted)">W{x["week"]}</text>')
        parts.append(f'<text x="{x0 + w / 2:.1f}%" y="{h - 22 - max(mh, th):.1f}" font-size="10" text-anchor="middle" fill="var(--ink)">{x["mine"]:.0f}</text>')
    return f'<svg class="hist" viewBox="0 0 100 {h}" preserveAspectRatio="none">{"".join(parts)}</svg>'


def standings_table(st):
    rows = "".join(
        f'<tr class="{"me" if d["is_me"] else ""}"><td>{i + 1}</td><td>{esc(d["name"])}</td><td class="num">{esc(d["record"])}</td>'
        f'<td class="num">{d["pf"]:.1f}</td><td>{esc(d["extra"])}</td></tr>' for i, d in enumerate(st))
    return f'<table><thead><tr><th>#</th><th>Team</th><th class="num">W-L</th><th class="num">PF</th><th></th></tr></thead><tbody>{rows}</tbody></table>'


def league_card(snap, report_text):
    act = lambda pid: (snap.p(pid).actual or 0.0) if pid and core.game_state(snap, pid) != "pre" else 0.0  # noqa: E731
    my_act, my_proj = core.total(snap, snap.me.starters, key=act), core.total(snap, snap.me.starters)
    opp = snap.opp
    opp_act = core.total(snap, opp.starters, key=act) if opp else 0.0
    opp_proj = core.total(snap, opp.starters) if opp else 0.0
    me_st = next((d for d in snap.standings if d["is_me"]), None)
    sub = f"{esc(snap.me.name)} · {esc(snap.me.record)}" + (f" · {esc(snap.me.extra)}" if snap.me.extra else "")
    if me_st:
        sub += f" · #{snap.standings.index(me_st) + 1} of {len(snap.standings)}"
    parts = [f'<section class="card"><h2>{esc(snap.name)}</h2><div class="sub">{sub} · Week {snap.week}</div>']
    parts.append(
        '<div class="score">'
        f'<div class="side"><div class="big">{my_act:.1f}</div><div class="proj">you · proj {my_proj:.1f}</div></div>'
        '<div class="vs">vs</div>'
        f'<div class="side them"><div class="big">{opp_act:.1f}</div><div class="proj">{esc(opp.name) if opp else "no matchup"} · proj {opp_proj:.1f}</div></div>'
        '</div>')
    parts.append(lineup_table(snap, snap.me))
    if opp:
        parts.append(f"<h3>{esc(opp.name)}</h3>" + lineup_table(snap, opp, bench=False))
    parts.append("<h3>Results</h3>" + history_svg(snap.history))
    if snap.standings:
        parts.append("<h3>Standings</h3>" + standings_table(snap.standings))
    if report_text:
        parts.append(f"<details><summary>Full check report</summary><pre>{esc(report_text)}</pre></details>")
    parts.append("</section>")
    return "".join(parts)


def render(snaps, reports, failures=()):
    now = datetime.now(LOCAL_TZ)
    cards = "".join(league_card(s, reports.get(s.key, "")) for s in snaps)
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
