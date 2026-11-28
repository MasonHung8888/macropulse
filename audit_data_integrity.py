#!/usr/bin/env python3
"""Fail CI when unverified/synthetic values leak into production data bundles."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
errors: list[str] = []


def load(name: str):
    with (ROOT / name).open(encoding="utf-8") as handle:
        return json.load(handle)


macro = load("macro_live_data.json")
if macro.get("data_quality", {}).get("status") != "valid":
    errors.append("macro_live_data.json did not pass its quality gate")

erp = macro.get("equity_risk_premium", {})
if erp:
    if (not erp.get("source_url") or "Yahoo Finance" not in str(erp.get("source", "")) or
            not erp.get("as_of") or not isinstance(erp.get("erp"), (int, float)) or
            not isinstance(erp.get("sp500_forward_pe"), (int, float))):
        errors.append("equity_risk_premium lacks live verified source, date, or numeric fields")

orders = macro.get("tw_export_orders", {})
orders_meta = orders.get("_quality_metadata", {})
orders_latest = orders.get("latest", {})
orders_history = orders.get("history", [])
if orders_meta.get("data_status") != "published_official" or orders_meta.get("is_projected") is not False:
    errors.append("Taiwan export orders are not published official observations")
if not str(orders.get("source_url", "")).endswith("/opendata/b.csv"):
    errors.append("Taiwan export orders do not use the MOEA open-data CSV")
if len(orders_history) < 24 or orders_latest.get("date") != orders_meta.get("observation_month"):
    errors.append("Taiwan export orders lack aligned 24-month official history")

for key, indicator in macro.get("macro_indicators", {}).items():
    if not indicator.get("source_url") or not indicator.get("period"):
        errors.append(f"macro indicator lacks source/date: {key}")

bonds = macro.get("corporate_bonds", {})
bond_indices = bonds.get("indices", [])
if {item.get("key") for item in bond_indices} != {"ig", "hy", "ccc"}:
    errors.append("corporate bond monitor lacks IG/HY/CCC index coverage")
for item in bond_indices:
    if item.get("date") != bonds.get("as_of") or not item.get("source_url"):
        errors.append(f"corporate bond index lacks aligned date/source: {item.get('key')}")
    if not isinstance(item.get("yield"), (int, float)) or not isinstance(item.get("oas_bps"), (int, float)):
        errors.append(f"corporate bond index lacks numeric yield/OAS: {item.get('key')}")
for issue in bonds.get("issues", []):
    if (issue.get("terms_status") != "verified" or not issue.get("maturity") or
            not isinstance(issue.get("coupon"), (int, float)) or not issue.get("currency") or
            not issue.get("source_url")):
        errors.append(f"corporate bond terms incomplete or unverified: {issue.get('issuer')}")
    if issue.get("market_yield") is not None and (not issue.get("source_url") or not issue.get("quote_date")):
        errors.append(f"corporate bond quote lacks date/source: {issue.get('issuer')}")
if len(bonds.get("issues", [])) != 10:
    errors.append("corporate bond monitor must contain 10 verified issue rows")

for market_key in ("tw_heatmap", "sp500_heatmap"):
    heatmap = macro.get(market_key, [])
    dates = {row.get("as_of") for row in heatmap if row.get("as_of")}
    if not heatmap or len(dates) != 1:
        errors.append(f"{market_key} must contain rows from exactly one observation date")
    for row in heatmap:
        ticker = row.get("ticker", "unknown")
        if not row.get("as_of") or not row.get("source") or not row.get("size_basis"):
            errors.append(f"{market_key}.{ticker} lacks date/source/size provenance")
        if not isinstance(row.get("cap"), (int, float)) or row["cap"] <= 0:
            errors.append(f"{market_key}.{ticker} has an invalid traded-value size")
        if not isinstance(row.get("d1"), (int, float)):
            errors.append(f"{market_key}.{ticker} lacks a valid 1D return")

taiex = macro.get("snapshots", {}).get("taiex", {})
tw_dates = {row.get("as_of") for row in macro.get("tw_heatmap", [])}
if taiex.get("as_of") not in tw_dates:
    errors.append("TAIEX snapshot date does not match the Taiwan heatmap")
if not str(taiex.get("source", "")).startswith("TWSE official"):
    errors.append("TAIEX snapshot is not sourced from TWSE official data")

tw = load("tw_bottom_data.json")
for key in ("backtest_data", "state_owned_banks", "trust_targeting"):
    if tw.get(key):
        errors.append(f"synthetic Taiwan module must not be published: {key}")
omp = tw.get("options_max_pain")
if omp and omp.get("source") != "TAIFEX Official OpenAPI":
    errors.append("options_max_pain must originate from TAIFEX Official OpenAPI or remain empty")

if not tw.get("market_date"):
    errors.append("Taiwan bundle lacks market_date")
if tw.get("_quality_metadata", {}).get("fallback_used"):
    errors.append("Taiwan bundle used a fallback instead of current source data")
taiex_hist_dates = tw.get("indices", {}).get("twse", {}).get("taiex", {}).get("history", {}).get("dates", [])
if taiex_hist_dates and tw.get("market_date"):
    last_hist_date = str(taiex_hist_dates[-1]).replace("-", "")
    if last_hist_date < str(tw["market_date"]):
        from datetime import datetime as _dt
        try:
            gap_days = (_dt.strptime(str(tw["market_date"]), "%Y%m%d") - _dt.strptime(last_hist_date, "%Y%m%d")).days
            if gap_days > 3:
                errors.append(f"Taiwan TAIEX history is stale ({last_hist_date} vs market_date {tw['market_date']})")
        except ValueError:
            pass

earnings = load("tech_earnings_data.json")
accepted_sources = {"TWSE_MOPS_OFFICIAL", "YAHOO_FINANCE_LIVE"}
for idx, item in enumerate(earnings.get("data", [])):
    meta = item.get("_quality_metadata", {})
    if meta.get("status") != "confirmed" or meta.get("source") not in accepted_sources:
        errors.append(f"earnings item {idx} is not source-confirmed")
    if not meta.get("source_url") or not meta.get("verified_at"):
        errors.append(f"earnings item {idx} lacks source URL or verification time")
    if item.get("focusPoints") or item.get("supplyChain"):
        errors.append(f"earnings item {idx} contains unverified editorial fields")
    rev = str(item.get("consensusRev", ""))
    if rev.startswith("$") and rev.endswith("B"):
        try:
            if float(rev[1:-1]) > 500:
                errors.append(f"earnings item {idx} ({item.get('ticker')}) USD revenue {rev} exceeds sanity bound (possible currency mismatch)")
        except ValueError:
            pass

# Mathematical & numerical sanity gates
for k, val in macro.get("fx", {}).items():
    if not isinstance(val, (int, float)) or val <= 0:
        errors.append(f"invalid FX rate for {k}: {val}")

fl = macro.get("fed_liquidity", {}).get("latest", {})
if fl:
    calc_fl = fl.get("total_assets_billions", 0) - fl.get("tga_billions", 0) - fl.get("rrp_billions", 0)
    if abs(calc_fl - fl.get("net_liquidity_billions", 0)) > 1.0:
        errors.append("fed_liquidity math mismatch")

tb = macro.get("tips_breakeven", {}).get("latest", {})
if tb:
    if abs((tb.get("nominal_yield", 0) - tb.get("real_yield", 0)) - tb.get("breakeven_inflation", 0)) > 0.25:
        errors.append("tips_breakeven math mismatch")

bi = macro.get("buffett_indicator", {}).get("latest", {})
if bi and bi.get("gdp_trillions"):
    if abs((bi.get("market_cap_trillions", 0) / bi["gdp_trillions"] * 100) - bi.get("ratio", 0)) > 1.0:
        errors.append("buffett_indicator math mismatch")

if erp:
    if abs((erp.get("earnings_yield", 0) - erp.get("us10y_yield", 0)) - erp.get("erp", 0)) > 0.1:
        errors.append("equity_risk_premium math mismatch")

etf_mon = macro.get("etf_monitor", {})
etf_list = etf_mon.get("etfs", [])
if len(etf_list) != 8:
    errors.append(f"etf_monitor must contain 8 verified ETFs, got {len(etf_list)}")
for etf in etf_list:
    if not isinstance(etf.get("price"), (int, float)) or etf["price"] <= 0 or not etf.get("as_of") or not etf.get("source"):
        errors.append(f"etf_monitor.{etf.get('ticker')} lacks valid price/date/source")

macro_cal = macro.get("macro_calendar", [])
if not macro_cal:
    errors.append("macro_calendar must contain official upcoming events")
for ev in macro_cal:
    if not ev.get("date") or not ev.get("event") or not ev.get("source_url"):
        errors.append(f"macro_calendar event incomplete: {ev}")

for issue in bonds.get("issues", []):
    ytm = issue.get("market_yield")
    if ytm is not None and (not isinstance(ytm, (int, float)) or ytm <= 0 or ytm > 50):
        errors.append(f"corporate bond YTM out of sanity range: {issue.get('issuer')}={ytm}")

for market_key in ("tw_heatmap", "sp500_heatmap"):
    for row in macro.get(market_key, []):
        p = row.get("price")
        d1 = row.get("d1")
        if not isinstance(p, (int, float)) or p <= 0:
            errors.append(f"{market_key}.{row.get('ticker')} invalid price: {p}")
        if not isinstance(d1, (int, float)) or abs(d1) > 35:
            errors.append(f"{market_key}.{row.get('ticker')} extreme d1 return: {d1}")

tw_taiex_close = tw.get("indices", {}).get("twse", {}).get("taiex", {}).get("close")
macro_taiex_asof = str(taiex.get("as_of", "")).replace("-", "")
if (isinstance(tw_taiex_close, (int, float)) and tw_taiex_close > 0 and
        isinstance(taiex.get("price"), (int, float)) and macro_taiex_asof == str(tw.get("market_date", ""))):
    diff_pct = abs(taiex["price"] - tw_taiex_close) / tw_taiex_close * 100
    if diff_pct > 0.5:
        errors.append(f"cross-bundle TAIEX mismatch on {macro_taiex_asof}: {taiex['price']} vs {tw_taiex_close}")

# Bond War Room data integrity checks
bw = load("bond_war_room_data.json")
bw_yc_pts = bw.get("yield_curve", {}).get("points", [])
if {p.get("tenor") for p in bw_yc_pts} != {"3M", "2Y", "5Y", "10Y", "30Y"}:
    errors.append("bond_war_room_data.json lacks full 3M/2Y/5Y/10Y/30Y yield curve points")
bw_cs_items = bw.get("credit_spreads", {}).get("items", [])
if {i.get("key") for i in bw_cs_items} != {"ig", "hy", "ccc"}:
    errors.append("bond_war_room_data.json lacks IG/HY/CCC credit spread items")
bw_liq = bw.get("liquidity", {})
for req_liq in ("reserves_trillions", "sofr", "iorb", "sofr_iorb_bps", "on_rrp_billions", "fed_assets_trillions"):
    if not isinstance(bw_liq.get(req_liq), (int, float)):
        errors.append(f"bond_war_room_data.json liquidity.{req_liq} is missing or non-numeric")
bw_tr = bw.get("transmission", {})
for req_tr in ("sp500", "nasdaq", "sox", "vix", "move"):
    if not isinstance((bw_tr.get(req_tr) or {}).get("latest"), (int, float)):
        errors.append(f"bond_war_room_data.json transmission.{req_tr} lacks live latest value")
bw_bonds = bw.get("ai_bonds", [])
if len(bw_bonds) != 17:
    errors.append(f"bond_war_room_data.json ai_bonds must have 17 rows, got {len(bw_bonds)}")
for b in bw_bonds:
    if b.get("market_yield") is not None and (not b.get("quote_date") or not b.get("quote_url")):
        errors.append(f"bond_war_room_data.json ai_bond {b.get('issuer')} lacks quote_date/quote_url")

if errors:
    print("DATA INTEGRITY AUDIT FAILED")
    for error in errors:
        print(f"- {error}")
    raise SystemExit(1)

print("DATA INTEGRITY AUDIT PASSED")
print(f"macro indicators: {len(macro.get('macro_indicators', {}))}")
print(f"Taiwan market date: {tw.get('market_date')}")
print(f"confirmed earnings items: {len(earnings.get('data', []))}")
