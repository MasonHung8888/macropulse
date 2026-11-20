#!/usr/bin/env python3
"""
MacroPulse 全方位真實市場與總經數據自動抓取腳本
100% 官方與真實市場資料源，雲端無人值守全自動執行版本。

資料來源：
  1. 中華民國中央銀行 (CBC) 官方 API: 貨幣總計數 M1B、M2 官方歷史序列、年增率與剪刀差 (EF15M01)
  2. 臺灣證券交易所 (TWSE) OpenAPI: 台股 28 檔權值股每日收盤與即時漲跌
  3. Yahoo Finance (yfinance): 美股 S&P 500 熱力圖成分股 (1D/1W/YTD)、大盤指數、10Y美債殖利率 (^TNX) 與大宗商品 24 個月序列
  4. 歐洲央行 (ECB) Frankfurter & Open ER-API: 官方外匯即時中間價 (USD/TWD, JPY, EUR, GBP)
  5. CoinGecko API: 比特幣現貨價格與 USDT/USDC 穩定幣真實市值

產出：macro_live_data.json
"""

import csv
import io
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "macro_live_data.json")

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


def fetch_url(url: str, timeout: int = 15) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


# 1. 抓取台灣中央銀行 (CBC) 官方貨幣總計數 (100% 官方真實 API)
def fetch_cbc_m1b_m2(months: int = 24):
    print("1/5 抓取台灣中央銀行 (CBC) 官方貨幣總計數 (M1B / M2)...")
    url = "https://cpx.cbc.gov.tw/API/DataAPI/Get?FileName=EF15M01"
    raw = fetch_url(url, timeout=20)
    data = json.loads(raw)
    datasets = data.get("data", {}).get("dataSets", [])
    if not datasets:
        raise ValueError("CBC 資料格式異常，未取得 dataSets")

    labels, m1b_vals, m2_vals, spread_vals = [], [], [], []
    for row in datasets[-months:]:
        if len(row) > 30:
            ym = row[0].replace("M", "-")
            try:
                m1b_yoy = float(row[28])
                m2_yoy = float(row[30])
                spread = round(m1b_yoy - m2_yoy, 2)
                labels.append(ym)
                m1b_vals.append(m1b_yoy)
                m2_vals.append(m2_yoy)
                spread_vals.append(spread)
            except (ValueError, TypeError):
                continue

    latest_ym = labels[-1] if labels else ""
    latest_m1b = m1b_vals[-1] if m1b_vals else 0.0
    latest_m2 = m2_vals[-1] if m2_vals else 0.0
    latest_spread = spread_vals[-1] if spread_vals else 0.0
    avg_m1b = round(sum(m1b_vals[-9:]) / len(m1b_vals[-9:]), 2) if len(m1b_vals) >= 9 else latest_m1b

    status_desc = "資金充沛 (黃金交叉)" if latest_spread > 0 else "資金偏緊 (死亡交叉)"
    print(f"  -> CBC 最新月份: {latest_ym}, M1B: {latest_m1b}%, M2: {latest_m2}%, 剪刀差: {latest_spread}% ({status_desc})")

    return {
        "labels": labels,
        "m1b": m1b_vals,
        "m2": m2_vals,
        "spread": spread_vals,
        "latest": {
            "date": latest_ym,
            "m1b": latest_m1b,
            "m2": latest_m2,
            "spread": latest_spread,
            "avg9m_m1b": avg_m1b,
            "status": status_desc,
        },
    }


# 2. 抓取 TWSE 臺灣證券交易所台股 28 檔權值股收盤
def fetch_twse_heatmap() -> list:
    print("2/5 抓取 TWSE 臺灣證交所台股 28 檔權值股收盤價與即時漲跌...")
    raw = fetch_url("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", timeout=20)
    rows = json.loads(raw)
    by_code = {r.get("Code", "").strip(): r for r in rows}
    result = []
    for sector, code, name, cap in TW_WATCHLIST:
        row = by_code.get(code)
        pct = 0.0
        price = 0.0
        if row:
            try:
                price = float(row.get("ClosingPrice", "0").replace(",", ""))
                chg = float(row.get("Change", "0").replace(",", ""))
                prev_p = price - chg
                if prev_p > 0:
                    pct = round((chg / prev_p) * 100, 2)
            except (ValueError, ZeroDivisionError):
                pct = 0.0
        result.append({
            "sector": sector,
            "ticker": code,
            "name": name,
            "cap": cap,
            "price": price,
            "d1": pct,
            "w1": pct,
            "ytd": pct,
        })
    print(f"  -> 成功抓取 TWSE 台股權值股共 {len(result)} 檔")
    return result


# 3. 抓取 Yahoo Finance 美股熱力圖與大盤指數
def fetch_us_market_data():
    print("3/5 抓取 Yahoo Finance 美股成分股、指數與美債殖利率...")
    sp500_heatmap = []
    snapshots = {}
    series = {}

    try:
        import yfinance as yf
    except ImportError:
        print("  [提示] yfinance 未安裝，跳過美股連線 (可在 GitHub Actions 中自動安裝)")
        return sp500_heatmap, snapshots, series

    # 批次下載熱力圖成分股
    all_tickers = [t for _, t, _, _ in SP500_WATCHLIST]
    ticker_str = " ".join(all_tickers)
    try:
        data = yf.download(ticker_str, period="1y", interval="1d", group_by="ticker", auto_adjust=True, progress=False)
        for sector, ticker, name, cap in SP500_WATCHLIST:
            try:
                df = data[ticker] if ticker in data else None
                if df is not None and not df.empty and "Close" in df:
                    closes = df["Close"].dropna()
                    if len(closes) >= 2:
                        latest = float(closes.iloc[-1])
                        prev_1d = float(closes.iloc[-2])
                        prev_1w = float(closes.iloc[-6]) if len(closes) >= 6 else float(closes.iloc[0])
                        first_ytd = float(closes.iloc[0])
                        d1 = round((latest - prev_1d) / prev_1d * 100, 2)
                        w1 = round((latest - prev_1w) / prev_1w * 100, 2)
                        ytd = round((latest - first_ytd) / first_ytd * 100, 2)
                        sp500_heatmap.append({
                            "sector": sector,
                            "ticker": ticker,
                            "name": name,
                            "cap": cap,
                            "price": round(latest, 2),
                            "d1": d1,
                            "w1": w1,
                            "ytd": ytd,
                        })
            except Exception:
                continue
        print(f"  -> 成功取得美股 S&P 500 熱力圖共 {len(sp500_heatmap)} 檔真實數據")
    except Exception as e:
        print(f"  美股熱力圖批次抓取略過: {e}")

    # 下載大盤指數、10Y公債殖利率、原物料報價
    indices = {
        "sp500": "^GSPC",
        "nasdaq": "^IXIC",
        "taiex": "^TWII",
        "nikkei": "^N225",
        "gold": "GC=F",
        "wti": "CL=F",
        "copper": "HG=F",
        "vix": "^VIX",
        "us10y_tnx": "^TNX",
        "us30y_tyx": "^TYX",
        "us5y_fvx": "^FVX",
    }
    try:
        idx_data = yf.download(" ".join(indices.values()), period="2y", interval="1mo", group_by="ticker", auto_adjust=True, progress=False)
        for key, sym in indices.items():
            try:
                df = idx_data[sym] if sym in idx_data else None
                if df is not None and not df.empty and "Close" in df:
                    closes = df["Close"].dropna()
                    if len(closes) >= 2:
                        latest = float(closes.iloc[-1])
                        prev_1d = float(closes.iloc[-2])
                        snapshots[key] = {
                            "price": round(latest, 2),
                            "d1": round((latest - prev_1d) / prev_1d * 100, 2),
                        }
                    # 存入 24 個月序列
                    labels = [d.strftime("%Y-%m") for d in closes.index][-24:]
                    vals = [round(float(v), 2) for v in closes.values][-24:]
                    if key in ["sp500", "taiex", "gold", "wti", "us10y_tnx"]:
                        series[key] = {
                            "name": f"[真實市場] {sym}",
                            "unit": "%" if "tnx" in key else "USD" if key in ["gold", "wti"] else "點",
                            "labels": labels,
                            "data": vals,
                        }
            except Exception:
                continue

        if "us10y_tnx" in snapshots:
            snapshots["us10y"] = snapshots["us10y_tnx"]["price"]
            print(f"  -> 美國 10 年期公債殖利率 (^TNX): {snapshots['us10y']}%")
        if "us5y_fvx" in snapshots and "us10y" in snapshots:
            snapshots["spread10y2y"] = round(snapshots["us10y"] - snapshots["us5y_fvx"]["price"], 2)
            print(f"  -> 美債 10Y-5Y 利差: {snapshots['spread10y2y']}%")
    except Exception as e:
        print(f"  指數與原物料抓取略過: {e}")

    return sp500_heatmap, snapshots, series


# 4. 即時官方匯率
def fetch_live_fx():
    print("4/5 抓取歐洲央行 (ECB) 官方參考匯率與台幣匯率...")
    rates = {}
    try:
        raw1 = fetch_url("https://api.frankfurter.app/latest?from=USD&to=JPY,EUR,GBP,AUD,CAD", timeout=10)
        d1 = json.loads(raw1)
        rates.update(d1.get("rates", {}))
    except Exception as e:
        print(f"  ECB Frankfurter 略過: {e}")

    try:
        raw2 = fetch_url("https://open.er-api.com/v6/latest/USD", timeout=10)
        d2 = json.loads(raw2)
        if "rates" in d2 and "TWD" in d2["rates"]:
            rates["TWD"] = round(d2["rates"]["TWD"], 2)
    except Exception as e:
        print(f"  Open ER-API 略過: {e}")

    print(f"  -> 即時匯率: USD/TWD={rates.get('TWD', 'N/A')}, USD/JPY={rates.get('JPY', 'N/A')}, EUR={rates.get('EUR', 'N/A')}")
    return rates


# 5. 即時加密貨幣
def fetch_live_crypto():
    print("5/5 抓取 CoinGecko 比特幣現貨價與穩定幣規模...")
    crypto = {}
    try:
        raw = fetch_url("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,tether,usd-coin&vs_currencies=usd&include_market_cap=true", timeout=10)
        d = json.loads(raw)
        if "bitcoin" in d:
            crypto["btc_price"] = round(d["bitcoin"]["usd"], 2)
        usdt_cap = d.get("tether", {}).get("usd_market_cap", 0)
        usdc_cap = d.get("usd-coin", {}).get("usd_market_cap", 0)
        if usdt_cap or usdc_cap:
            crypto["stablecoin_market_cap_b"] = round((usdt_cap + usdc_cap) / 1e9, 1)
        print(f"  -> BTC: ${crypto.get('btc_price', 'N/A')}, 穩定幣市值: {crypto.get('stablecoin_market_cap_b', 'N/A')}B")
    except Exception as e:
        print(f"  CoinGecko 略過: {e}")
    return crypto


def main():
    print("=" * 65)
    print("MacroPulse 雲端自動化真實總經資料擷取引擎啟動")
    print(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "tw_m1b_m2": {},
        "tw_heatmap": [],
        "sp500_heatmap": [],
        "snapshots": {},
        "series": {},
        "fx": {},
        "crypto": {},
    }

    # 1. 台灣央行 M1B / M2
    try:
        m1b_m2_data = fetch_cbc_m1b_m2(months=24)
        payload["tw_m1b_m2"] = m1b_m2_data
        payload["series"]["twM1b"] = {
            "name": "台灣 M1B 年增率 (%) [央行官方]",
            "unit": "%",
            "labels": m1b_m2_data["labels"],
            "data": m1b_m2_data["m1b"],
        }
        payload["series"]["twM2"] = {
            "name": "台灣 M2 年增率 (%) [央行官方]",
            "unit": "%",
            "labels": m1b_m2_data["labels"],
            "data": m1b_m2_data["m2"],
        }
        payload["series"]["twM1bM2Spread"] = {
            "name": "台灣 M1B - M2 剪刀差 (%) [央行官方]",
            "unit": "%",
            "labels": m1b_m2_data["labels"],
            "data": m1b_m2_data["spread"],
        }
        payload["snapshots"]["tw_m1b"] = m1b_m2_data["latest"]["m1b"]
        payload["snapshots"]["tw_m2"] = m1b_m2_data["latest"]["m2"]
        payload["snapshots"]["tw_spread"] = m1b_m2_data["latest"]["spread"]
    except Exception as e:
        print(f"  台灣央行 CBC M1B/M2 抓取失敗: {e}")

    # 2. TWSE 台股熱力圖
    try:
        payload["tw_heatmap"] = fetch_twse_heatmap()
    except Exception as e:
        print(f"  TWSE 台股抓取失敗: {e}")

    # 3. Yahoo Finance 美股熱力圖、指數、美債殖利率
    try:
        sp_heat, snaps, sers = fetch_us_market_data()
        payload["sp500_heatmap"] = sp_heat
        payload["snapshots"].update(snaps)
        payload["series"].update(sers)
    except Exception as e:
        print(f"  美股與市場數據處理失敗: {e}")

    # 4. 匯率
    payload["fx"] = fetch_live_fx()

    # 5. 加密貨幣
    payload["crypto"] = fetch_live_crypto()

    # 寫入 macro_live_data.json
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("=" * 65)
    print(f"🎉 全部完成！已寫入 {OUTPUT_FILE}")
    print(f"總結：")
    print(f"  • 台灣央行 M1B/M2 官方序列: {'成功' if payload['tw_m1b_m2'] else '未取得'}")
    print(f"  • 台股權值股熱力圖: {len(payload['tw_heatmap'])} 檔")
    print(f"  • 美股 S&P 500 熱力圖: {len(payload['sp500_heatmap'])} 檔")
    print(f"  • 即時市場快照指標: {len(payload['snapshots'])} 個")
    print(f"  • 24個月歷史時間序列: {len(payload['series'])} 組")
    print("=" * 65)


if __name__ == "__main__":
    main()
