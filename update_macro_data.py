#!/usr/bin/env python3
"""
MacroPulse 全方位真實市場與總經數據自動抓取腳本 (純 Python 標準函式庫，免安裝額外套件)
資料來源：
  1. 臺灣證券交易所 (TWSE) OpenAPI: 台股 28 檔權值股每日收盤
  2. Yahoo Finance Chart JSON: 美股 S&P 500 熱力圖成分股 (1D/1W/YTD)、大盤指數與大宗商品 24 個月序列
  3. 聖路易聯邦準備銀行 (FRED) 公開 CSV: 美國 10Y/2Y 殖利率、利差、CPI 年增率、M2 年增率、失業率

使用方式：
  python update_macro_data.py
產出 macro_live_data.json，搭配 GitHub Actions 即可每日定時自動更新整個網站。
"""

import csv
import io
import json
import ssl
import urllib.request
from datetime import datetime

TW_WATCHLIST = [
    ("半導體", "2330", "台積電", 520),
    ("半導體", "2454", "聯發科", 95),
    ("半導體", "3711", "日月光投控", 45),
    ("半導體", "2303", "聯電", 38),
    ("半導體", "2379", "瑞昱", 24),
    ("半導體", "3034", "聯詠", 22),
    ("半導體", "3661", "世芯-KY", 26),
    ("AI 伺服器/電子", "2317", "鴻海", 125),
    ("AI 伺服器/電子", "2382", "廣達", 65),
    ("AI 伺服器/電子", "2308", "台達電", 58),
    ("AI 伺服器/電子", "3231", "緯創", 34),
    ("AI 伺服器/電子", "6669", "緯穎", 32),
    ("AI 伺服器/電子", "2357", "華碩", 28),
    ("AI 伺服器/電子", "2376", "技嘉", 20),
    ("金融保險", "2881", "富邦金", 68),
    ("金融保險", "2882", "國泰金", 58),
    ("金融保險", "2891", "中信金", 44),
    ("金融保險", "2886", "兆豐金", 36),
    ("金融保險", "2884", "玉山金", 32),
    ("金融保險", "2885", "元大金", 28),
    ("航運/傳產", "2603", "長榮", 42),
    ("航運/傳產", "2609", "陽明", 24),
    ("航運/傳產", "2615", "萬海", 20),
    ("航運/傳產", "1301", "台塑", 26),
    ("航運/傳產", "2002", "中鋼", 24),
    ("電信/內需", "2412", "中華電", 52),
    ("電信/內需", "1216", "統一", 35),
    ("電信/內需", "3045", "台灣大", 24),
]

SP500_WATCHLIST = [
    ("TECHNOLOGY", "NVDA", "Nvidia Corp", 340),
    ("TECHNOLOGY", "AAPL", "Apple Inc", 330),
    ("TECHNOLOGY", "MSFT", "Microsoft Corp", 310),
    ("TECHNOLOGY", "AVGO", "Broadcom Inc", 115),
    ("TECHNOLOGY", "MU", "Micron Tech", 70),
    ("TECHNOLOGY", "AMD", "Advanced Micro Devices", 68),
    ("TECHNOLOGY", "INTC", "Intel Corp", 36),
    ("TECHNOLOGY", "QCOM", "Qualcomm Inc", 32),
    ("TECHNOLOGY", "CRM", "Salesforce Inc", 55),
    ("TECHNOLOGY", "ORCL", "Oracle Corp", 52),
    ("TECHNOLOGY", "PLTR", "Palantir Tech", 48),
    ("TECHNOLOGY", "PANW", "Palo Alto Networks", 42),
    ("TECHNOLOGY", "CRWD", "CrowdStrike", 38),
    ("TECHNOLOGY", "AMAT", "Applied Materials", 40),
    ("COMMUNICATION SERVICES", "GOOGL", "Alphabet Inc", 230),
    ("COMMUNICATION SERVICES", "META", "Meta Platforms", 155),
    ("COMMUNICATION SERVICES", "NFLX", "Netflix Inc", 48),
    ("COMMUNICATION SERVICES", "DIS", "Walt Disney Co", 40),
    ("FINANCIAL", "BRK-B", "Berkshire Hathaway", 135),
    ("FINANCIAL", "JPM", "JPMorgan Chase", 110),
    ("FINANCIAL", "V", "Visa Inc", 85),
    ("FINANCIAL", "MA", "Mastercard Inc", 72),
    ("FINANCIAL", "BAC", "Bank of America", 55),
    ("FINANCIAL", "GS", "Goldman Sachs", 42),
    ("CONSUMER CYCLICAL", "AMZN", "Amazon.com Inc", 215),
    ("CONSUMER CYCLICAL", "TSLA", "Tesla Inc", 145),
    ("CONSUMER CYCLICAL", "HD", "Home Depot", 62),
    ("HEALTHCARE", "LLY", "Eli Lilly & Co", 130),
    ("HEALTHCARE", "JNJ", "Johnson & Johnson", 65),
    ("HEALTHCARE", "UNH", "UnitedHealth Group", 58),
    ("CONSUMER DEFENSIVE", "WMT", "Walmart Inc", 95),
    ("CONSUMER DEFENSIVE", "COST", "Costco Wholesale", 75),
    ("CONSUMER DEFENSIVE", "KO", "Coca-Cola Co", 52),
    ("INDUSTRIALS", "GE", "GE Aerospace", 54),
    ("INDUSTRIALS", "CAT", "Caterpillar Inc", 48),
    ("ENERGY", "XOM", "Exxon Mobil", 75),
    ("ENERGY", "CVX", "Chevron Corp", 52),
]

YAHOO_SERIES = {
    "sp500": ("^GSPC", "[真實 Yahoo] S&P 500 指數", "點"),
    "taiex": ("^TWII", "[真實 Yahoo] 台股加權指數 TAIEX", "點"),
    "gold": ("GC=F", "[真實 Yahoo] 黃金期貨 (USD/oz)", "USD"),
    "wti": ("CL=F", "[真實 Yahoo] WTI 原油期貨 (USD/bbl)", "USD"),
}

MARKET_SNAPSHOT_SYMBOLS = {
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "taiex": "^TWII",
    "nikkei": "^N225",
    "gold": "GC=F",
    "wti": "CL=F",
    "copper": "HG=F",
    "vix": "^VIX",
}


def fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 MacroPulse/2.0"})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_twse_heatmap() -> list:
    print("1/4 抓取 TWSE 台股 28 檔每日收盤...")
    raw = fetch_url("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL")
    rows = json.loads(raw)
    by_code = {r.get("Code", "").strip(): r for r in rows}
    result = []
    for sector, code, name, cap in TW_WATCHLIST:
        row = by_code.get(code)
        pct = 0.0
        if row:
            try:
                close_p = float(row.get("ClosingPrice", "0").replace(",", ""))
                chg = float(row.get("Change", "0").replace(",", ""))
                prev_p = close_p - chg
                if prev_p > 0:
                    pct = round((chg / prev_p) * 100, 2)
            except ValueError:
                pct = 0.0
        result.append({"sector": sector, "ticker": code, "name": name, "cap": cap, "d1": pct, "w1": pct, "ytd": pct})
    return result


def fetch_yahoo_quote_changes(symbol: str):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=ytd&interval=1d"
    data = json.loads(fetch_url(url))
    res = data["chart"]["result"][0]
    closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
    if len(closes) < 2:
        return None
    latest = closes[-1]
    prev_1d = closes[-2]
    prev_1w = closes[-6] if len(closes) >= 6 else closes[0]
    first_ytd = closes[0]
    return {
        "price": round(latest, 2),
        "d1": round((latest - prev_1d) / prev_1d * 100, 2) if prev_1d else 0.0,
        "w1": round((latest - prev_1w) / prev_1w * 100, 2) if prev_1w else 0.0,
        "ytd": round((latest - first_ytd) / first_ytd * 100, 2) if first_ytd else 0.0,
    }


def fetch_yahoo_monthly_series(symbol: str, months: int = 24):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=2y&interval=1mo"
    data = json.loads(fetch_url(url))
    res = data["chart"]["result"][0]
    ts_list = res.get("timestamp", [])
    closes = res["indicators"]["quote"][0]["close"]
    labels, vals = [], []
    for ts, c in zip(ts_list, closes):
        if c is None:
            continue
        labels.append(datetime.utcfromtimestamp(ts).strftime("%Y-%m"))
        vals.append(round(c, 2))
    return labels[-months:], vals[-months:]


def fetch_fred_monthly(series_id: str, months: int = 36):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    text = fetch_url(url)
    reader = csv.reader(io.StringIO(text))
    next(reader, None)
    monthly = {}
    for row in reader:
        if len(row) >= 2 and row[1] not in ("", "."):
            try:
                monthly[row[0][:7]] = float(row[1])
            except ValueError:
                continue
    keys = sorted(monthly.keys())[-months:]
    return keys, [round(monthly[k], 2) for k in keys]


def compute_yoy(labels, vals, months: int = 24):
    if len(vals) <= 12:
        return labels, vals
    out_l, out_v = [], []
    for i in range(12, len(vals)):
        if vals[i - 12] > 0:
            out_l.append(labels[i])
            out_v.append(round((vals[i] / vals[i - 12] - 1) * 100, 2))
    return out_l[-months:], out_v[-months:]


def main():
    import urllib.parse  # ensure available
    globals()["urllib"].parse = urllib.parse

    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "tw_heatmap": [],
        "sp500_heatmap": [],
        "snapshots": {},
        "series": {},
    }

    try:
        payload["tw_heatmap"] = fetch_twse_heatmap()
    except Exception as e:
        print(f"TWSE 略過: {e}")

    print("2/4 抓取 Yahoo Finance 美股熱力圖成分股...")
    for sector, ticker, name, cap in SP500_WATCHLIST:
        try:
            q = fetch_yahoo_quote_changes(ticker)
            if q:
                payload["sp500_heatmap"].append({
                    "sector": sector, "ticker": ticker, "name": name, "cap": cap,
                    "d1": q["d1"], "w1": q["w1"], "ytd": q["ytd"],
                })
        except Exception:
            continue

    print("3/4 抓取全球大盤指數與原物料報價及 24 個月序列...")
    for key, sym in MARKET_SNAPSHOT_SYMBOLS.items():
        try:
            q = fetch_yahoo_quote_changes(sym)
            if q:
                payload["snapshots"][key] = q
        except Exception:
            continue

    for key, (sym, title, unit) in YAHOO_SERIES.items():
        try:
            l, v = fetch_yahoo_monthly_series(sym, months=24)
            if l:
                payload["series"][key] = {"name": title, "unit": unit, "labels": l, "data": v}
        except Exception:
            continue

    print("4/4 抓取 FRED 官方總經序列 (殖利率/CPI/M2/失業率)...")
    for key, fid, title, unit, is_yoy in [
        ("us10y", "DGS10", "[真實 FRED] 美國 10Y 公債殖利率 (%)", "%", False),
        ("us2y", "DGS2", "[真實 FRED] 美國 2Y 公債殖利率 (%)", "%", False),
        ("spread10y2y", "T10Y2Y", "[真實 FRED] 美債 10Y-2Y 利差 (%)", "%", False),
        ("usCpi", "CPIAUCSL", "[真實 FRED] 美國 CPI 年增率 (%)", "%", True),
        ("usM2", "M2SL", "[真實 FRED] 美國 M2 年增率 (%)", "%", True),
        ("usUnrate", "UNRATE", "[真實 FRED] 美國失業率 (%)", "%", False),
    ]:
        try:
            l, v = fetch_fred_monthly(fid, months=36 if is_yoy else 24)
            if is_yoy:
                l, v = compute_yoy(l, v, months=24)
            if l:
                payload["series"][key] = {"name": title, "unit": unit, "labels": l, "data": v}
                payload["snapshots"][key] = v[-1]
        except Exception as e:
            print(f"FRED {fid} 略過: {e}")

    with open("macro_live_data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"完成！已寫入 macro_live_data.json（美股 {len(payload['sp500_heatmap'])} 檔、台股 {len(payload['tw_heatmap'])} 檔、序列 {len(payload['series'])} 組）")


if __name__ == "__main__":
    main()
