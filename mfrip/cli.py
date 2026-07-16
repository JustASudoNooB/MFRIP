"""MFRIP command-line interface.

    python -m mfrip.cli sync-schemes
    python -m mfrip.cli resolve "HDFC Top 100"
    python -m mfrip.cli fetch 118550 120716
    python -m mfrip.cli snapshot 118550 --as-of 2023-06-30 --benchmark 120716

The first three need network (your machine). `snapshot` works fully offline
on whatever is already cached.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import ingest
from .config import DEFAULT_CONFIG, Config
from .metrics.snapshot import build_snapshot
from .portfolio.audit import run_audit
from .recommend import loader, schema
from .sources import mfapi
from .store import nav_store

DEFAULT_BENCHMARK = 120716  # UTI Nifty 50 Index Fund - Direct - Growth (TRI proxy)


def _cmd_sync_schemes(args) -> int:
    conn = ingest.open_store()
    n = ingest.sync_scheme_master(conn)
    print(f"Synced {n} schemes into {DEFAULT_CONFIG.db_path}")
    return 0


def _cmd_resolve(args) -> int:
    hits = mfapi.search_schemes(args.query)
    if not hits:
        print("No matches.")
        return 1
    for h in hits[: args.limit]:
        print(f"{h['schemeCode']:>9}  {h['schemeName']}")
    return 0


def _cmd_fetch(args) -> int:
    conn = ingest.open_store()
    results = ingest.ingest_many(conn, [int(c) for c in args.codes], force=args.force)
    for code, n in results.items():
        print(f"{code}: {n} NAV rows cached")
    return 0


def _cmd_seed_universe(args) -> int:
    from . import universe
    conn = ingest.open_store()
    n_schemes = conn.execute("SELECT COUNT(*) FROM schemes").fetchone()[0]
    if n_schemes == 0:
        print("Scheme master is empty; downloading it first (one time)...")
        ingest.sync_scheme_master(conn)
    out = universe.build_universe(conn, target=args.target, delay=args.delay)
    conn.execute("VACUUM")
    print(f"Done. {out['total_cached']} funds now cached "
          f"({out['downloaded']} downloaded, {out['failed']} failed, "
          f"{out['dropped_stale']} stale plans dropped).")
    print("Next: commit the updated mfrip_data.db with GitHub Desktop and push.")
    return 0


def _cmd_snapshot(args) -> int:
    conn = ingest.open_store()
    nav = nav_store.load_nav(conn, int(args.code))
    if nav.empty:
        print(f"No cached NAV for {args.code}. Run: fetch {args.code}", file=sys.stderr)
        return 1
    bench = None
    if args.benchmark:
        bench = nav_store.load_nav(conn, int(args.benchmark))
        if bench.empty:
            print(f"No cached NAV for benchmark {args.benchmark}.", file=sys.stderr)
            return 1

    cfg = Config(rf_annual=args.rf) if args.rf is not None else DEFAULT_CONFIG
    as_of = args.as_of or str(nav.index[-1].date())
    snap = build_snapshot(nav, as_of, benchmark=bench, config=cfg, scheme_code=str(args.code))
    print(json.dumps(snap.to_dict(), indent=2, default=str))
    return 0


def _cmd_load_rec(args) -> int:
    conn = ingest.open_store()
    rec = loader.parse_yaml(args.yaml)
    report = loader.auto_resolve(conn, rec)
    rec_id = schema.save_recommendation(conn, rec)
    print(f"Saved recommendation #{rec_id}: {rec.advisor} ({rec.risk_profile}), {rec.rec_date}\n")
    print("Resolved funds (check these, fix wrong ones with `rec-fix`):")
    for f, cands in report:
        if not f.included:
            print(f"  [excluded] {f.display_name}")
            continue
        print(f"  {f.weight:6.1%}  {f.display_name}")
        print(f"           -> {f.scheme_code}  {f.resolved_name}")
        for c in cands[1:3]:
            print(f"              alt: {c.scheme_code}  {c.scheme_name}")
    print(f"\nNext: python -m mfrip.cli fetch-rec {rec_id}")
    return 0


def _cmd_rec_show(args) -> int:
    conn = ingest.open_store()
    rec = schema.load_recommendation(conn, int(args.rec_id))
    print(f"#{rec.rec_id} {rec.advisor} ({rec.risk_profile}) via {rec.creator}, {rec.rec_date}")
    for f in rec.funds:
        flag = "" if f.included else " [excluded]"
        print(f"  {f.weight:6.1%}  {f.scheme_code}  {f.resolved_name or f.display_name}{flag}")
    return 0


def _cmd_rec_fix(args) -> int:
    conn = ingest.open_store()
    meta, _ = mfapi.fetch_nav_history(args.code)  # confirm code exists, grab name
    name = meta.get("scheme_name", str(args.code))
    schema.update_fund_resolution(conn, int(args.rec_id), args.display_name, int(args.code), name)
    print(f"Set '{args.display_name}' -> {args.code} ({name})")
    return 0


def _cmd_fetch_rec(args) -> int:
    conn = ingest.open_store()
    rec = schema.load_recommendation(conn, int(args.rec_id))
    codes = [f.scheme_code for f in rec.funds if f.included and f.scheme_code]
    codes.append(int(args.benchmark))
    print(f"Fetching {len(codes)} NAV histories...")
    results = ingest.ingest_many(conn, codes, force=args.force)
    for code, n in results.items():
        print(f"  {code}: {n} rows")
    return 0


def _audit_one(conn, rec_id: int, benchmark: int, proxies=None):
    """Build an AuditResult for a stored recommendation, or None if unrunnable."""
    from .config import ASSET_PROXIES
    proxies = proxies or ASSET_PROXIES
    rec = schema.load_recommendation(conn, int(rec_id))
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
        return None, rec, missing
    bench = nav_store.load_nav(conn, int(benchmark))
    if bench.empty:
        return None, rec, missing
    from .portfolio.benchmark import build_blended_benchmark
    blended = build_blended_benchmark(conn, rec, rec.rec_date, rec.total_amount, proxies)
    blended_value = blended.value if blended is not None else None
    result = run_audit(
        nav_by_code, weights, bench, start=rec.rec_date,
        amount=rec.total_amount, rec_id=rec.rec_id, advisor=rec.advisor,
        blended_value=blended_value,
    )
    return result, rec, missing


def _cmd_advise(args) -> int:
    from .advisor import (DebtLoad, DrawdownReaction, EmergencyFund, Employment,
                          Experience, InvestorProfile)
    from .advisor.recommend import format_text, recommend
    emp = {"stable": Employment.SALARIED_STABLE, "private": Employment.SALARIED_PRIVATE,
           "self": Employment.SELF_EMPLOYED, "business": Employment.BUSINESS,
           "retired": Employment.RETIRED, "student": Employment.STUDENT,
           "unemployed": Employment.UNEMPLOYED}
    ef = {"none": EmergencyFund.NONE, "3m": EmergencyFund.UPTO_3M,
          "6m": EmergencyFund.THREE_TO_6M, "6m+": EmergencyFund.SIX_PLUS}
    dl = {"none": DebtLoad.NONE, "low": DebtLoad.LOW, "moderate": DebtLoad.MODERATE,
          "high": DebtLoad.HIGH}
    rx = {"sell": DrawdownReaction.SELL_ALL, "wait": DrawdownReaction.WAIT,
          "invest": DrawdownReaction.INVEST_MORE, "sip": DrawdownReaction.INCREASE_SIP}
    profile = InvestorProfile(
        age=args.age, horizon_years=args.horizon, employment=emp[args.employment],
        emergency_fund=ef[args.emergency], debt=dl[args.debt],
        drawdown_reaction=rx[args.reaction], experience=Experience(args.experience),
    )
    conn = ingest.open_store()
    rec = recommend(conn, profile, benchmark_code=args.benchmark)
    print(format_text(rec))
    return 0


def _cmd_research(args) -> int:
    from .webapp.research import recommendation_report, render_html
    conn = ingest.open_store()
    rep = recommendation_report(conn, args.rec_id, benchmark=args.benchmark,
                                proxies=_proxies_from_args(args))
    if rep is None:
        print(f"Cannot build research for #{args.rec_id} (missing data).", file=sys.stderr)
        return 1
    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(render_html(rep))
    print(f"Wrote {args.output}. Double-click to open the research memo.")
    return 0


def _cmd_report(args) -> int:
    from .webapp.report import build_report
    conn = ingest.open_store()
    html = build_report(conn, benchmark=args.benchmark, proxies=_proxies_from_args(args))
    out = args.output
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"Wrote {out} ({len(html):,} bytes). Double-click it to open in your browser.")
    return 0


def _proxies_from_args(args) -> dict:
    from .config import ASSET_PROXIES
    p = dict(ASSET_PROXIES)
    if getattr(args, "equity_proxy", None):
        p["equity"] = int(args.equity_proxy)
    if getattr(args, "debt_proxy", None):
        p["debt"] = int(args.debt_proxy)
    if getattr(args, "gold_proxy", None):
        p["gold"] = int(args.gold_proxy)
    return p


def _cmd_audit(args) -> int:
    conn = ingest.open_store()
    result, rec, missing = _audit_one(conn, args.rec_id, args.benchmark, _proxies_from_args(args))
    if result is None:
        print(f"Cannot audit #{args.rec_id}: missing NAV for {missing or 'benchmark'}. "
              f"Run fetch-rec first.", file=sys.stderr)
        return 1
    print(json.dumps(result.to_dict(), indent=2, default=str))
    return 0


def _cmd_load_all(args) -> int:
    import glob
    conn = ingest.open_store()
    paths = sorted(glob.glob(os.path.join(args.folder, "*.yaml")))
    if not paths:
        print(f"No YAML files in {args.folder}", file=sys.stderr)
        return 1
    print(f"Loading {len(paths)} recommendation files...\n")
    for p in paths:
        rec = loader.parse_yaml(p)
        loader.auto_resolve(conn, rec)
        rid = schema.save_recommendation(conn, rec)
        priced = [f for f in rec.funds if f.included and f.scheme_code]
        unresolved = [f.display_name for f in rec.funds if f.included and not f.scheme_code]
        print(f"  #{rid:<2} {rec.advisor} ({rec.risk_profile}): {len(priced)} funds resolved"
              + (f", UNRESOLVED: {unresolved}" if unresolved else ""))
    print("\nReview resolutions with `rec-show <id>`; fix any with `rec-fix`.\n"
          "Then: fetch-all  ->  audit-all")
    return 0


def _cmd_fetch_all(args) -> int:
    conn = ingest.open_store()
    codes: set[int] = set()
    for r in conn.execute("SELECT rec_id FROM recommendations").fetchall():
        rec = schema.load_recommendation(conn, r["rec_id"])
        codes.update(f.scheme_code for f in rec.funds if f.included and f.scheme_code)
    codes.add(int(args.benchmark))
    todo = [c for c in sorted(codes) if args.force or not nav_store.has_nav(conn, c)]
    print(f"{len(codes)} unique funds across all plans; {len(todo)} need downloading.")
    results = ingest.ingest_many(conn, todo, sleep=0.4, force=args.force)
    ok = sum(1 for n in results.values() if n > 0)
    still = [c for c in todo if nav_store.load_nav(conn, c).empty]
    print(f"Downloaded {ok}/{len(todo)}." + (f" Still empty (retry fetch-all): {still}" if still else " All present."))
    return 0


def _cmd_audit_all(args) -> int:
    conn = ingest.open_store()
    proxies = _proxies_from_args(args)
    rows = []
    for r in conn.execute("SELECT rec_id FROM recommendations ORDER BY rec_id").fetchall():
        result, rec, missing = _audit_one(conn, r["rec_id"], args.benchmark, proxies)
        if result is None:
            print(f"  (skipped #{r['rec_id']} {rec.advisor} {rec.risk_profile}: missing data)")
            continue
        rows.append(result)
    if not rows:
        print("Nothing auditable yet. Run load-all then fetch-all.", file=sys.stderr)
        return 1

    bench_latest = rows[0].benchmark_returns["latest"]
    rows.sort(key=lambda x: x.recommended_returns["latest"], reverse=True)
    print(f"\nForward audit since recommendation date, vs Nifty 50 ({bench_latest:+.1%})")
    print("'vs Passive' = excess over the SAME allocation built from index funds "
          "(i.e. fund-picking skill).\n")
    print(f"{'Advisor':<22}{'Tier':<22}{'Value now':>13}{'Return':>9}{'vs Nifty':>10}{'vs Passive':>12}{'Excl%':>7}")
    print("-" * 95)
    for x in rows:
        vp = f"{x.excess_vs_blended:+.1%}" if x.excess_vs_blended is not None else "—"
        print(f"{x.advisor[:20]:<22}{(x.rec_id and _tier(conn, x.rec_id))[:20]:<22}"
              f"{x.recommended_value_now:>13,.0f}{x.recommended_returns['latest']:>9.1%}"
              f"{x.excess_vs_benchmark:>+10.1%}{vp:>12}{x.excluded_weight:>7.0%}")
    print("\nNote: a falling market favours defensive (lower-equity) plans; 7 months is an\n"
          "outcome snapshot, not proof of skill. 'vs Passive' is the fairer skill measure.")
    return 0


def _tier(conn, rec_id: int) -> str:
    r = conn.execute("SELECT risk_profile FROM recommendations WHERE rec_id=?", (rec_id,)).fetchone()
    return r["risk_profile"] if r else ""


def _review_flag(asset_class: str, name: str, category: str) -> str | None:
    """Heuristic: does this resolved fund look wrong for the slot it's in?"""
    low = f"{name} {category}".lower()
    ac = (asset_class or "").lower()
    for kw in ("global", "us equity", "us bluechip", "overnight", "liquid fund", "interval"):
        if kw in low:
            return f"looks like a '{kw}' fund"
    if ac == "equity":
        for kw in ("arbitrage", "fund of fund", " fof", "g-sec", "gilt", " bond",
                   "money market", "hybrid", "balanced", "debt index"):
            if kw in low:
                return f"equity slot but resembles '{kw.strip()}'"
    if ac == "gold" and "gold" not in low:
        return "gold slot but name lacks 'gold'"
    return None


def _cmd_verify(args) -> int:
    conn = ingest.open_store()
    recs = conn.execute(
        "SELECT rec_id, advisor, risk_profile FROM recommendations ORDER BY rec_id"
    ).fetchall()
    flags = []
    for r in recs:
        funds = conn.execute(
            """SELECT rf.display_name, rf.scheme_code, rf.resolved_name, rf.weight,
                      rf.asset_class, rf.included, s.scheme_category
               FROM recommendation_funds rf
               LEFT JOIN schemes s ON s.scheme_code = rf.scheme_code
               WHERE rf.rec_id = ? ORDER BY rf.rowid""",
            (r["rec_id"],),
        ).fetchall()
        resolved = [f for f in funds if f["included"] and f["scheme_code"]]
        if not resolved:
            continue  # skip empty/duplicate recommendations
        print(f"\n#{r['rec_id']}  {r['advisor']} · {r['risk_profile']}")
        for f in funds:
            if not f["included"]:
                print(f"   - [excluded] {f['display_name']}")
                continue
            cat = f["scheme_category"] or "(run fetch-all to load category)"
            name = f["resolved_name"] or "?? UNRESOLVED"
            flag = _review_flag(f["asset_class"], name, cat)
            print(f"   {f['weight']:5.1%}  {f['display_name']}")
            print(f"          -> {name}")
            print(f"          [{f['asset_class']}] [{cat}]" + ("   <<< REVIEW" if flag else ""))
            if flag:
                flags.append((r["rec_id"], f["display_name"], name, flag))
    print("\n" + "=" * 60)
    if flags:
        print("FLAGGED FOR REVIEW (check these against the slides):")
        for rid, dn, nm, why in flags:
            print(f"  #{rid}  '{dn}' -> {nm}\n        ({why})")
    else:
        print("No automatic red flags. Scan the names + categories above vs the slides.")
    return 0


def _cmd_backtest(args) -> int:
    from .portfolio.backtest import backtest
    conn = ingest.open_store()
    rec = schema.load_recommendation(conn, int(args.rec_id))
    rows = backtest(conn, rec, proxies=_proxies_from_args(args))
    if not rows:
        print("No backtestable data (funds not fetched?).", file=sys.stderr)
        return 1
    print(f"\nHistorical backtest · {rec.advisor} ({rec.risk_profile})")
    print("Same allocation run over past windows, vs passive twin (index funds).\n")
    print(f"{'Window':<8}{'From':<12}{'Return':>9}{'Vol':>8}{'Sharpe':>8}{'MaxDD':>8}{'vs Passive':>12}{'Dropped':>9}")
    print("-" * 74)
    for r in rows:
        vp = f"{r.excess_vs_passive:+.1%}" if r.excess_vs_passive is not None else "—"
        print(f"{r.window:<8}{r.start:<12}{r.plan_return:>9.1%}{r.plan_vol:>8.1%}"
              f"{r.plan_sharpe:>8.2f}{r.plan_maxdd:>8.1%}{vp:>12}{r.dropped_weight:>9.0%}")
    print("\n'Dropped' = plan weight excluded in that window because those funds didn't\n"
          "exist yet (e.g. target-maturity funds launched recently).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mfrip", description="Mutual Fund Recommendation Intelligence Platform")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("sync-schemes", help="download the full scheme master").set_defaults(func=_cmd_sync_schemes)

    pr = sub.add_parser("resolve", help="search scheme names -> codes")
    pr.add_argument("query")
    pr.add_argument("--limit", type=int, default=15)
    pr.set_defaults(func=_cmd_resolve)

    pf = sub.add_parser("fetch", help="download & cache NAV history for scheme codes")
    pf.add_argument("codes", nargs="+")
    pf.add_argument("--force", action="store_true")
    pf.set_defaults(func=_cmd_fetch)

    pu = sub.add_parser("seed-universe",
                        help="curate and download a broad fund universe for the screener")
    pu.add_argument("--target", type=int, default=500,
                    help="approximate number of funds to cache (default 500)")
    pu.add_argument("--delay", type=float, default=0.15,
                    help="seconds to wait between downloads (be kind to the free API)")
    pu.set_defaults(func=_cmd_seed_universe)

    ps = sub.add_parser("snapshot", help="point-in-time metrics for a cached scheme")
    ps.add_argument("code")
    ps.add_argument("--as-of", dest="as_of", default=None, help="YYYY-MM-DD (default: latest)")
    ps.add_argument("--benchmark", default=None, help="benchmark scheme code (TRI index fund)")
    ps.add_argument("--rf", type=float, default=None, help="annual risk-free override")
    ps.set_defaults(func=_cmd_snapshot)

    pl = sub.add_parser("load-rec", help="load a recommendation YAML and resolve fund codes")
    pl.add_argument("yaml")
    pl.set_defaults(func=_cmd_load_rec)

    prs = sub.add_parser("rec-show", help="show a stored recommendation")
    prs.add_argument("rec_id")
    prs.set_defaults(func=_cmd_rec_show)

    prf = sub.add_parser("rec-fix", help="override a fund's resolved scheme code")
    prf.add_argument("rec_id")
    prf.add_argument("display_name")
    prf.add_argument("code", type=int)
    prf.set_defaults(func=_cmd_rec_fix)

    pfr = sub.add_parser("fetch-rec", help="download NAVs for all funds in a recommendation")
    pfr.add_argument("rec_id")
    pfr.add_argument("--benchmark", type=int, default=DEFAULT_BENCHMARK)
    pfr.add_argument("--force", action="store_true")
    pfr.set_defaults(func=_cmd_fetch_rec)

    pa = sub.add_parser("audit", help="forward-audit a recommendation vs benchmark + equal-weight")
    pa.add_argument("rec_id")
    pa.add_argument("--benchmark", type=int, default=DEFAULT_BENCHMARK)
    pa.add_argument("--equity-proxy", dest="equity_proxy", default=None)
    pa.add_argument("--debt-proxy", dest="debt_proxy", default=None)
    pa.add_argument("--gold-proxy", dest="gold_proxy", default=None)
    pa.set_defaults(func=_cmd_audit)

    pla = sub.add_parser("load-all", help="load every YAML in a folder and resolve codes")
    pla.add_argument("--folder", default="recommendations")
    pla.set_defaults(func=_cmd_load_all)

    pfa = sub.add_parser("fetch-all", help="download NAVs for every fund across all plans (with retry)")
    pfa.add_argument("--benchmark", type=int, default=DEFAULT_BENCHMARK)
    pfa.add_argument("--force", action="store_true")
    pfa.set_defaults(func=_cmd_fetch_all)

    paa = sub.add_parser("audit-all", help="audit every plan and print a comparison table")
    paa.add_argument("--benchmark", type=int, default=DEFAULT_BENCHMARK)
    paa.add_argument("--equity-proxy", dest="equity_proxy", default=None)
    paa.add_argument("--debt-proxy", dest="debt_proxy", default=None)
    paa.add_argument("--gold-proxy", dest="gold_proxy", default=None)
    paa.set_defaults(func=_cmd_audit_all)

    pv = sub.add_parser("verify", help="list every fund with resolved name + category and flag mismatches")
    pv.set_defaults(func=_cmd_verify)

    pbt = sub.add_parser("backtest", help="run a plan's allocation over past 1/3/5y windows")
    pbt.add_argument("rec_id")
    pbt.add_argument("--equity-proxy", dest="equity_proxy", default=None)
    pbt.add_argument("--debt-proxy", dest="debt_proxy", default=None)
    pbt.add_argument("--gold-proxy", dest="gold_proxy", default=None)
    pbt.set_defaults(func=_cmd_backtest)

    prp = sub.add_parser("report", help="generate a self-contained HTML audit dashboard")
    prp.add_argument("--output", default="mfrip_report.html")
    prp.add_argument("--benchmark", type=int, default=DEFAULT_BENCHMARK)
    prp.add_argument("--equity-proxy", dest="equity_proxy", default=None)
    prp.add_argument("--debt-proxy", dest="debt_proxy", default=None)
    prp.add_argument("--gold-proxy", dest="gold_proxy", default=None)
    prp.set_defaults(func=_cmd_report)

    pad = sub.add_parser("advise", help="recommend a suitable portfolio for an investor profile")
    pad.add_argument("--age", type=int, default=30)
    pad.add_argument("--horizon", type=float, default=10, help="investment horizon in years")
    pad.add_argument("--employment", default="private",
                     choices=["stable", "private", "self", "business", "retired", "student", "unemployed"])
    pad.add_argument("--emergency", default="6m+", choices=["none", "3m", "6m", "6m+"],
                     help="emergency fund saved")
    pad.add_argument("--debt", default="none", choices=["none", "low", "moderate", "high"])
    pad.add_argument("--reaction", default="wait", choices=["sell", "wait", "invest", "sip"],
                     help="reaction if a 10L portfolio fell to 7L")
    pad.add_argument("--experience", default="beginner",
                     choices=["none", "beginner", "intermediate", "experienced"])
    pad.add_argument("--benchmark", type=int, default=DEFAULT_BENCHMARK)
    pad.set_defaults(func=_cmd_advise)

    prs = sub.add_parser("research", help="export an institutional research memo (HTML) for a plan")
    prs.add_argument("rec_id")
    prs.add_argument("--output", default="mfrip_research.html")
    prs.add_argument("--benchmark", type=int, default=DEFAULT_BENCHMARK)
    prs.add_argument("--equity-proxy", dest="equity_proxy", default=None)
    prs.add_argument("--debt-proxy", dest="debt_proxy", default=None)
    prs.add_argument("--gold-proxy", dest="gold_proxy", default=None)
    prs.set_defaults(func=_cmd_research)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
