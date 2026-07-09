"""Generate a single self-contained HTML dashboard of the recommendation audit.

No server, no JS libraries, no internet: charts are inline SVG, styling is
inline CSS. The output file opens by double-click in any browser and can be
shared or attached as-is.
"""
from __future__ import annotations

import html
import sqlite3
from datetime import date

import pandas as pd

from ..config import ASSET_PROXIES
from ..portfolio.audit import run_audit

DEFAULT_BENCHMARK = 120716  # UTI Nifty 50 Index Fund (TRI proxy)
from ..portfolio.backtest import backtest
from ..portfolio.benchmark import build_blended_benchmark
from ..portfolio.reconstruct import reconstruct
from ..recommend import schema
from ..store import nav_store

BG = "#F2EFE8"
PANEL = "#FBF9F4"
BORDER = "#E4DDD0"
TEXT = "#17150F"
MUTED = "#8D8677"
NAVY = "#EBE6DB"          # header bars (kept name for compatibility)
ACCENT = "#B98A46"        # bronze, the single signature accent
PASSIVE = "#7A6FB3"       # teal-cyan (chart line only)
BENCH = "#8D8677"         # gray (chart line only)
GOOD = "#147A52"          # green, direction only
BAD = "#C2452D"           # red, direction only
GRID = "#E4DDD0"


# ---------- data gathering -------------------------------------------------

def _plan_series(conn, rec, benchmark_code, proxies):
    """Return (recommended, nifty, passive) value series aligned, plus audit."""
    nav_by_code, weights, missing = {}, {}, []
    for f in rec.funds:
        if not (f.included and f.scheme_code):
            continue
        s = nav_store.load_nav(conn, f.scheme_code)
        if s.empty:
            missing.append(f.scheme_code)
            continue
        nav_by_code[f.scheme_code] = s
        weights[f.scheme_code] = weights.get(f.scheme_code, 0.0) + f.weight
    if not weights:
        return None
    bench_nav = nav_store.load_nav(conn, benchmark_code)
    if bench_nav.empty:
        return None

    rec_recon = reconstruct(nav_by_code, weights, rec.rec_date, rec.total_amount)
    start = rec_recon.start_date
    # Nifty scaled to same rupee start
    bn = bench_nav[bench_nav.index >= start]
    nifty = (bn / float(bn.iloc[0])) * rec.total_amount
    blended = build_blended_benchmark(conn, rec, rec.rec_date, rec.total_amount, proxies)
    passive = blended.value if blended is not None else None

    audit = run_audit(
        nav_by_code, weights, bench_nav, start=rec.rec_date,
        amount=rec.total_amount, rec_id=rec.rec_id, advisor=rec.advisor,
        blended_value=passive,
    )
    bt = backtest(conn, rec, proxies=proxies)
    from .data import window_stats
    fwd = window_stats(rec_recon.value, lookback_years=None)
    return {
        "rec": rec, "audit": audit, "backtest": bt, "fwd": fwd,
        "recommended": rec_recon.value, "nifty": nifty, "passive": passive,
    }


# ---------- svg helpers ----------------------------------------------------

def _svg_line(series: dict[str, tuple[pd.Series, str]], w=720, h=300) -> str:
    """series: label -> (pd.Series, colour). Dark theme, gridlines, area fill on first series."""
    pad_l, pad_r, pad_t, pad_b = 8, 8, 16, 24
    clean = {k: (s.dropna(), c) for k, (s, c) in series.items() if s is not None and len(s.dropna()) > 1}
    if not clean:
        return '<p style="color:#787b86">(no chart data)</p>'
    all_idx = sorted(set().union(*[set(s.index) for s, _ in clean.values()]))
    idx = pd.DatetimeIndex(all_idx)
    lo = min(float(s.reindex(idx).ffill().min()) for s, _ in clean.values())
    hi = max(float(s.reindex(idx).ffill().max()) for s, _ in clean.values())
    span = (hi - lo) or 1.0
    n = len(idx)
    plot_h = h - pad_t - pad_b

    def xy(s):
        s = s.reindex(idx).ffill().bfill()
        step = max(1, n // 240)
        pts = []
        for i in range(0, n, step):
            x = pad_l + (i / (n - 1)) * (w - pad_l - pad_r)
            y = pad_t + (1 - (float(s.iloc[i]) - lo) / span) * plot_h
            pts.append((x, y))
        return pts

    # horizontal gridlines (4)
    grid = ""
    for g in range(5):
        gy = pad_t + plot_h * g / 4
        val = hi - span * g / 4
        grid += (f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{w-pad_r}" y2="{gy:.1f}" '
                 f'stroke="{GRID}" stroke-width="1"/>'
                 f'<text x="{w-pad_r}" y="{gy-2:.1f}" font-size="9" fill="{MUTED}" '
                 f'text-anchor="end">₹{val/100000:.1f}L</text>')

    body, legend, lx = "", "", pad_l
    first = True
    for label, (s, c) in clean.items():
        pts = xy(s)
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        if first:  # area fill under the primary (recommended) series
            area = f"{pts[0][0]:.1f},{pad_t+plot_h:.1f} " + poly + f" {pts[-1][0]:.1f},{pad_t+plot_h:.1f}"
            body += (f'<defs><linearGradient id="ag" x1="0" y1="0" x2="0" y2="1">'
                     f'<stop offset="0" stop-color="{c}" stop-opacity="0.22"/>'
                     f'<stop offset="1" stop-color="{c}" stop-opacity="0"/></linearGradient></defs>'
                     f'<polygon points="{area}" fill="url(#ag)"/>')
            first = False
        body += f'<polyline fill="none" stroke="{c}" stroke-width="1.6" points="{poly}"/>'
        legend += (f'<rect x="{lx}" y="{h-11}" width="9" height="3" rx="1.5" fill="{c}"/>'
                   f'<text x="{lx+13}" y="{h-7}" font-size="10.5" fill="{MUTED}">{html.escape(label)}</text>')
        lx += 13 + int(6.2 * len(label)) + 20

    return (
        f'<svg viewBox="0 0 {w} {h}" width="100%" xmlns="http://www.w3.org/2000/svg" '
        f'style="background:{BG};border:1px solid {BORDER};border-radius:6px">'
        f'{grid}{body}{legend}'
        f'<text x="{pad_l}" y="11" font-size="9.5" fill="{MUTED}">{idx[0].date().isoformat()}</text>'
        f'<text x="{w-pad_r}" y="11" font-size="9.5" fill="{MUTED}" text-anchor="end">{idx[-1].date().isoformat()}</text>'
        f'</svg>'
    )


def _svg_bars(rows, w=720, bar_h=22) -> str:
    """Horizontal bars of excess-vs-passive per plan."""
    if not rows:
        return ""
    gap, pad_l, pad_t = 8, 220, 10
    vals = [(r.excess_vs_blended or 0.0) for r in rows]
    mx = max(0.06, max(abs(v) for v in vals))
    zero_x = pad_l + (w - pad_l - 20) * (mx / (2 * mx))
    h = pad_t * 2 + len(rows) * (bar_h + gap)
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" xmlns="http://www.w3.org/2000/svg">']
    for i, r in enumerate(rows):
        y = pad_t + i * (bar_h + gap)
        v = r.excess_vs_blended or 0.0
        bw = (w - pad_l - 20) * (abs(v) / (2 * mx))
        x = zero_x if v >= 0 else zero_x - bw
        col = GOOD if v >= 0 else BAD
        label = f"{r.advisor} · {_tier(r)}"
        out.append(
            f'<text x="{pad_l-8}" y="{y+15}" font-size="11" fill="{TEXT}" text-anchor="end">{html.escape(label)}</text>'
            f'<rect x="{x:.1f}" y="{y}" width="{bw:.1f}" height="{bar_h}" fill="{col}" rx="2"/>'
            f'<text x="{(zero_x+bw+5) if v>=0 else (zero_x+5):.1f}" y="{y+15}" font-size="11" '
            f'fill="{col}" text-anchor="start">{v:+.1%}</text>'
        )
    out.append(f'<line x1="{zero_x}" y1="{pad_t-4}" x2="{zero_x}" y2="{h-pad_t+4}" stroke="{GRID}"/>')
    out.append("</svg>")
    return "".join(out)


def _tier(audit_or_row) -> str:
    return getattr(audit_or_row, "_tier", "") or ""


def _months_between(start_iso: str, end_iso: str) -> float:
    a, b = pd.Timestamp(start_iso), pd.Timestamp(end_iso)
    return (b - a).days / 30.44


def _bt_row(bt, window):
    for r in bt:
        if r.window == window:
            return r
    return None


def _exec_summary(d) -> str:
    """One paragraph, every figure computed."""
    a, fwd = d["audit"], d["fwd"]
    ret = a.recommended_returns["latest"]
    bench = a.benchmark_returns["latest"]
    vb, vp = a.excess_vs_benchmark, a.excess_vs_blended
    mo = _months_between(a.start_date, a.as_of)
    fell = "fell" if bench < 0 else "rose"
    parts = [
        f"Over roughly {mo:.0f} months, this {html.escape(a._tier.lower())} plan turned "
        f"₹{a.invested:,.0f} into ₹{a.recommended_value_now:,.0f} "
        f"({ret:+.1%}), while the Nifty 50 {fell} {abs(bench):.1%}."
    ]
    if vp is not None:
        if vp > 0.02:
            interp = ("a meaningful part of the result came from fund selection, not just "
                      "the asset mix")
        elif vp >= -0.01:
            interp = ("almost all of the result came from the asset mix rather than the "
                      "specific fund picks")
        else:
            interp = ("the specific fund picks actually lagged a cheap index version of the "
                      "same allocation")
        verb = "added" if vp >= 0 else "gave up"
        parts.append(
            f"Measured against a passive twin of the same allocation, the plan {verb} "
            f"{abs(vp):.1%}, which means {interp}."
        )
    if a.excluded_weight > 0:
        parts.append(
            f"{a.excluded_weight:.0%} of the plan (un-priceable assets) was excluded, so these "
            f"figures cover the priced portion only."
        )
    return " ".join(parts)


def _key_insights(d) -> list[str]:
    a, fwd = d["audit"], d["fwd"]
    out = []
    vb, vp = a.excess_vs_benchmark, a.excess_vs_blended
    if vp is not None:
        gap = vb - vp
        out.append(
            f"Beat the Nifty by {vb:+.1%}, but only {vp:+.1%} survived a fair passive comparison. "
            f"About {abs(gap):.1%} of the apparent edge was really asset allocation (holding debt and gold) "
            f"in a falling market, not fund selection."
        )
    out.append(
        f"The advisor's specific weights "
        + ("beat" if a.weighting_added else "did not beat")
        + " an equal-weight version of the same funds."
    )
    b3 = _bt_row(d["backtest"], "3Y")
    if b3 and b3.excess_vs_passive is not None:
        if b3.excess_vs_passive > 0.05 and b3.dropped_weight < 0.2:
            out.append(
                f"Over 3 years the allocation beat its passive twin by {b3.excess_vs_passive:+.1%} "
                f"(only {b3.dropped_weight:.0%} dropped), so the edge is not purely the recent window."
            )
        elif b3.excess_vs_passive <= 0:
            out.append(
                f"Over 3 years the allocation did not beat its passive twin "
                f"({b3.excess_vs_passive:+.1%}), so there is no clear multi-year selection edge."
            )
    out.append(
        f"Realised volatility was {fwd.volatility:.0%} with a maximum drawdown of "
        f"{fwd.max_drawdown:.0%} over the window (Sharpe {fwd.sharpe:.2f})."
    )
    return out


def _caveats(d) -> list[str]:
    a = d["audit"]
    out = []
    mo = _months_between(a.start_date, a.as_of)
    out.append(
        f"This is a {mo:.0f}-month outcome snapshot in a falling market, which flatters "
        f"defensive plans; it is not proof of skill."
    )
    if a.excess_vs_blended is not None:
        out.append(
            "The passive-twin comparison still blends fund selection with a deliberate "
            "mid/small-cap tilt; isolating pure stock-picking needs category-matched benchmarks."
        )
    b5 = _bt_row(d["backtest"], "5Y")
    if b5 and b5.dropped_weight >= 0.2:
        out.append(
            f"The 5-year backtest dropped {b5.dropped_weight:.0%} of the plan (funds that "
            f"launched recently), so its figures rely on partial data."
        )
    if a.excluded_weight >= 0.15:
        out.append(
            f"{a.excluded_weight:.0%} of this plan was un-priceable and excluded, so trust its "
            f"ranking least."
        )
    return out


def _verdict(d) -> str:
    a = d["audit"]
    vp = a.excess_vs_blended
    b3 = _bt_row(d["backtest"], "3Y")
    short = ("selection added value" if (vp is not None and vp > 0.02)
             else "selection roughly matched a passive twin" if (vp is not None and vp >= -0.01)
             else "selection lagged a passive twin")
    if b3 and b3.excess_vs_passive is not None and b3.dropped_weight < 0.2:
        long = (f"over 3 years a selection-plus-tilt edge of {b3.excess_vs_passive:+.1%} is present"
                if b3.excess_vs_passive > 0.05 else
                "over 3 years no clear edge over passive is present")
    else:
        long = "a multi-year read isn't reliable here (insufficient fund history)"
    return (f"Short term, {short}; {long}. Read this as a description of how the plan navigated "
            f"this period, not as a verdict on the advisor.")


# ---------- html assembly --------------------------------------------------

def _fmt_pct(v):
    return "—" if v is None else f"{v:+.1%}"


def build_report(conn: sqlite3.Connection, benchmark=DEFAULT_BENCHMARK, proxies=ASSET_PROXIES) -> str:
    plans = []
    for r in conn.execute("SELECT rec_id, risk_profile FROM recommendations ORDER BY rec_id").fetchall():
        rec = schema.load_recommendation(conn, r["rec_id"])
        data = _plan_series(conn, rec, benchmark, proxies)
        if data is None:
            continue
        data["audit"]._tier = r["risk_profile"]
        plans.append(data)
    if not plans:
        return "<html><body><p>No auditable plans found.</p></body></html>"

    plans.sort(key=lambda d: d["audit"].recommended_returns["latest"], reverse=True)
    bench_ret = plans[0]["audit"].benchmark_returns["latest"]
    as_of = plans[0]["audit"].as_of

    # summary table rows
    trows = ""
    for d in plans:
        a = d["audit"]
        fwd = d["fwd"]
        vp = a.excess_vs_blended
        vp_col = GOOD if (vp or 0) >= 0 else BAD
        vp_sort = "" if vp is None else f"{vp:.6f}"
        data = 1.0 - a.excluded_weight
        ret = a.recommended_returns["latest"]
        rc = GOOD if ret >= 0 else BAD
        vb = a.excess_vs_benchmark
        vbc = GOOD if vb >= 0 else BAD
        ddc = BAD  # drawdowns always shown in red
        trows += (
            f'<tr>'
            f'<td data-sort="{html.escape(a.advisor)}">{html.escape(a.advisor)}</td>'
            f'<td data-sort="{html.escape(a._tier)}">{html.escape(a._tier)}</td>'
            f'<td class="num" data-sort="{a.recommended_value_now:.2f}">₹{a.recommended_value_now:,.0f}</td>'
            f'<td class="num" data-sort="{ret:.6f}" style="color:{rc}">{ret:+.1%}</td>'
            f'<td class="num" data-sort="{vb:.6f}" style="color:{vbc}">{vb:+.1%}</td>'
            f'<td class="num" data-sort="{vp_sort}" style="color:{vp_col};font-weight:600">{_fmt_pct(vp)}</td>'
            f'<td class="num" data-sort="{fwd.volatility:.6f}">{fwd.volatility:.0%}</td>'
            f'<td class="num" data-sort="{fwd.sharpe:.6f}">{fwd.sharpe:.2f}</td>'
            f'<td class="num" data-sort="{fwd.max_drawdown:.6f}" style="color:{ddc}">{fwd.max_drawdown:.0%}</td>'
            f'<td class="num" data-sort="{data:.6f}">{data:.0%}</td>'
            f'</tr>'
        )

    # per-plan detail sections
    sections = ""
    for d in plans:
        a, rec = d["audit"], d["rec"]
        chart = _svg_line({
            "Recommended": (d["recommended"], ACCENT),
            "Passive twin": (d["passive"], PASSIVE),
            "Nifty 50": (d["nifty"], BENCH),
        })
        funds = "".join(
            f'<li>{html.escape(f.display_name)} '
            f'<span class="muted">({f.weight:.0%}{"" if f.included and f.scheme_code else " · excluded"})</span></li>'
            for f in rec.funds
        )
        btrows = "".join(
            f'<tr><td>{b.window}</td><td>{b.start}</td><td class="num">{b.plan_return:+.1%}</td>'
            f'<td class="num">{b.plan_sharpe:.2f}</td><td class="num">{b.plan_maxdd:.1%}</td>'
            f'<td class="num">{_fmt_pct(b.excess_vs_passive)}</td><td class="num">{b.dropped_weight:.0%}</td></tr>'
            for b in d["backtest"]
        )
        insights = "".join(f"<li>{html.escape(s)}</li>" for s in _key_insights(d))
        caveats = "".join(f"<li>{html.escape(s)}</li>" for s in _caveats(d))
        sections += f"""
        <section class="card">
          <h3>{html.escape(a.advisor)} · {html.escape(a._tier)}</h3>
          <p class="summary">{html.escape(_exec_summary(d))}</p>
          <div class="grid">
            <div>{chart}</div>
            <div>
              <p class="muted" style="margin:0 0 6px">Holdings</p>
              <ul class="funds">{funds}</ul>
            </div>
          </div>
          <p class="muted" style="margin:14px 0 4px">Historical backtest · allocation over past windows</p>
          <table class="mini"><thead><tr><th>Window</th><th>From</th><th>Return</th>
          <th>Sharpe</th><th>MaxDD</th><th>vs Passive</th><th>Dropped</th></tr></thead>
          <tbody>{btrows}</tbody></table>
          <div class="cols">
            <div><h4>Key insights</h4><ul>{insights}</ul></div>
            <div><h4>Methodological caveats</h4><ul>{caveats}</ul></div>
          </div>
          <p class="verdict"><b>Verdict.</b> {html.escape(_verdict(d))}</p>
        </section>"""

    bars = _svg_bars([d["audit"] for d in plans])
    today = date.today().isoformat()

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MFRIP · Recommendation Audit</title>
<style>
  * {{ box-sizing:border-box; }}
  body {{ font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
         color:{TEXT}; margin:0; background:{BG}; line-height:1.45;
         border-top:2px solid {ACCENT}; }}
  .wrap {{ max-width:1020px; margin:0 auto; padding:0 18px 56px; }}
  header {{ border-bottom:1px solid {BORDER}; padding:16px 0 12px; margin-bottom:6px;
           display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; }}
  header h1 {{ color:{TEXT}; margin:0; font-size:19px; font-weight:600; letter-spacing:.02em; }}
  header .tag {{ color:{BG}; background:{ACCENT}; font-weight:700; font-size:11px;
               letter-spacing:.16em; padding:3px 8px; border-radius:2px; }}
  header p {{ color:{MUTED}; margin:0; font-size:12px;
            font-family:'SF Mono','Roboto Mono',Consolas,monospace; }}
  .num, td.num, th.num {{ text-align:right;
         font-family:'SF Mono','Roboto Mono',Consolas,'Courier New',monospace;
         font-variant-numeric:tabular-nums; letter-spacing:-.02em; }}
  .card {{ background:{PANEL}; border:1px solid {BORDER}; border-radius:3px;
          padding:14px 16px; margin:12px 0; }}
  table {{ border-collapse:collapse; width:100%; font-size:12.5px; }}
  th {{ background:transparent; color:{ACCENT}; text-align:left; padding:6px 10px;
       font-weight:600; font-size:10px; text-transform:uppercase; letter-spacing:.08em;
       border-bottom:1px solid {ACCENT}33; }}
  td {{ padding:6px 10px; border-bottom:1px solid {GRID}; }}
  tbody tr:hover {{ background:#191d25; }}
  tbody tr:last-child td {{ border-bottom:none; }}
  .mini th {{ color:{MUTED}; border-bottom:1px solid {GRID}; }}
  .mini td {{ font-size:12px; color:{TEXT}; }}
  .grid {{ display:grid; grid-template-columns:1.7fr 1fr; gap:16px; align-items:start; }}
  .funds {{ margin:0; padding-left:15px; font-size:12px; color:{TEXT}; }}
  .funds li {{ margin:1px 0; }}
  .muted {{ color:{MUTED}; font-size:12px; }}
  h2 {{ color:{ACCENT}; font-size:13px; text-transform:uppercase; letter-spacing:.08em; }}
  h3 {{ color:{ACCENT}; margin:0 0 8px; font-size:13px; text-transform:uppercase; letter-spacing:.05em; }}
  h4 {{ color:{MUTED}; margin:0 0 5px; font-size:10px; text-transform:uppercase; letter-spacing:.08em; }}
  .summary {{ font-size:13px; color:{TEXT}; background:{BG}; border-left:2px solid {ACCENT};
             padding:10px 13px; border-radius:0 3px 3px 0; margin:0 0 12px; }}
  .cols {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:12px; }}
  .cols ul {{ margin:0; padding-left:15px; font-size:12px; color:{TEXT}; }} .cols li {{ margin:3px 0; }}
  .verdict {{ margin:12px 0 0; padding:10px 13px; background:#191510;
             border:1px solid {ACCENT}40; border-left:2px solid {ACCENT};
             border-radius:0 3px 3px 0; font-size:13px; color:{TEXT}; }}
  #summary th {{ cursor:pointer; user-select:none; }}
  #summary th:hover {{ color:{TEXT}; }}
  .note {{ background:#15120c; border:1px solid {ACCENT}33; border-radius:3px;
          padding:13px 16px; font-size:12px; color:#b59a6a; }}
  b {{ color:{TEXT}; }} .verdict b, .note b {{ color:{ACCENT}; }}
  @media(max-width:680px) {{ .grid,.cols {{ grid-template-columns:1fr; }} }}
</style></head><body><div class="wrap">
  <header>
    <span class="tag">MFRIP</span>
    <h1>Recommendation Audit</h1>
    <p>Warikoo "Invest in 2026" panel · 9 plans · as of {as_of} · generated {today}</p>
  </header>

  <div class="card">
    <h3>How every plan fared</h3>
    <p class="muted">Forward audit since the recommendation date. Nifty 50 returned
    {bench_ret:+.1%} over the window. <b>"vs Passive"</b> compares each plan to the
    <i>same allocation built from index funds</i>, the fairer measure of fund-selection skill.
    <span class="muted">Click any column header to sort.</span></p>
    <table id="summary"><thead><tr>
    <th>Advisor</th><th>Tier</th><th>Value now</th><th>Return</th>
    <th>vs Nifty</th><th>vs Passive</th><th>Vol</th><th>Sharpe</th><th>MaxDD</th><th>Data</th>
    </tr></thead><tbody>{trows}</tbody></table>
  </div>

  <div class="card">
    <h3>Fund-selection skill (excess over passive twin)</h3>
    {bars}
  </div>

  <h2 style="margin:26px 0 2px;border-top:1px solid {BORDER};padding-top:20px">Plan-by-plan detail</h2>
  {sections}

  <div class="note">
    <b>Methodology &amp; honest caveats.</b> Direct-Growth plans, point-in-time NAVs, no
    lookahead. The passive twin uses index-fund proxies for equity/debt/gold at the plan's
    own weights. A ~7-month window in a falling market flatters defensive plans, so the
    forward audit is an outcome snapshot, not proof of skill. "vs Passive" still blends
    fund-selection with deliberate mid/small-cap tilt; isolating pure stock-picking would
    need category-matched benchmarks. Backtest rows with high "Dropped" rely on partial
    data (funds that launched recently). Un-priceable sleeves (FDs, direct bonds, REITs)
    are excluded and shown in "Data" (completeness = 100% − excluded).
  </div>
</div>
<script>
(function(){{
  var tbl = document.getElementById('summary');
  if(!tbl) return;
  var ths = tbl.tHead.rows[0].cells, sortState = {{}};
  for(var i=0;i<ths.length;i++){{
    (function(col){{
      ths[col].addEventListener('click', function(){{
        var body = tbl.tBodies[0], rows = Array.prototype.slice.call(body.rows);
        var asc = !sortState[col]; sortState = {{}}; sortState[col] = asc;
        rows.sort(function(a,b){{
          var x = a.cells[col].getAttribute('data-sort'); if(x===null) x = a.cells[col].innerText;
          var y = b.cells[col].getAttribute('data-sort'); if(y===null) y = b.cells[col].innerText;
          var nx = parseFloat(x), ny = parseFloat(y);
          if(!isNaN(nx) && !isNaN(ny)){{ return asc ? nx-ny : ny-nx; }}
          return asc ? String(x).localeCompare(y) : String(y).localeCompare(x);
        }});
        rows.forEach(function(r){{ body.appendChild(r); }});
      }});
    }})(i);
  }}
}})();
</script>
</body></html>"""
