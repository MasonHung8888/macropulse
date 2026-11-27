#!/usr/bin/env python3
"""
MacroPulse「美國債市戰情室」每日資料引擎
產出：
  - bond_war_room_data.json
  - bond_war_room_archive.json (每日判讀存檔不覆寫 + 隔日命中率驗證與權重進化日誌)

資料來源（100% 真實公開來源，Zero-Mock）：
  - FRED: DGS3MO, DGS2, DGS5, DGS10, DGS30, T10Y2Y, ICE BofA IG/HY/CCC, WRESBAL, SOFR, IORB, RRPONTSYD, WALCL
  - Yahoo Finance: ^GSPC, ^IXIC, ^SOX, ^VIX, ^MOVE, SPY
  - Markets Insider: AI 相關公司美元債券公開報價（找不到即標「無公開報價」，絕不虛構）
  - Google News RSS: 美國債市新聞（自動初判利多／利空／中性）
"""

import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from update_macro_data import fetch_fred_observations, fetch_markets_insider_bond_quote

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "bond_war_room_data.json")
ARCHIVE_FILE = os.path.join(SCRIPT_DIR, "bond_war_room_archive.json")

DEFAULT_WEIGHTS = {
    "ccc_yield": 0.20,
    "hy_oas_mom": 0.16,
    "ig_oas_mom": 0.12,
    "sofr_iorb": 0.16,
    "fed_reserves": 0.14,
    "move_index": 0.12,
    "us10y_mom": 0.10,
}

AI_BOND_SPECS = [
    {"issuer": "CoreWeave", "maturity": "2031-10-01", "coupon": 9.750, "currency": "USD", "identifier": "21873SAG3",
     "isin": "USU2069EAC40", "slug": "coreweave_incdl-notes_202626-31_regs-Bond-2031-usu2069eac40",
     "source_url": "https://www.sec.gov/Archives/edgar/data/1769628/000176962826000183/ex411.htm"},
    {"issuer": "SoftBank Group", "maturity": "2031-07-08", "coupon": 7.000, "currency": "USD", "identifier": "XS2854422818",
     "isin": "XS2854422818", "slug": "softbank_group_corpdl-notes_202424-31-Bond-2031-xs2854422818",
     "source_url": "https://group.softbank/en/ir/stock/bond"},
    {"issuer": "Oracle", "maturity": "2032-09-26", "coupon": 4.800, "currency": "USD", "identifier": "68389XDK8",
     "isin": "US68389XDK81", "slug": "oracle_corpdl-notes_202525-32-Bond-2032-us68389xdk81",
     "source_url": "https://www.sec.gov/Archives/edgar/data/1341439/000119312525220445/d31817dex41.htm"},
    {"issuer": "SpaceX", "maturity": "2031-07-15", "coupon": 5.350, "currency": "USD", "identifier": "84615QAA1",
     "isin": "USU8531HAA87", "slug": "space_exploration_techs_corpdl-notes_202626-31_regs-Bond-2031-usu8531haa87",
     "source_url": "https://ir.spacex.com/updates/releases-details/2026/SpaceX-Announces-Pricing-of-25-Billion-Inaugural-Bond-Issuance-2026-33VwNgsx3O/default.aspx"},
    {"issuer": "Broadcom", "maturity": "2031-11-15", "coupon": 5.150, "currency": "USD", "identifier": "11135FBY6",
     "isin": "US11135FBY60", "slug": "broadcom_incdl-notes_202424-31-Bond-2031-us11135fby60",
     "source_url": "https://www.sec.gov/Archives/edgar/data/1730168/000114036124033072/ny20032136x6_ex4-2.htm"},
    {"issuer": "NVIDIA", "maturity": "2031-06-15", "coupon": 4.500, "currency": "USD", "identifier": "67066GAR5",
     "isin": "US67066GAR56", "slug": "nvidia_corpdl-notes_202626-31-Bond-2031-us67066gar56",
     "source_url": "https://www.sec.gov/Archives/edgar/data/1045810/000119312526275783/d48176dex42.htm"},
    {"issuer": "Meta", "maturity": "2031-05-15", "coupon": 4.550, "currency": "USD", "identifier": "30303MAF9",
     "isin": "US30303MAF95", "slug": "meta_platforms_incdl-notes_202626-31-Bond-2031-us30303maf95",
     "source_url": "https://www.sec.gov/Archives/edgar/data/1326801/000119312526201738/d109954d424b2.htm"},
    {"issuer": "Alphabet", "maturity": "2031-08-15", "coupon": 4.875, "currency": "USD", "identifier": "02079KCQ8",
     "isin": "US02079KCQ85", "slug": "alphabet_incdl-notes_202626-31-Bond-2031-us02079kcq85",
     "source_url": "https://www.sec.gov/Archives/edgar/data/1652044/000119312526342390/d171253dex46.htm"},
    {"issuer": "Microsoft", "maturity": "2031-11-03", "coupon": 5.200, "currency": "USD", "identifier": "594918DB7",
     "isin": "US594918DB72", "slug": "microsoft_corpdl-notes_202626-31-Bond-2031-us594918db72",
     "source_url": "https://www.sec.gov/Archives/edgar/data/789019/000119312526442618/d150456d424b2.htm"},
    {"issuer": "Amazon", "maturity": "2031-07-09", "coupon": 4.800, "currency": "USD", "identifier": "023135EC6",
     "isin": "US023135EC69", "slug": "amazoncom_incdl-notes_202626-31-Bond-2031-us023135ec69",
     "source_url": "https://www.sec.gov/Archives/edgar/data/1018724/000110465926081334/tm2619352d3_fwp.htm"},
    {"issuer": "AMD", "maturity": "2032-06-01", "coupon": 4.393, "currency": "USD", "identifier": "007903BF3",
     "isin": "US007903BF39", "slug": "advanced_micro_devices_incdl-notes_202222-32-Bond-2032-us007903bf39",
     "source_url": "https://markets.businessinsider.com/bonds/advanced_micro_devices_incdl-notes_202222-32-Bond-2032-us007903bf39"},
    {"issuer": "Super Micro", "maturity": "2028-07-15", "coupon": 2.250, "currency": "USD", "identifier": "86800UAC8",
     "isin": "US86800UAC80", "slug": "super_micro_computer_incdl-conv_notes_202528_144a-Bond-2028-us86800uac80",
     "source_url": "https://markets.businessinsider.com/bonds/super_micro_computer_incdl-conv_notes_202528_144a-Bond-2028-us86800uac80"},
    {"issuer": "台積電 (TSMC)", "maturity": "2032-04-22", "coupon": 4.250, "currency": "USD", "identifier": "USG91139AL26",
     "isin": "USG91139AL26", "slug": "tsmc_globaldl-notes_202222-32_regs-Bond-2032-usg91139al26",
     "source_url": "https://markets.businessinsider.com/bonds/tsmc_globaldl-notes_202222-32_regs-Bond-2032-usg91139al26"},
    {"issuer": "Tesla", "maturity": None, "coupon": None, "currency": "USD", "identifier": None,
     "isin": None, "slug": None, "source_url": None},
    {"issuer": "Micron", "maturity": None, "coupon": None, "currency": "USD", "identifier": None,
     "isin": None, "slug": None, "source_url": None},
    {"issuer": "Dell", "maturity": None, "coupon": None, "currency": "USD", "identifier": None,
     "isin": None, "slug": None, "source_url": None},
    {"issuer": "Arista Networks", "maturity": None, "coupon": None, "currency": "USD", "identifier": None,
     "isin": None, "slug": None, "source_url": None},
]


def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, val))


def _status_from_score(score: float) -> str:
    if score >= 67:
        return "警戒"
    if score >= 34:
        return "注意"
    return "平穩"


def fetch_equity_and_vol() -> dict:
    """透過 yfinance 抓取 S&P 500、Nasdaq、費半、VIX 與 MOVE 近 90 個交易日序列。"""
    specs = {
        "sp500": ("^GSPC", "S&P 500"),
        "nasdaq": ("^IXIC", "Nasdaq"),
        "sox": ("^SOX", "費城半導體"),
        "vix": ("^VIX", "VIX 股市波動"),
        "move": ("^MOVE", "MOVE 債市波動"),
        "spy": ("SPY", "SPY ETF"),
    }
    out = {}
    try:
        import yfinance as yf
        syms = " ".join(s for s, _ in specs.values())
        df_all = yf.download(syms, period="6mo", interval="1d", group_by="ticker", auto_adjust=True, progress=False)
        for key, (sym, label) in specs.items():
            try:
                df = df_all[sym] if sym in df_all else None
                if df is None or df.empty or "Close" not in df:
                    continue
                closes = df["Close"].dropna()
                if len(closes) < 2:
                    continue
                recent = closes.iloc[-90:]
                latest = float(recent.iloc[-1])
                prev = float(recent.iloc[-2])
                prev_30 = float(recent.iloc[-31]) if len(recent) >= 31 else float(recent.iloc[0])
                out[key] = {
                    "label": label,
                    "symbol": sym,
                    "latest": round(latest, 2),
                    "d1_pct": round((latest - prev) / prev * 100, 2),
                    "chg_30d_pct": round((latest - prev_30) / prev_30 * 100, 2),
                    "as_of": recent.index[-1].strftime("%Y-%m-%d"),
                    "labels": [idx.strftime("%Y-%m-%d") for idx in recent.index],
                    "data": [round(float(v), 2) for v in recent.tolist()],
                    "source": "Yahoo Finance",
                }
            except Exception:
                continue
    except Exception as exc:
        print(f"  yfinance 股債波動抓取略過: {exc}")
    return out


def fetch_bond_news(limit: int = 8) -> list[dict]:
    """抓取 Google News RSS 美國債市新聞，並以規則引擎自動初判利多／利空／中性。"""
    url = "https://news.google.com/rss/search?q=US+Treasury+yield+OR+corporate+bond+spread+OR+Federal+Reserve+liquidity+when:7d&hl=en-US&gl=US&ceid=US:en"
    bullish_kw = ("fall", "falls", "drop", "drops", "ease", "eases", "rally", "rallies", "cut", "cuts", "cool", "cools", "tighten", "narrow", "demand", "inflow")
    bearish_kw = ("surge", "surges", "spike", "jump", "jumps", "soar", "soars", "widen", "widens", "default", "downgrade", "stress", "rout", "selloff", "sell-off", "hawkish", "inflation")
    items = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            xml_bytes = resp.read()
        root = ET.fromstring(xml_bytes)
        for entry in root.findall("./channel/item")[:limit]:
            title = (entry.findtext("title") or "").strip()
            link = (entry.findtext("link") or "").strip()
            pub_date = (entry.findtext("pubDate") or "").strip()
            source_el = entry.find("source")
            source_name = source_el.text.strip() if source_el is not None and source_el.text else "Google News"
            low = title.lower()
            bull_hits = [w for w in bullish_kw if re.search(rf"\b{w}\b", low)]
            bear_hits = [w for w in bearish_kw if re.search(rf"\b{w}\b", low)]
            if len(bull_hits) > len(bear_hits):
                sentiment = "利多"
                reason = f"自動初判：標題出現殖利率回落或買盤支撐訊號（{', '.join(bull_hits[:2])}），有利債市估值。"
            elif len(bear_hits) > len(bull_hits):
                sentiment = "利空"
                reason = f"自動初判：標題出現利率彈升、利差擴大或鷹派風險訊號（{', '.join(bear_hits[:2])}），增加債市壓力。"
            else:
                sentiment = "中性"
                reason = "自動初判：屬市場評論或雙向消息，暫無單邊壓力訊號。"
            items.append({
                "title": title,
                "link": link,
                "published_at": pub_date,
                "source": source_name,
                "sentiment": sentiment,
                "reason": reason,
                "auto_classified": True,
            })
    except Exception as exc:
        print(f"  債市新聞 RSS 抓取略過: {exc}")
    return items


def load_archive() -> dict:
    if os.path.exists(ARCHIVE_FILE):
        try:
            with open(ARCHIVE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"weights": dict(DEFAULT_WEIGHTS), "records": [], "evolution_log": []}


def calibrate_and_archive(archive: dict, today_record: dict, spy_d1: float | None, hy_oas_chg_1d_bps: float | None) -> dict:
    """每日判讀存檔不覆寫；若昨日紀錄尚未驗證，依今日實際 SPY 與 HY OAS 走勢檢驗並微調權重。"""
    weights = dict(archive.get("weights") or DEFAULT_WEIGHTS)
    records = list(archive.get("records") or [])
    evo_log = list(archive.get("evolution_log") or [])

    # Verify latest unverified record if today's date is newer
    if records and spy_d1 is not None and hy_oas_chg_1d_bps is not None:
        prev = records[-1]
        if prev.get("date") != today_record["date"] and not prev.get("verified"):
            prev_score = prev["stress_score"]
            if prev_score >= 55:
                hit = (spy_d1 < 0) or (hy_oas_chg_1d_bps > 0)
                expectation = "高壓預警風險資產承壓或利差走寬"
            elif prev_score < 40:
                hit = (spy_d1 >= -0.5) and (hy_oas_chg_1d_bps <= 5)
                expectation = "低壓預期股市穩健且信用利差收斂"
            else:
                hit = abs(spy_d1) < 1.5
                expectation = "中性區間預期市場震盪可控"

            prev["verified"] = True
            prev["hit"] = bool(hit)
            prev["actual_spy_d1"] = spy_d1
            prev["actual_hy_oas_chg_bps"] = round(hy_oas_chg_1d_bps, 1)

            if not hit:
                # Identify strongest disagreeing signal and nudge weights
                sig_scores = prev.get("signal_scores") or {}
                if prev_score >= 55:
                    reason = f"預期{expectation}，但隔日 SPY {spy_d1:+.2f}%、HY OAS {hy_oas_chg_1d_bps:+.1f}bps；微調偏高權重訊號。"
                    top_sig = max(sig_scores, key=lambda k: sig_scores[k], default=None)
                    if top_sig and top_sig in weights:
                        weights[top_sig] = max(0.06, round(weights[top_sig] - 0.01, 4))
                else:
                    reason = f"預期{expectation}，但隔日 SPY {spy_d1:+.2f}%、HY OAS {hy_oas_chg_1d_bps:+.1f}bps；上調高敏度利差訊號權重。"
                    if "hy_oas_mom" in weights:
                        weights["hy_oas_mom"] = min(0.28, round(weights["hy_oas_mom"] + 0.01, 4))
                # Renormalize weights to sum to 1.0
                total_w = sum(weights.values())
                weights = {k: round(v / total_w, 4) for k, v in weights.items()}
                prev["miss_reason"] = reason
                evo_log.append({
                    "date": today_record["date"],
                    "evaluated_date": prev["date"],
                    "event": "權重自動校準",
                    "reason": reason,
                    "weights": dict(weights),
                })
            else:
                prev["miss_reason"] = None

    # Append today's record ONLY if date does not already exist (never overwrite historical dates)
    if not any(r.get("date") == today_record["date"] for r in records):
        records.append(today_record)

    verified_records = [r for r in records if r.get("verified")]
    hits = sum(1 for r in verified_records if r.get("hit"))
    hit_rate = round(hits / len(verified_records) * 100, 1) if verified_records else None

    archive_out = {
        "weights": weights,
        "records": records[-180:],
        "evolution_log": evo_log[-60:],
    }
    tmp = ARCHIVE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(archive_out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, ARCHIVE_FILE)

    return {
        "weights": weights,
        "hit_rate_pct": hit_rate,
        "verified_count": len(verified_records),
        "total_count": len(records),
        "records": list(reversed(records[-30:])),
        "evolution_log": list(reversed(evo_log[-20:])),
    }


def main():
    print("=" * 65)
    print("MacroPulse「美國債市戰情室」資料引擎啟動")
    print("=" * 65)

    fred_ids = [
        "DGS3MO", "DGS2", "DGS5", "DGS10", "DGS30", "T10Y2Y",
        "BAMLC0A0CMEY", "BAMLC0A0CM", "BAMLH0A0HYM2EY", "BAMLH0A0HYM2",
        "BAMLH0A3HYCEY", "BAMLH0A3HYC",
        "WRESBAL", "SOFR", "IORB", "RRPONTSYD", "WALCL",
    ]
    obs = fetch_fred_observations(fred_ids)
    eq_vol = fetch_equity_and_vol()

    def latest_and_30d(sid: str):
        rows = obs.get(sid, [])
        if not rows:
            return None, None, None, None
        d_last, v_last = rows[-1]
        v_prev = rows[-2][1] if len(rows) >= 2 else v_last
        v_30 = rows[-22][1] if len(rows) >= 22 else rows[0][1]
        return d_last, v_last, v_last - v_prev, v_last - v_30

    # 1. Yield Curve
    curve_specs = [("3M", "DGS3MO"), ("2Y", "DGS2"), ("5Y", "DGS5"), ("10Y", "DGS10"), ("30Y", "DGS30")]
    curve_points = []
    for tenor, sid in curve_specs:
        d, v, d1, d30 = latest_and_30d(sid)
        if v is not None:
            curve_points.append({
                "tenor": tenor, "series_id": sid, "yield": round(v, 2),
                "chg_30d_bps": round(d30 * 100), "date": d,
            })
    d_2s10s, v_2s10s, _, d30_2s10s = latest_and_30d("T10Y2Y")
    dgs10_rows = obs.get("DGS10", [])[-90:]
    dgs2_map = dict(obs.get("DGS2", [])[-120:])
    curve_history_labels = [d for d, _ in dgs10_rows]
    yield_curve = {
        "as_of": max((p["date"] for p in curve_points), default=None),
        "points": curve_points,
        "spread_2s10s": round(v_2s10s, 2) if v_2s10s is not None else None,
        "spread_2s10s_bps": round(v_2s10s * 100) if v_2s10s is not None else None,
        "is_inverted": (v_2s10s < 0) if v_2s10s is not None else None,
        "history": {
            "labels": curve_history_labels,
            "dgs10": [round(v, 2) for _, v in dgs10_rows],
            "dgs2": [round(dgs2_map[d], 2) if d in dgs2_map else None for d in curve_history_labels],
        },
        "source": "FRED (DGS3MO, DGS2, DGS5, DGS10, DGS30, T10Y2Y)",
    }

    # 2. Credit Spreads & Effective Yields (IG, HY, CCC)
    credit_defs = [
        ("ig", "投資級 (IG)", "BAMLC0A0CMEY", "BAMLC0A0CM"),
        ("hy", "高收益 (HY)", "BAMLH0A0HYM2EY", "BAMLH0A0HYM2"),
        ("ccc", "CCC 以下", "BAMLH0A3HYCEY", "BAMLH0A3HYC"),
    ]
    credit_items = []
    credit_hist_maps = {}
    credit_dates = set()
    hy_oas_1d_bps = None
    for key, name, y_id, o_id in credit_defs:
        dy, vy, _, dy30 = latest_and_30d(y_id)
        do, vo, do1, do30 = latest_and_30d(o_id)
        if key == "hy" and do1 is not None:
            hy_oas_1d_bps = do1 * 100
        if vy is not None:
            credit_items.append({
                "key": key, "name": name, "date": dy,
                "yield": round(vy, 2),
                "yield_chg_30d_bps": round(dy30 * 100) if dy30 is not None else None,
                "oas_bps": round(vo * 100) if vo is not None else None,
                "oas_chg_30d_bps": round(do30 * 100) if do30 is not None else None,
            })
        y_recent = obs.get(y_id, [])[-90:]
        o_recent = obs.get(o_id, [])[-90:]
        credit_hist_maps[f"{key}_yield"] = {d: round(v, 2) for d, v in y_recent}
        credit_hist_maps[f"{key}_oas"] = {d: round(v * 100) for d, v in o_recent}
        credit_dates.update(d for d, _ in y_recent)
    c_labels = sorted(credit_dates)
    credit_spreads = {
        "as_of": max((i["date"] for i in credit_items), default=None),
        "items": credit_items,
        "history": {"labels": c_labels, **{k: [m.get(d) for d in c_labels] for k, m in credit_hist_maps.items()}},
        "source": "ICE Data Indices via FRED",
    }

    # 3. Liquidity Dashboard
    d_res, v_res, _, d30_res = latest_and_30d("WRESBAL")  # Millions USD
    d_sofr, v_sofr, _, _ = latest_and_30d("SOFR")
    d_iorb, v_iorb, _, _ = latest_and_30d("IORB")
    d_rrp, v_rrp, _, d30_rrp = latest_and_30d("RRPONTSYD")  # Billions USD
    d_walcl, v_walcl, _, d30_walcl = latest_and_30d("WALCL")  # Millions USD
    sofr_iorb_bps = round((v_sofr - v_iorb) * 100, 1) if (v_sofr is not None and v_iorb is not None) else None
    reserves_t = round(v_res / 1e6, 3) if v_res is not None else None
    reserves_30d_pct = round(d30_res / (v_res - d30_res) * 100, 2) if (v_res and d30_res is not None and (v_res - d30_res) != 0) else None
    liquidity = {
        "reserves_trillions": reserves_t,
        "reserves_chg_30d_pct": reserves_30d_pct,
        "reserves_date": d_res,
        "sofr": round(v_sofr, 2) if v_sofr is not None else None,
        "iorb": round(v_iorb, 2) if v_iorb is not None else None,
        "sofr_iorb_bps": sofr_iorb_bps,
        "sofr_date": d_sofr,
        "on_rrp_billions": round(v_rrp, 2) if v_rrp is not None else None,
        "on_rrp_date": d_rrp,
        "fed_assets_trillions": round(v_walcl / 1e6, 3) if v_walcl is not None else None,
        "fed_assets_date": d_walcl,
        "source": "FRED (WRESBAL, SOFR, IORB, RRPONTSYD, WALCL)",
    }

    # 4. 7 Signals & Stress Score (0-100)
    archive = load_archive()
    weights = archive.get("weights") or DEFAULT_WEIGHTS
    ccc_y = next((i["yield"] for i in credit_items if i["key"] == "ccc"), None)
    hy_mom = next((i["oas_chg_30d_bps"] for i in credit_items if i["key"] == "hy"), None)
    ig_mom = next((i["oas_chg_30d_bps"] for i in credit_items if i["key"] == "ig"), None)
    move_val = eq_vol.get("move", {}).get("latest")
    us10y_mom = next((p["chg_30d_bps"] for p in curve_points if p["tenor"] == "10Y"), None)

    raw_signals = [
        ("ccc_yield", "CCC 有效殖利率", ccc_y, "%",
         _clamp(((ccc_y - 10.0) / 8.0) * 100) if ccc_y is not None else 50.0,
         f"CCC 級有效殖利率 {ccc_y:.2f}%，{'高於 15% 顯示弱信用借款人融資成本明顯承壓' if (ccc_y or 0) >= 15 else '處於可控或溫和區間'}。" if ccc_y is not None else "暫無資料"),
        ("hy_oas_mom", "高收益利差 30 日動能", hy_mom, " bps",
         _clamp(25.0 + (hy_mom / 80.0) * 55.0) if hy_mom is not None else 50.0,
         f"近 30 日 HY OAS 變動 {hy_mom:+d} bps，{'信用利差正在明顯走寬' if (hy_mom or 0) >= 35 else '高收債利差尚稱穩定'}。" if hy_mom is not None else "暫無資料"),
        ("ig_oas_mom", "投資級利差 30 日動能", ig_mom, " bps",
         _clamp(20.0 + (ig_mom / 35.0) * 60.0) if ig_mom is not None else 50.0,
         f"近 30 日 IG OAS 變動 {ig_mom:+d} bps，{'優質企業債同步承壓' if (ig_mom or 0) >= 15 else '投資級信用極為穩健（僅弱信用承壓）'}。" if ig_mom is not None else "暫無資料"),
        ("sofr_iorb", "SOFR − IORB 資金利差", sofr_iorb_bps, " bps",
         _clamp(((sofr_iorb_bps + 5.0) / 20.0) * 100) if sofr_iorb_bps is not None else 30.0,
         f"回購利率與準備金利率差 {sofr_iorb_bps:+.1f} bps，{'貨幣市場資金趨緊' if (sofr_iorb_bps or 0) > 5 else '銀行體系短端流動性充裕'}。" if sofr_iorb_bps is not None else "暫無資料"),
        ("fed_reserves", "聯準會準備金餘額", reserves_t, " 兆$",
         _clamp(85.0 - ((reserves_t - 2.5) / 0.8) * 70.0) if reserves_t is not None else 40.0,
         f"銀行準備金 ${reserves_t:.2f} 兆美元（30日 {reserves_30d_pct:+.1f}%），{'逼近充裕準備金下緣' if (reserves_t or 3) < 2.9 else '準備金水位安全'}。" if reserves_t is not None else "暫無資料"),
        ("move_index", "MOVE 美債波動指數", move_val, "",
         _clamp(((move_val - 75.0) / 55.0) * 100) if move_val is not None else 40.0,
         f"MOVE 指數報 {move_val:.1f}，{'美債利率波動劇烈' if (move_val or 0) >= 105 else '公債市場波動維持溫和'}。" if move_val is not None else "暫無資料"),
        ("us10y_mom", "10 年期殖利率 30 日動能", us10y_mom, " bps",
         _clamp(25.0 + (us10y_mom / 50.0) * 55.0) if us10y_mom is not None else 40.0,
         f"10Y 美債近 30 日變動 {us10y_mom:+d} bps，{'長端利率快速抽升壓抑風險估值' if (us10y_mom or 0) >= 25 else '長端殖利率走勢平穩'}。" if us10y_mom is not None else "暫無資料"),
    ]
    signals = []
    signal_scores = {}
    weighted_sum = 0.0
    total_w = 0.0
    for key, label, val, unit, score, note in raw_signals:
        score = round(score, 1)
        signal_scores[key] = score
        w = float(weights.get(key, DEFAULT_WEIGHTS[key]))
        weighted_sum += score * w
        total_w += w
        signals.append({
            "key": key,
            "label": label,
            "value": val,
            "unit": unit,
            "score": score,
            "weight": round(w, 4),
            "status": _status_from_score(score),
            "note": note,
        })
    stress_score = round(weighted_sum / total_w, 1) if total_w > 0 else 50.0

    # Regime classification: 挑客戶 vs 系統性危機 vs 平穩寬鬆
    sys_liq_stress = (
        signal_scores.get("sofr_iorb", 0) >= 60 or
        signal_scores.get("fed_reserves", 0) >= 67 or
        (signal_scores.get("move_index", 0) >= 67 and signal_scores.get("ig_oas_mom", 0) >= 60)
    )
    credit_tiering = (
        signal_scores.get("ccc_yield", 0) >= 50 or
        signal_scores.get("hy_oas_mom", 0) >= 55
    )
    if sys_liq_stress and stress_score >= 55:
        regime = "系統性危機（流動性枯竭風險）"
        regime_key = "systemic_crisis"
        conclusion = f"壓力分數 {stress_score:.0f}/100：短端資金或投資級利差同步收緊，已出現系統性流動性壓力徵兆，股市面臨估值與融資雙重壓抑。"
    elif credit_tiering:
        regime = "挑客戶（信用分層、只針對弱借款人收費）"
        regime_key = "selective_credit"
        conclusion = f"壓力分數 {stress_score:.0f}/100：銀行準備金與 SOFR-IORB 仍屬平穩，但高收益／CCC 級高風險借款人融資成本偏高，屬於信用分層而非系統性危機。"
    else:
        regime = "平穩寬鬆（無系統性壓力）"
        regime_key = "calm"
        conclusion = f"壓力分數 {stress_score:.0f}/100：公債波動、信用利差與銀行流動性皆維持平穩，債市對股市資金環境友善。"

    # 5. AI Corporate Bonds (17 companies, sorted by YTM descending, unquoted at bottom)
    ust5 = next((p["yield"] for p in curve_points if p["tenor"] == "5Y"), None)
    ust7_approx = (next((p["yield"] for p in curve_points if p["tenor"] == "10Y"), None) + ust5) / 2 if ust5 else None
    ust10 = next((p["yield"] for p in curve_points if p["tenor"] == "10Y"), None)
    ai_bonds = []
    for spec in AI_BOND_SPECS:
        q = fetch_markets_insider_bond_quote(spec["isin"], spec["slug"]) if spec.get("slug") else None
        if q and q.get("market_yield") is not None:
            ytm = q["market_yield"]
            mat_yr = int(spec["maturity"][:4])
            bench = ust5 if mat_yr <= 2031 else (ust7_approx or ust10)
            spread = round((ytm - bench) * 100) if bench is not None else None
            ai_bonds.append({
                "issuer": spec["issuer"],
                "maturity": spec["maturity"],
                "coupon": spec["coupon"],
                "currency": spec["currency"],
                "identifier": spec["identifier"],
                "market_price": q.get("market_price"),
                "market_yield": ytm,
                "spread_bps": spread,
                "quote_date": q["quote_date"],
                "quote_source": f"Markets Insider ({q['venue']})" if q.get("venue") else "Markets Insider",
                "quote_url": q["quote_url"],
                "quote_status": "公開報價",
                "source_url": spec["source_url"],
            })
        else:
            ai_bonds.append({
                "issuer": spec["issuer"],
                "maturity": spec["maturity"],
                "coupon": spec["coupon"],
                "currency": spec["currency"],
                "identifier": spec["identifier"],
                "market_price": None,
                "market_yield": None,
                "spread_bps": None,
                "quote_date": None,
                "quote_source": None,
                "quote_url": None,
                "quote_status": "無公開報價",
                "source_url": spec["source_url"],
            })
    ai_bonds.sort(key=lambda b: (0, -b["market_yield"]) if b["market_yield"] is not None else (1, 0))

    # 6. Daily Archive & Calibration
    as_of_date = yield_curve["as_of"] or credit_spreads["as_of"] or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_rec = {
        "date": as_of_date,
        "stress_score": stress_score,
        "regime": regime,
        "regime_key": regime_key,
        "signal_scores": signal_scores,
        "verified": False,
        "hit": None,
        "miss_reason": None,
    }
    spy_d1 = eq_vol.get("spy", {}).get("d1_pct")
    calibration = calibrate_and_archive(archive, today_rec, spy_d1, hy_oas_1d_bps)

    # 7. Bond News
    news = fetch_bond_news(limit=8)

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "as_of": as_of_date,
        "summary": {
            "stress_score": stress_score,
            "regime": regime,
            "regime_key": regime_key,
            "conclusion": conclusion,
            "signals": signals,
        },
        "yield_curve": yield_curve,
        "credit_spreads": credit_spreads,
        "liquidity": liquidity,
        "ai_bonds": ai_bonds,
        "transmission": {
            "sp500": eq_vol.get("sp500"),
            "nasdaq": eq_vol.get("nasdaq"),
            "sox": eq_vol.get("sox"),
            "vix": eq_vol.get("vix"),
            "move": eq_vol.get("move"),
        },
        "calibration": calibration,
        "news": news,
    }

    tmp = OUTPUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, OUTPUT_FILE)
    print(f"🎉 已完成美國債市戰情室資料寫入: {OUTPUT_FILE}")
    print(f"  • 壓力分數: {stress_score}/100 ({regime})")
    print(f"  • AI 公司債取得公開報價: {sum(1 for b in ai_bonds if b['market_yield'] is not None)}/{len(ai_bonds)} 檔")
    print(f"  • 債市新聞: {len(news)} 則 | 每日存檔累計: {calibration['total_count']} 筆")


if __name__ == "__main__":
    main()
