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

for key in ("equity_risk_premium",):
    if macro.get(key):
        errors.append(f"{key} must remain empty until a verifiable live source is implemented")

for key in ("equityRiskPremium",):
    if key in macro.get("series", {}):
        errors.append(f"unverified series leaked into macro bundle: {key}")

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
for key in ("backtest_data", "options_max_pain", "state_owned_banks", "trust_targeting"):
    if tw.get(key):
        errors.append(f"synthetic Taiwan module must not be published: {key}")

if not tw.get("market_date"):
    errors.append("Taiwan bundle lacks market_date")
if tw.get("_quality_metadata", {}).get("fallback_used"):
    errors.append("Taiwan bundle used a fallback instead of current source data")

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

if errors:
    print("DATA INTEGRITY AUDIT FAILED")
    for error in errors:
        print(f"- {error}")
    raise SystemExit(1)

print("DATA INTEGRITY AUDIT PASSED")
print(f"macro indicators: {len(macro.get('macro_indicators', {}))}")
print(f"Taiwan market date: {tw.get('market_date')}")
print(f"confirmed earnings items: {len(earnings.get('data', []))}")
