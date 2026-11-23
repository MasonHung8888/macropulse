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

for key in ("tw_export_orders", "equity_risk_premium"):
    if macro.get(key):
        errors.append(f"{key} must remain empty until a verifiable live source is implemented")

for key in ("twExportOrders", "twExportOrdersYoY", "equityRiskPremium"):
    if key in macro.get("series", {}):
        errors.append(f"unverified series leaked into macro bundle: {key}")

for key, indicator in macro.get("macro_indicators", {}).items():
    if not indicator.get("source_url") or not indicator.get("period"):
        errors.append(f"macro indicator lacks source/date: {key}")

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
