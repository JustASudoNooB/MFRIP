"""Professional, interactive Plotly charts in a clean, light, screener-style palette.

Shared so the Streamlit app and any future surface render identical-looking
charts. All figures are light, indigo-accented, with hover and zoom.
"""
from __future__ import annotations

import pandas as pd

BG = "#F2EFE8"
PANEL = "#EBE6DB"
GRID = "#E4DDD0"
TEXT = "#17150F"
MUTED = "#7A7264"
AMBER = "#D9730D"  # primary line (deep amber)
CYAN = "#0F766E"  # teal (second voice)
GRAY = "#8D8677"
GREEN = "#147A52"
RED = "#C2452D"

# colour cycle for multi-series (portfolio comparison etc.)
SERIES = [AMBER, CYAN, "#7A6FB3", "#147A52", "#C2452D", "#4C7A9B"]


def _base(fig, height=340, ytitle=""):
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(color=TEXT, size=12, family="Inter, Segoe UI, sans-serif"),
        margin=dict(l=8, r=10, t=10, b=8), height=height,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0,
                    bgcolor="rgba(0,0,0,0)", font=dict(size=11, color=MUTED)),
        xaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID,
                   showspikes=True, spikecolor=MUTED, spikethickness=1, spikemode="across"),
        yaxis=dict(gridcolor=GRID, zerolinecolor=GRID, linecolor=GRID, title=ytitle),
    )
    return fig


def calendar_year_chart(cy, height=300):
    """Year-on-year (calendar-year) returns as coloured bars: green up, red down.
    `cy` is the list of (year, return, is_partial) from calendar_year_returns."""
    import plotly.graph_objects as go
    years = [str(y) for (y, r, p) in cy]
    vals = [r * 100 for (y, r, p) in cy]
    colors = [GREEN if v >= 0 else RED for v in vals]
    labels = [f"{v:+.1f}%" + ("*" if p else "") for (v, (y, r, p)) in zip(vals, cy)]
    fig = go.Figure(go.Bar(
        x=years, y=vals, marker_color=colors, text=labels, textposition="outside",
        cliponaxis=False, hovertemplate="%{x}: %{y:+.1f}%<extra></extra>"))
    _base(fig, height, ytitle="")
    fig.update_layout(hovermode="x")
    fig.update_yaxes(ticksuffix="%", zeroline=True, zerolinecolor=MUTED)
    fig.update_xaxes(title="calendar year", type="category")
    return fig


def growth_chart(series: dict[str, pd.Series], height=340):
    """Lines. A single series is coloured by direction (green up / red down);
    multiple series get distinct colours (amber, cyan, …) with amber filled."""
    import plotly.graph_objects as go
    fig = go.Figure()
    items = [(k, v) for k, v in series.items() if v is not None and len(v.dropna()) > 1]
    single = len(items) == 1
    for i, (label, s) in enumerate(items):
        s = s.dropna()
        if single:
            up = float(s.iloc[-1]) >= float(s.iloc[0])
            colour = GREEN if up else RED
            fillc = "rgba(20,122,82,0.13)" if up else "rgba(194,69,45,0.13)"
            filled = True
        else:
            colour = AMBER if i == 0 else (CYAN if i == 1 else SERIES[i % len(SERIES)])
            fillc = "rgba(217,115,13,0.10)"
            filled = (i == 0)
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values, name=label, mode="lines",
            line=dict(color=colour, width=1.8 if (single or i == 0) else 1.4),
            fill="tozeroy" if filled else None,
            fillcolor=fillc if filled else None,
            hovertemplate="₹%{y:,.0f}<extra>" + label + "</extra>",
        ))
    _base(fig, height)
    lo = min(float(s.dropna().min()) for _, s in items)
    fig.update_yaxes(range=[lo * 0.985, None], tickprefix="₹", tickformat=",.0f")
    return fig


def skill_bars(rows: list[tuple[str, float]], height=None):
    """Horizontal diverging bars (green positive, red negative)."""
    import plotly.graph_objects as go
    labels = [r[0] for r in rows][::-1]
    vals = [r[1] for r in rows][::-1]
    colours = [GREEN if v >= 0 else RED for v in vals]
    fig = go.Figure(go.Bar(
        x=vals, y=labels, orientation="h", marker_color=colours,
        text=[f"{v:+.1%}" for v in vals], textposition="outside",
        textfont=dict(color=TEXT, size=11),
        hovertemplate="%{x:+.1%}<extra>%{y}</extra>",
    ))
    _base(fig, height or max(220, 38 * len(rows)))
    fig.update_xaxes(tickformat="+.0%", zeroline=True, zerolinecolor=MUTED)
    fig.update_layout(hovermode="closest")
    return fig


def allocation_pie(labels, weights, title="", height=230):
    """Donut of portfolio weights, dark theme with the shared colour cycle."""
    import plotly.graph_objects as go
    cols = [SERIES[i % len(SERIES)] for i in range(len(labels))]
    fig = go.Figure(go.Pie(
        labels=labels, values=weights, hole=0.56, sort=False,
        marker=dict(colors=cols, line=dict(color=BG, width=2)),
        textinfo="percent", textfont=dict(size=11, color="#ffffff"),
        hovertemplate="%{label}: %{percent}<extra></extra>",
    ))
    fig.update_layout(
        template="plotly_white", paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(color=TEXT, size=11), margin=dict(l=4, r=4, t=26, b=4),
        height=height, showlegend=False,
        title=dict(text=title, font=dict(size=12, color=AMBER), x=0.5, xanchor="center"),
    )
    return fig


def correlation_heat(matrix: pd.DataFrame, height=340):
    import plotly.graph_objects as go
    fig = go.Figure(go.Heatmap(
        z=matrix.values, x=list(matrix.columns), y=list(matrix.index),
        colorscale=[[0, RED], [0.5, PANEL], [1, GREEN]], zmid=0, zmin=-1, zmax=1,
        text=[[f"{v:.2f}" for v in row] for row in matrix.values],
        texttemplate="%{text}", textfont=dict(size=12, color=TEXT),
        colorbar=dict(outlinecolor=GRID, tickcolor=MUTED, tickfont=dict(color=MUTED)),
        hovertemplate="%{y} vs %{x}: %{z:.2f}<extra></extra>",
    ))
    _base(fig, height)
    return fig


def validation_scatter(df, ycol: str, ylabel: str, rho=None, height=340,
                       higher_is_better=True):
    """Scatter of in-sample composite score (x) vs a realised out-of-sample metric
    (y), pooled across funds and windows, with a dotted linear trend line."""
    import plotly.graph_objects as go
    import numpy as np
    x = df["score"].to_numpy(float)
    y = df[ycol].to_numpy(float)
    keep = ~(np.isnan(x) | np.isnan(y))
    x, y = x[keep], y[keep]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="markers", name="each fund, each window",
        marker=dict(color=AMBER, size=7, opacity=0.55, line=dict(width=0)),
        hovertemplate="score %{x:.0f} · " + ylabel + " %{y:.2f}<extra></extra>"))
    if len(x) >= 3 and np.ptp(x) > 1e-9:
        b1, b0 = np.polyfit(x, y, 1)
        xs = np.array([x.min(), x.max()])
        fig.add_trace(go.Scatter(
            x=xs, y=b0 + b1 * xs, mode="lines", name="trend",
            line=dict(color=CYAN, width=2, dash="dot"), hoverinfo="skip"))
    _base(fig, height, ytitle=ylabel)
    fig.update_xaxes(title="in-sample composite score (higher = ranked better)")
    if rho is not None and rho == rho:
        fig.add_annotation(x=0.02, y=0.98, xref="paper", yref="paper", xanchor="left",
                           yanchor="top", text=f"rank correlation ρ = {rho:+.2f}",
                           showarrow=False, font=dict(color=TEXT, size=12),
                           bgcolor="rgba(0,0,0,0.35)", borderpad=4)
    return fig


def montecarlo_fan(sim: dict, height=360):
    """Probability fan of a SIP's future corpus from Monte Carlo simulation.
    Shaded 10th-90th and 25th-75th percentile bands, a median line, the dotted
    'you invest' line, and an optional goal line."""
    import plotly.graph_objects as go
    x = sim["time_years"]
    b = sim["bands"]
    AMBER_LO = "rgba(217,115,13,0.12)"
    AMBER_MID = "rgba(217,115,13,0.24)"
    EDGE = "rgba(217,115,13,0.45)"
    fig = go.Figure()
    # 10th-90th band (lower boundary first, then fill up to it)
    fig.add_trace(go.Scatter(x=x, y=b[10], mode="lines", name="10th percentile",
        line=dict(width=0.8, color=EDGE), hovertemplate="10th ₹%{y:,.0f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=x, y=b[90], mode="lines", name="90th percentile",
        line=dict(width=0.8, color=EDGE), fill="tonexty", fillcolor=AMBER_LO,
        hovertemplate="90th ₹%{y:,.0f}<extra></extra>"))
    # 25th-75th band (drawn on top, more opaque); boundaries hidden from hover
    fig.add_trace(go.Scatter(x=x, y=b[25], mode="lines", line=dict(width=0, color="rgba(0,0,0,0)"),
        showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=b[75], mode="lines", name="25th-75th (likeliest half)",
        line=dict(width=0, color="rgba(0,0,0,0)"), fill="tonexty", fillcolor=AMBER_MID,
        hoverinfo="skip"))
    # median
    fig.add_trace(go.Scatter(x=x, y=b[50], mode="lines", name="Median outcome",
        line=dict(color=AMBER, width=2.6), hovertemplate="Median ₹%{y:,.0f}<extra></extra>"))
    # amount invested
    fig.add_trace(go.Scatter(x=x, y=sim["invested"], mode="lines", name="You invest",
        line=dict(color=MUTED, width=1.4, dash="dot"),
        hovertemplate="You invest ₹%{y:,.0f}<extra></extra>"))
    if sim.get("target"):
        fig.add_hline(y=sim["target"], line=dict(color=GREEN, width=1.3, dash="dash"),
                      annotation_text="your goal", annotation_position="top left",
                      annotation_font_color=GREEN)
    _base(fig, height, ytitle="")
    fig.update_yaxes(tickprefix="₹", tickformat=",.0f")
    fig.update_xaxes(title="years", ticksuffix="y")
    return fig


def goal_projection_chart(monthly: float, years: float,
                          rates=(0.08, 0.10, 0.12), height=320):
    import plotly.graph_objects as go
    n = int(round(years * 12))
    months = list(range(0, n + 1))
    xs = [m / 12 for m in months]
    fig = go.Figure()
    invested = [monthly * m for m in months]
    fig.add_trace(go.Scatter(
        x=xs, y=invested, name="You invest", mode="lines",
        line=dict(color=MUTED, width=1.4, dash="dot"),
        hovertemplate="Year %{x:.0f}: ₹%{y:,.0f} put in<extra></extra>"))
    palette = [GREEN, AMBER, CYAN, "#7A6FB3"]
    for i, r in enumerate(sorted(rates)):
        mr = (1.0 + r) ** (1.0 / 12) - 1.0
        corpus = [monthly * (((1 + mr) ** m - 1) / mr) * (1 + mr) if m > 0 else 0.0 for m in months]
        fig.add_trace(go.Scatter(
            x=xs, y=corpus, name=f"{r:.0%}/yr", mode="lines",
            line=dict(color=palette[i % len(palette)], width=2),
            hovertemplate=f"{r:.0%}/yr · year %{{x:.0f}}: ₹%{{y:,.0f}}<extra></extra>"))
    _base(fig, height, ytitle="")
    fig.update_yaxes(tickprefix="₹", tickformat=",.0f")
    fig.update_xaxes(title="years", ticksuffix="y")
    return fig


def stress_chart(episodes: list[dict], height=None):
    """Horizontal bars of each stress episode's return (red down / green up),
    with a sensible x-range so small moves look small and big crashes extend."""
    import plotly.graph_objects as go
    eps = episodes[::-1]
    labels = [e["name"] for e in eps]
    rets = [e["return"] for e in eps]
    colours = [GREEN if v >= 0 else RED for v in rets]
    fig = go.Figure(go.Bar(
        x=rets, y=labels, orientation="h", marker_color=colours,
        text=[f"{v:+.1%}" for v in rets], textposition="outside",
        textfont=dict(color=TEXT, size=12), width=0.5,
        customdata=[e["drawdown"] for e in eps],
        hovertemplate="%{y}<br>return %{x:+.1%}<br>worst drawdown %{customdata:.1%}<extra></extra>"))
    lo, hi = min(rets + [0.0]), max(rets + [0.0])
    left = min(lo * 1.3, -0.06)
    right = max(hi * 1.3, 0.04)
    _base(fig, height or max(150, 70 * len(eps)))
    fig.update_xaxes(tickformat=".1%", range=[left, right], zeroline=True,
                     zerolinecolor=MUTED, nticks=7)
    fig.update_layout(hovermode="closest", bargap=0.4)
    return fig


def rolling_range_chart(rows: list[dict], height=None):
    """A dumbbell per window: the worst rolling return (red) and best (green) with
    the average (amber diamond) between them, every point labelled. Reads as
    'depending on timing, your N-year return swung between X and Y'."""
    import plotly.graph_objects as go
    rows = rows[::-1]
    labels = [r["window"] for r in rows]
    fig = go.Figure()
    for r in rows:                                   # connector lines
        fig.add_trace(go.Scatter(
            x=[r["worst"], r["best"]], y=[r["window"], r["window"]], mode="lines",
            line=dict(color="#D8D0C0", width=5), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=[r["worst"] for r in rows], y=labels, mode="markers+text",
        marker=dict(color=RED, size=14, line=dict(color=BG, width=1)),
        text=[f"{r['worst']:+.0%}" for r in rows], textposition="middle left",
        textfont=dict(color=RED, size=12), name="worst",
        hovertemplate="%{y}: worst %{x:+.1%}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=[r["best"] for r in rows], y=labels, mode="markers+text",
        marker=dict(color=GREEN, size=14, line=dict(color=BG, width=1)),
        text=[f"{r['best']:+.0%}" for r in rows], textposition="middle right",
        textfont=dict(color=GREEN, size=12), name="best",
        hovertemplate="%{y}: best %{x:+.1%}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=[r["avg"] for r in rows], y=labels, mode="markers",
        marker=dict(color=AMBER, size=14, symbol="diamond", line=dict(color=BG, width=1)),
        name="average", hovertemplate="%{y}: average %{x:+.1%}<extra></extra>"))
    allx = [v for r in rows for v in (r["worst"], r["best"])]
    lo, hi = min(allx), max(allx)
    pad = max(0.04, (hi - lo) * 0.22)
    _base(fig, height or max(170, 78 * len(rows)))
    fig.update_xaxes(tickformat=".0%", range=[lo - pad, hi + pad], zeroline=True,
                     zerolinecolor=MUTED, title="annualised return")
    fig.update_yaxes(title="")
    fig.update_layout(hovermode="closest")
    return fig
