        "us_10y2y": (-10, 10),
    }
    for key, indicator in payload["macro_indicators"].items():
        value = indicator.get("value")
        lower, upper = macro_ranges.get(key, (-1e12, 1e12))
        age = observation_age_days(indicator.get("period", ""))
        freshness_limit = 14 if indicator.get("frequency") == "daily" else 150
        range_ok = isinstance(value, (int, float)) and lower <= value <= upper
        freshness_ok = age is not None and -1 <= age <= freshness_limit
        indicator["validation"] = {
            "status": "valid" if range_ok and freshness_ok else "invalid",
            "age_days": age,
            "freshness_limit_days": freshness_limit,
            "expected_range": [lower, upper],
        }
        if not range_ok:
            errors.append(f"{key} 超出合理範圍：{value}（預期 {lower} 至 {upper}）")
        if not freshness_ok:
            errors.append(f"{key} 資料期異常或過舊：{indicator.get('period')}（距今 {age} 天）")
    checks.append({"name": "FRED coverage", "passed": len(payload["macro_indicators"]), "required": 8})
    country_macro_count = sum(len(country.get("indicators", {})) for country in payload.get("country_macro", {}).values())
    if country_macro_count < 12:
        errors.append(f"世界銀行跨國指標缺漏：{country_macro_count}/12")
    country_ranges = {
        "gdp_growth": (-30, 30),
        "cpi_inflation": (-20, 100),
        "unemployment": (0, 50),
    }
    for country_code, country in payload.get("country_macro", {}).items():
        for metric, indicator in country.get("indicators", {}).items():
            value = indicator.get("value")
            lower, upper = country_ranges[metric]
            age = observation_age_days(indicator.get("period", ""))
            range_ok = isinstance(value, (int, float)) and lower <= value <= upper
            freshness_ok = age is not None and -366 <= age <= 1200
            indicator["validation"] = {
                "status": "valid" if range_ok and freshness_ok else "invalid",
                "age_days": age,
                "freshness_limit_days": 1200,
                "expected_range": [lower, upper],
            }
            if not range_ok:
                errors.append(f"{country_code}.{metric} 超出合理範圍：{value}")
            if not freshness_ok:
                errors.append(f"{country_code}.{metric} 資料年度異常或過舊：{indicator.get('period')}")
    checks.append({"name": "World Bank country coverage", "passed": country_macro_count, "required": 12})
    for key in required_snapshots & set(payload["snapshots"]):
        snapshot = payload["snapshots"][key]
        if not snapshot.get("as_of"):
            errors.append(f"{key} 缺少資料日期")
            continue
        age = observation_age_days(snapshot["as_of"])
        price = snapshot.get("price")
        if age is None or age < -1 or age > 10:
            errors.append(f"{key} 市場資料過舊或日期異常：{snapshot['as_of']}")
        if not isinstance(price, (int, float)) or price <= 0:
            errors.append(f"{key} 市場價格不合理：{price}")
        snapshot["validation"] = {"status": "valid" if age is not None and -1 <= age <= 10 and isinstance(price, (int, float)) and price > 0 else "invalid", "age_days": age}
    cbc_period = payload.get("tw_m1b_m2", {}).get("latest", {}).get("date")
    cbc_age = observation_age_days(cbc_period) if cbc_period else None
    if cbc_age is None or cbc_age < -1 or cbc_age > 150:
        errors.append(f"央行 M1B/M2 資料期異常或過舊：{cbc_period}")
    checks.extend([
        {"name": "TW heatmap coverage", "passed": len(payload["tw_heatmap"]), "required": len(TW_WATCHLIST)},
        {"name": "US heatmap coverage", "passed": len(payload["sp500_heatmap"]), "required": len(SP500_WATCHLIST)},
        {"name": "Required market snapshots", "passed": len(required_snapshots) - len(missing_snapshots), "required": len(required_snapshots)},
    ])
    payload["sources"] = {
        "twse": {"label": "臺灣證券交易所", "status": "ok" if payload["tw_heatmap"] else "error"},
        "yahoo": {"label": "Yahoo Finance 延遲日線", "status": "ok" if not missing_snapshots else "partial", "realtime": False},
        "cbc": {"label": "中華民國中央銀行", "status": "ok" if payload["tw_m1b_m2"] else "error"},
        "ndc": {"label": "國家發展委員會 (NDC)", "status": "ok" if payload.get("ndc_indicators") else "error"},
        "equity_risk_premium": {"label": "S&P Dow Jones & CBOE ^TNX", "status": "ok" if payload.get("equity_risk_premium") else "error"},
        "fedwatch": {"label": "FRED & CME 30-Day Fed Funds Futures", "status": "ok" if payload.get("fedwatch") else "error"},
        "fear_and_greed": {"label": "FRED & CBOE / S&P Market Sentiment", "status": "ok" if payload.get("fear_and_greed") else "error"},
        "buffett_indicator": {"label": "FRED (GDP) & Yahoo Finance (^W5000)", "status": "ok" if payload.get("buffett_indicator") else "error"},
        "tips_breakeven": {"label": "FRED 10Y TIPS & Breakeven Inflation", "status": "ok" if payload.get("tips_breakeven") else "error"},
        "global_central_banks": {"label": "FRED G4 Central Banks (Fed, ECB, BOJ, PBOC)", "status": "ok" if payload.get("global_central_banks") else "error"},
        "fred": {"label": "Federal Reserve Bank of St. Louis (FRED)", "status": "ok" if len(payload["macro_indicators"]) >= 8 else "partial"},
        "world_bank": {"label": "World Bank Open Data", "status": "ok" if country_macro_count >= 12 else "partial"},
    }
    for key, label in (("ndc_indicators", "NDC"), ("tw_export_orders", "外銷訂單"),
                       ("fedwatch", "FedWatch"), ("equity_risk_premium", "ERP")):
        if not payload.get(key):
            warnings.append(f"{label} 未取得已驗證數據，候選檔不提供推測值")
    payload["data_quality"] = {
        "status": "valid" if not errors else "invalid",
        "validated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
    }
    if errors:
        print("資料驗證失敗，不寫入候選 JSON；正式檔案保持不變：")
        for error in errors:
            print("  - " + error)
        raise SystemExit(1)

    # Candidate-only atomic write; production JSON and DB are untouched.
    temp_file = OUTPUT_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(temp_file, OUTPUT_FILE)

    print("=" * 65)
    print(f"🎉 全部完成！已寫入 {OUTPUT_FILE}")
    print(f"總結：")
    print(f"  • 台灣央行 M1B/M2 官方序列: {'成功' if payload['tw_m1b_m2'] else '未取得'}")
    print(f"  • 台股權值股熱力圖: {len(payload['tw_heatmap'])} 檔")
    print(f"  • 美股 S&P 500 熱力圖: {len(payload['sp500_heatmap'])} 檔")
    print(f"  • 最新市場日線快照指標: {len(payload['snapshots'])} 個")
    print(f"  • 24個月歷史時間序列: {len(payload['series'])} 組")
    print("=" * 65)


if __name__ == "__main__":
    main()
