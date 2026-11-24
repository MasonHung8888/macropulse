#!/usr/bin/env python3
"""
test_full_regression.py
Runs end-to-end schema compatibility and functional checks across all 3 candidate JSONs
"""

import sys
import json
import os
from validate_schema_compatibility import validate_pair

BASE_DIR = os.environ.get("MACROPULSE_TEST_DIR", os.path.dirname(os.path.abspath(__file__)))

def test_system_a():
    base = os.path.join(BASE_DIR, "macro_live_data.json")
    cand = os.path.join(BASE_DIR, "macro_live_data_candidate.json")
    assert validate_pair(base, cand), "System A Schema mismatch!"
    with open(cand, 'r', encoding='utf-8') as f:
        d = json.load(f)
    # Check A-01 FedWatch
    fw = d.get("fedwatch", {})
    assert "next_meeting" in fw and "prob_cut" in fw["next_meeting"], "FedWatch next meeting missing"
    assert fw["next_meeting"]["prob_cut"] + fw["next_meeting"]["prob_hold"] + fw["next_meeting"]["prob_hike"] == 100.0, "FedWatch probs sum != 100"
    # Check A-02 export orders
    assert "tw_export_orders" in d and d["tw_export_orders"]["latest"]["amount_billions"] > 0
    # Check A-03 net liquidity
    assert "fed_liquidity" in d and d["fed_liquidity"]["latest"]["net_liquidity_billions"] > 0
    # Check A-05 ERP
    assert "equity_risk_premium" in d and "erp" in d["equity_risk_premium"]
    print(">>> System A Full Regression: ALL CHECKS PASSED!")

def test_system_b():
    base = os.path.join(BASE_DIR, "tech_earnings_data.json")
    cand = os.path.join(BASE_DIR, "tech_earnings_data_candidate.json")
    assert validate_pair(base, cand), "System B Schema mismatch!"
    with open(cand, 'r', encoding='utf-8') as f:
        d = json.load(f)
    assert len(d.get("data", [])) == 16, "System B must have 16 tickers"
    for item in d["data"]:
        assert item["ticker"] and item["date"] and item["consensusEps"]
        assert "_quality_metadata" in item and item["_quality_metadata"]["status"] in ["confirmed", "estimated", "unverified"]
    print(">>> System B Full Regression: ALL CHECKS PASSED!")

def test_system_c():
    base = os.path.join(BASE_DIR, "tw_bottom_data.json")
    cand = os.path.join(BASE_DIR, "tw_bottom_data_candidate.json")
    assert validate_pair(base, cand), "System C Schema mismatch!"
    with open(cand, 'r', encoding='utf-8') as f:
        d = json.load(f)
    # C-01
    df = d["institutional_flow"]["history"]["daily_foreign"]
    ih = d["institutional_flow"]["history"]
    assert ih.get("provenance") == "official_observations", "institutional history must be source-backed"
    assert len(df) == len(ih["dates"]), "institutional dates and values must align"
    # C-02
    mb = d["margin_trading"]["history"]["balances"]
    md = d["margin_trading"]["history"]["diffs"]
    assert len(mb) == len(md)
    # C-04
    assert d["indices"]["twse"]["taiex"]["close"] != 36033.29, "No fake 36,033 points"
    # C-07: max-pain is optional; absence is preferable to a fabricated strike.
    omp = d.get("options_max_pain", {})
    if omp.get("weekly"):
        assert omp["weekly"].get("max_pain_strike", 0) > 0
    # C-08
    p_opt = int(d["scenarios"]["optimistic"]["probability"].replace("%", ""))
    p_base = int(d["scenarios"]["base_case"]["probability"].replace("%", ""))
    p_str = int(d["scenarios"]["stress_case"]["probability"].replace("%", ""))
    assert p_opt + p_base + p_str == 100, "Scenarios prob sum != 100"
    print(">>> System C Full Regression: ALL CHECKS PASSED!")

if __name__ == "__main__":
    print("=================================================================")
    print("Starting MacroPulse Tri-Engine Comprehensive Regression Test")
    print("=================================================================")
    test_system_a()
    test_system_b()
    test_system_c()
    print("=================================================================")
    print("🎉 ALL THREE DATA ENGINES CANDIDATE JSONS 100% VERIFIED!")
    print("=================================================================")
