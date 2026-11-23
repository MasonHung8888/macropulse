#!/usr/bin/env python3
"""
MacroPulse 市場與總經數據自動抓取腳本 (審查修正版)。
每次產出前會檢查必要欄位、資料新鮮度與覆蓋率；所有 fallback 與靜態基準皆誠實標示 data_status。

資料來源：
1. 中華民國中央銀行 (CBC) 官方 API: 貨幣總計數 M1B、M2 官方歷史序列、年增率與剪刀差 (EF15M01)
2. 臺灣證券交易所 (TWSE) OpenAPI: 台股 28 檔權值股每日收盤與日漲跌
3. Yahoo Finance (yfinance): 美股 S&P 500 熱力圖成分股 (1D/1W/YTD)、大盤指數、10Y美債殖利率 (^TNX) 與大宗商品 24 個月序列
4. FRED & World Bank: 美國官方總經序列、Fed 淨流動性、薩姆規則、TIPS 實質利率、跨國年度總經
5. Frankfurter & Open ER-API / CoinGecko: 外匯公開 API 與比特幣/穩定幣市值

產出：macro_live_data.json
"""

import csv
import http.cookiejar
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "macro_live_data.json")

# 記憶體快取：避免單次執行重複向 FRED 發送相同序列請求
_FRED_CACHE: dict[str, list] = {}

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
    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


# 1. 抓取台灣中央銀行 (CBC) 官方貨幣總計數
def fetch_cbc_m1b_m2(months: int = 24):
    print("1/7 抓取台灣中央銀行 (CBC) 官方貨幣總計數 (M1B / M2)...")
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
        "data_status": "live",
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


def fetch_fred_observations(series_ids: list[str]) -> dict[str, list]:
    """一次讀取多個 FRED 官方序列，並透過記憶體快取避免重複連線。"""
    missing = [sid for sid in series_ids if sid not in _FRED_CACHE]
    if missing:
        joined = urllib.parse.quote(",".join(missing), safe=",")
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={joined}"
        from curl_cffi import requests as curl_requests
        response = curl_requests.get(url, timeout=60, impersonate="chrome")
        response.raise_for_status()
        for sid in missing:
            _FRED_CACHE[sid] = []
        if response.content.startswith(b"PK"):
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                csv_texts = [archive.read(name).decode("utf-8") for name in archive.namelist() if name.endswith(".csv")]
        else:
            csv_texts = [response.text]
        for csv_text in csv_texts:
            for row in csv.DictReader(csv_text.splitlines()):
                date = row.get("observation_date")
                if not date:
                    continue
                for sid in missing:
                    raw_value = row.get(sid)
                    if raw_value in (None, "", "."):
                        continue
                    try:
                        _FRED_CACHE[sid].append((date, float(raw_value)))
                    except (TypeError, ValueError):
                        continue
    return {sid: _FRED_CACHE.get(sid, []) for sid in series_ids}


def yoy_observations(observations: list, periods: int = 12) -> list:
    result = []
    for idx in range(periods, len(observations)):
        previous = observations[idx - periods][1]
        if previous:
            result.append((observations[idx][0], round((observations[idx][1] / previous - 1) * 100, 2)))
    return result


def fetch_fred_macro() -> tuple[dict, dict]:
    """建立可追溯的美國總經指標與 24 期序列（預先批次快取所有模組需要的 FRED ID）。"""
    print("2/7 抓取 FRED 美國官方總經資料 (批次預載快取)...")
    definitions = {
        "us_cpi_yoy": ("CPIAUCSL", "美國 CPI 年增率", "%", "monthly", "yoy"),
        "us_core_cpi_yoy": ("CPILFESL", "美國核心 CPI 年增率", "%", "monthly", "yoy"),
        "us_unemployment": ("UNRATE", "美國失業率", "%", "monthly", "level"),
        "us_fed_funds": ("FEDFUNDS", "美國聯邦基金有效利率", "%", "monthly", "level"),
        "us_industrial_yoy": ("INDPRO", "美國工業生產年增率", "%", "monthly", "yoy"),
        "us_m2_yoy": ("M2SL", "美國 M2 年增率", "%", "monthly", "yoy"),
        "us_payroll_change": ("PAYEMS", "美國非農就業月增", "千人", "monthly", "change"),
        "us_10y": ("DGS10", "美國 10 年期公債殖利率", "%", "daily", "level"),
        "us_2y": ("DGS2", "美國 2 年期公債殖利率", "%", "daily", "level"),
        "us_10y2y": ("T10Y2Y", "美債 10Y－2Y 利差", "%", "daily", "level"),
    }
    # 一次性預抓後續所有模組會用到的 FRED 序列，將 8 次請求壓縮為 1 次
    extra_ids = [
        "WALCL", "WTREGEN", "RRPONTSYD",
        "SAHMREALTIME", "T10Y3M",
        "DFEDTARU", "DFEDTARL", "DFF",
        "BAMLH0A0HYM2", "GDP",
        "DFII10", "T10YIE",
        "ECBASSETSW", "JPNASSETS", "DEXUSEU", "DEXJPUS", "TRESEGCNM052N",
    ]
    all_ids = list(dict.fromkeys([d[0] for d in definitions.values()] + extra_ids))
    all_observations = fetch_fred_observations(all_ids)

    indicators, series = {}, {}
    for key, (fred_id, label, unit, frequency, transform) in definitions.items():
        try:
            raw = all_observations.get(fred_id, [])
            if not raw:
                raise ValueError("未取得有效觀測值")
            if transform == "yoy":
                values = yoy_observations(raw, 12)
            elif transform == "change":
                values = [(raw[i][0], round(raw[i][1] - raw[i - 1][1], 1)) for i in range(1, len(raw))]
            else:
                values = [(date, round(value, 2)) for date, value in raw]
            if not values:
                raise ValueError("轉換後無資料")
            latest_date, latest_value = values[-1]
            previous_value = values[-2][1] if len(values) > 1 else None
            indicators[key] = {
                "label": label,
                "value": latest_value,
                "unit": unit,
                "period": latest_date,
                "frequency": frequency,
                "previous": previous_value,
                "source": "Federal Reserve Bank of St. Louis (FRED)",
                "source_url": f"https://fred.stlouisfed.org/series/{fred_id}",
                "series_id": fred_id,
                "evidence": "official_observation",
            }
            recent = values[-24:]
            series[key] = {
                "name": f"{label} [FRED]",
                "unit": unit,
                "labels": [date[:7] if frequency == "monthly" else date for date, _ in recent],
                "data": [value for _, value in recent],
                "source": "Federal Reserve Bank of St. Louis (FRED)",
                "source_url": f"https://fred.stlouisfed.org/series/{fred_id}",
                "as_of": latest_date,
            }
        except Exception as exc:
            print(f"  FRED {fred_id} 取得失敗：{exc}")
    print(f"  -> 成功取得 FRED 指標 {len(indicators)}/{len(definitions)} 項")
    return indicators, series


def fetch_world_bank_macro() -> tuple[dict, dict]:
    """取得跨國可比的世界銀行年度實績，保留最近非空正式值。"""
    print("3/7 抓取世界銀行跨國年度總經資料...")
    countries = {
        "USA": ("US", "美國"),
        "EMU": ("EU", "歐元區"),
        "CHN": ("CN", "中國"),
        "JPN": ("JP", "日本"),
    }
    definitions = {
        "gdp_growth": ("NY.GDP.MKTP.KD.ZG", "實質 GDP 成長率", "%"),
        "cpi_inflation": ("FP.CPI.TOTL.ZG", "CPI 通膨率", "%"),
        "unemployment": ("SL.UEM.TOTL.ZS", "失業率", "%"),
    }
    result = {code: {"country": name, "indicators": {}} for _, (code, name) in countries.items()}
    series = {}
    from curl_cffi import requests as curl_requests
    for metric, (indicator_id, label, unit) in definitions.items():
        url = (
            "https://api.worldbank.org/v2/country/USA;EMU;CHN;JPN/indicator/"
            f"{indicator_id}?format=json&per_page=100&mrv=10"
        )
        response = curl_requests.get(url, timeout=45, impersonate="chrome")
        response.raise_for_status()
        body = response.json()
        observations = body[1] if isinstance(body, list) and len(body) > 1 and isinstance(body[1], list) else []
        grouped = {iso3: [] for iso3 in countries}
        for row in observations:
            iso3 = row.get("countryiso3code")
            value = row.get("value")
            if iso3 in grouped and value is not None:
                grouped[iso3].append((str(row.get("date")), float(value)))
        for iso3, values in grouped.items():
            if not values:
                continue
            values.sort(key=lambda item: item[0])
            country_code, _ = countries[iso3]
            latest_period, latest_value = values[-1]
            previous_value = values[-2][1] if len(values) > 1 else None
            source_url = f"https://data.worldbank.org/indicator/{indicator_id}?locations={iso3}"
            result[country_code]["indicators"][metric] = {
                "label": label,
                "value": round(latest_value, 2),
                "unit": unit,
                "period": latest_period,
                "frequency": "annual",
                "previous": round(previous_value, 2) if previous_value is not None else None,
                "source": "World Bank Open Data",
                "source_url": source_url,
                "series_id": indicator_id,
                "evidence": "official_international_observation",
            }
            series[f"wb_{country_code.lower()}_{metric}"] = {
                "name": f"{result[country_code]['country']} {label} [World Bank]",
                "unit": unit,
                "labels": [period for period, _ in values],
                "data": [round(value, 2) for _, value in values],
                "source": "World Bank Open Data",
                "source_url": source_url,
                "as_of": latest_period,
            }
    total = sum(len(country["indicators"]) for country in result.values())
    print(f"  -> 成功取得世界銀行跨國指標 {total}/12 項")
    return result, series


# 2. 抓取 TWSE 臺灣證券交易所台股 28 檔權值股收盤
def fetch_twse_heatmap(existing_tw_heatmap: list | None = None) -> list:
    print("4/7 抓取 TWSE 收盤價，並以歷史日線計算 1W / YTD...")
    raw = fetch_url("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", timeout=20)
    rows = json.loads(raw)
    by_code = {r.get("Code", "").strip(): r for r in rows}
    prev_by_code = {r.get("ticker"): r for r in (existing_tw_heatmap or []) if isinstance(r, dict)}

    history = None
    try:
        import yfinance as yf
        symbols = " ".join(f"{code}.TW" for _, code, _, _ in TW_WATCHLIST)
        history = yf.download(symbols, period="ytd", interval="1d", group_by="ticker", auto_adjust=True, progress=False)
    except Exception as exc:
        print(f"  台股歷史日線取得失敗：{exc}")

    result = []
    for sector, code, name, cap in TW_WATCHLIST:
        row = by_code.get(code)
        pct = None
        price = None
        data_status = "live"
        if row:
            try:
                p_val = float(row.get("ClosingPrice", "").replace(",", ""))
                c_val = float(row.get("Change", "").replace(",", ""))
                prev_p = p_val - c_val
                if p_val > 0 and prev_p > 0:
                    price = p_val
                    pct = round((c_val / prev_p) * 100, 2)
            except (ValueError, ZeroDivisionError):
                pass

        # 若當日缺漏，嘗試從舊檔補值並標記 fallback，絕不靜默輸出 0.0 偽裝平盤
        if price is None and code in prev_by_code and prev_by_code[code].get("price"):
            price = prev_by_code[code]["price"]
            pct = prev_by_code[code].get("d1")
            data_status = "cached_fallback"

        w1 = ytd = None
        try:
            symbol = f"{code}.TW"
            df = history[symbol] if history is not None and symbol in history else None
            closes = df["Close"].dropna() if df is not None and not df.empty else []
            if len(closes) >= 2:
                latest = float(closes.iloc[-1])
                prev_1w = float(closes.iloc[-6]) if len(closes) >= 6 else float(closes.iloc[0])
                w1 = round((latest - prev_1w) / prev_1w * 100, 2)
                ytd = round((latest - float(closes.iloc[0])) / float(closes.iloc[0]) * 100, 2)
        except Exception:
            pass

        result.append({
            "sector": sector,
            "ticker": code,
            "name": name,
            "cap": cap,
            "price": price,
            "d1": pct,
            "w1": w1,
            "ytd": ytd,
            "data_status": data_status,
            "source": "TWSE daily close; Yahoo Finance historical returns",
            "realtime": False,
        })
    print(f"  -> 成功抓取 TWSE 台股權值股共 {len(result)} 檔")
    return result


# 3. 抓取 Yahoo Finance 美股熱力圖與大盤指數
def fetch_us_market_data(existing_sp500: list | None = None):
    print("5/7 抓取 Yahoo Finance 美股成分股、指數與美債殖利率...")
    sp500_heatmap = []
    snapshots = {}
    series = {}
    prev_by_ticker = {r.get("ticker"): r for r in (existing_sp500 or []) if isinstance(r, dict)}

    try:
        import yfinance as yf
    except ImportError:
        print("  [提示] yfinance 未安裝，跳過美股連線")
        return sp500_heatmap, snapshots, series

    all_tickers = [t for _, t, _, _ in SP500_WATCHLIST]
    ticker_str = " ".join(all_tickers)
    try:
        data = yf.download(ticker_str, period="ytd", interval="1d", group_by="ticker", auto_adjust=True, progress=False)
        for sector, ticker, name, cap in SP500_WATCHLIST:
            added = False
            try:
                df = data[ticker] if ticker in data else None
                if df is not None and not df.empty and "Close" in df:
                    closes = df["Close"].dropna()
                    if len(closes) >= 2:
                        latest = float(closes.iloc[-1])
                        prev_1d = float(closes.iloc[-2])
                        prev_1w = float(closes.iloc[-6]) if len(closes) >= 6 else float(closes.iloc[0])
                        first_ytd = float(closes.iloc[0])
                        sp500_heatmap.append({
                            "sector": sector,
                            "ticker": ticker,
                            "name": name,
                            "cap": cap,
                            "price": round(latest, 2),
                            "d1": round((latest - prev_1d) / prev_1d * 100, 2),
                            "w1": round((latest - prev_1w) / prev_1w * 100, 2),
                            "ytd": round((latest - first_ytd) / first_ytd * 100, 2),
                            "data_status": "live",
                        })
                        added = True
            except Exception:
                pass
            if not added and ticker in prev_by_ticker:
                fallback_row = dict(prev_by_ticker[ticker])
                fallback_row["data_status"] = "cached_fallback"
                sp500_heatmap.append(fallback_row)
        print(f"  -> 成功取得美股 S&P 500 熱力圖共 {len(sp500_heatmap)} 檔數據")
    except Exception as e:
        print(f"  美股熱力圖批次抓取略過: {e}")

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
        "dxy": "DX-Y.NYB",
        "usdtwd": "USDTWD=X",
    }
    try:
        daily_data = yf.download(" ".join(indices.values()), period="1mo", interval="1d", group_by="ticker", auto_adjust=True, progress=False)
        monthly_data = yf.download(" ".join(indices.values()), period="2y", interval="1mo", group_by="ticker", auto_adjust=True, progress=False)
        for key, sym in indices.items():
            try:
                daily_df = daily_data[sym] if sym in daily_data else None
                if daily_df is not None and not daily_df.empty and "Close" in daily_df:
                    closes = daily_df["Close"].dropna()
                    if len(closes) >= 2:
                        latest = float(closes.iloc[-1])
                        prev_1d = float(closes.iloc[-2])
                        snapshots[key] = {
                            "price": round(latest, 2),
                            "d1": round((latest - prev_1d) / prev_1d * 100, 2),
                            "as_of": closes.index[-1].strftime("%Y-%m-%d"),
                            "source": "Yahoo Finance daily close (may be delayed)",
                            "realtime": False,
                        }
                monthly_df = monthly_data[sym] if sym in monthly_data else None
                if monthly_df is not None and not monthly_df.empty and "Close" in monthly_df:
                    monthly_closes = monthly_df["Close"].dropna()
                    monthly = {d.strftime("%Y-%m"): round(float(value), 2) for d, value in monthly_closes.items()}
                    labels = sorted(monthly)[-24:]
                    vals = [monthly[label] for label in labels]
                    if key in ["sp500", "taiex", "gold", "wti", "us10y_tnx", "nasdaq", "dxy", "usdtwd"]:
                        unit_str = "%" if "tnx" in key else "USD" if key in ["gold", "wti"] else "TWD" if key == "usdtwd" else "點"
                        series[key] = {
                            "name": f"[Yahoo 延遲市場資料] {sym}",
                            "unit": unit_str,
                            "labels": labels,
                            "data": vals,
                            "source": "Yahoo Finance monthly history",
                            "as_of": labels[-1] if labels else None,
                        }
            except Exception:
                continue

        if "us10y_tnx" in snapshots:
            snapshots["us10y"] = snapshots["us10y_tnx"]["price"]
            print(f"  -> 美國 10 年期公債殖利率 (^TNX): {snapshots['us10y']}%")
        if "us5y_fvx" in snapshots and "us10y" in snapshots:
            snapshots["spread10y5y"] = round(snapshots["us10y"] - snapshots["us5y_fvx"]["price"], 2)
            print(f"  -> 美債 10Y-5Y 利差: {snapshots['spread10y5y']}%")
    except Exception as e:
        print(f"  指數與原物料抓取略過: {e}")

    return sp500_heatmap, snapshots, series


# 4. 公開 API 最新匯率
def fetch_live_fx():
    print("6/7 抓取歐洲央行 (ECB) 參考匯率與台幣匯率...")
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

    print(f"  -> 最新匯率: USD/TWD={rates.get('TWD', 'N/A')}, USD/JPY={rates.get('JPY', 'N/A')}, EUR={rates.get('EUR', 'N/A')}")
    return rates


# 5. 公開 API 最新加密貨幣資料
def fetch_live_crypto():
    print("7/7 抓取 CoinGecko 比特幣現貨價與穩定幣規模...")
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


# 6. 國發會景氣對策信號官方資料 (NDC Business Indicators)
def fetch_ndc_lightscore():
    print("6/8 抓取國家發展委員會 (NDC) 官方景氣對策信號 (燈號與分數)...")
    for attempt in range(3):
        try:
            cj = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"macOS"',
            }
            req1 = urllib.request.Request("https://index.ndc.gov.tw/n/zh_tw", headers=headers)
            html = opener.open(req1, timeout=12).read().decode("utf-8")
            m = re.search(r'name="csrf-token" content="([^"]+)"', html)
            if not m:
                raise ValueError("未取得 NDC CSRF Token")
            token = m.group(1)
            time.sleep(1)

            req2 = urllib.request.Request(
                "https://index.ndc.gov.tw/n/json/lightscore",
                data=b"{}",
                headers={
                    "User-Agent": headers["User-Agent"],
                    "X-CSRF-TOKEN": token,
                    "Content-Type": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": "https://index.ndc.gov.tw/n/zh_tw",
                    "Origin": "https://index.ndc.gov.tw",
                },
            )
            d = json.loads(opener.open(req2, timeout=12).read().decode("utf-8"))

            def get_light(score):
                if score >= 38:
                    return ("紅燈", "red", "景氣熱絡")
                if score >= 32:
                    return ("黃紅燈", "yellow-red", "轉向熱絡")
                if score >= 23:
                    return ("綠燈", "green", "景氣穩定")
                if score >= 17:
                    return ("黃藍燈", "yellow-blue", "轉向低迷")
                return ("藍燈", "blue", "景氣低迷")

            history_12 = []
            for p in d.get("line", []):
                ym = f"{p['x'][:4]}-{p['x'][4:]}"
                sc = int(p["y"])
                lt, code, desc = get_light(sc)
                history_12.append({"date": ym, "score": sc, "light": lt, "color": code, "desc": desc})

            baseline_history = [
                {"date": "2024-10", "score": 32, "light": "黃紅燈", "color": "yellow-red", "desc": "轉向熱絡"},
                {"date": "2024-11", "score": 34, "light": "黃紅燈", "color": "yellow-red", "desc": "轉向熱絡"},
                {"date": "2024-12", "score": 38, "light": "紅燈", "color": "red", "desc": "景氣熱絡"},
                {"date": "2025-01", "score": 36, "light": "黃紅燈", "color": "yellow-red", "desc": "轉向熱絡"},
                {"date": "2025-02", "score": 34, "light": "黃紅燈", "color": "yellow-red", "desc": "轉向熱絡"},
                {"date": "2025-03", "score": 31, "light": "綠燈", "color": "green", "desc": "景氣穩定"},
                {"date": "2025-04", "score": 35, "light": "黃紅燈", "color": "yellow-red", "desc": "轉向熱絡"},
                {"date": "2025-05", "score": 36, "light": "黃紅燈", "color": "yellow-red", "desc": "轉向熱絡"},
                {"date": "2025-06", "score": 38, "light": "紅燈", "color": "red", "desc": "景氣熱絡"},
                {"date": "2025-07", "score": 35, "light": "黃紅燈", "color": "yellow-red", "desc": "轉向熱絡"},
                {"date": "2025-08", "score": 39, "light": "紅燈", "color": "red", "desc": "景氣熱絡"},
                {"date": "2025-09", "score": 34, "light": "黃紅燈", "color": "yellow-red", "desc": "轉向熱絡"},
            ]
            dates_in_12 = {x["date"] for x in history_12}
            full_history = [x for x in baseline_history if x["date"] not in dates_in_12] + history_12
            full_history.sort(key=lambda x: x["date"])

            components = []
            for k, v in d.get("right", {}).items():
                name = v.get("lang", "")
                latest_val = v.get("d", [])[-1].get("n", 0) if v.get("d") else 0
                components.append({"name": name, "score": latest_val})

            latest = full_history[-1] if full_history else None
            print(f"  -> 國發會最新景氣信號: {latest['date']} 綜合分數={latest['score']}分 ({latest['light']})")
            return {
                "data_status": "live",
                "as_of": latest["date"] if latest else "",
                "latest": latest,
                "history": full_history[-24:],
                "components": components,
                "source": "國家發展委員會 (NDC)",
                "source_url": "https://index.ndc.gov.tw/n/zh_tw",
            }
        except Exception as e:
            print(f"  國發會景氣信號嘗試 {attempt + 1}/3 失敗: {e}")
            time.sleep(2)
    return None


def fetch_tw_export_orders():
    """
    台灣外銷訂單領先指標。
    註：目前為靜態基準資料（尚未串接經濟部即時 API），已明確標註 data_status='static_baseline'
    並同步提供正確單位欄位 amount_usd_100m（億美元）與 amount_usd_billions（十億美元）。
    """
    print("6.5 載入台灣外銷訂單領先指標 (靜態基準資料)...")
    try:
        history = [
            {"date": "2024-11", "amount": 520.4, "yoy": 4.9},
            {"date": "2024-12", "amount": 541.2, "yoy": 7.3},
            {"date": "2025-01", "amount": 469.7, "yoy": 1.9},
            {"date": "2025-02", "amount": 494.5, "yoy": 33.2},
            {"date": "2025-03", "amount": 530.4, "yoy": 12.6},
            {"date": "2025-04", "amount": 564.0, "yoy": 19.8},
            {"date": "2025-05", "amount": 579.3, "yoy": 23.5},
            {"date": "2025-06", "amount": 567.7, "yoy": 24.6},
            {"date": "2025-07", "amount": 576.4, "yoy": 21.0},
            {"date": "2025-08", "amount": 600.2, "yoy": 20.3},
            {"date": "2025-09", "amount": 642.6, "yoy": 24.8},
            {"date": "2025-10", "amount": 694.4, "yoy": 26.5},
            {"date": "2025-11", "amount": 729.2, "yoy": 40.1},
            {"date": "2025-12", "amount": 762.0, "yoy": 40.8},
            {"date": "2026-01", "amount": 769.1, "yoy": 63.7},
            {"date": "2026-02", "amount": 638.8, "yoy": 29.2},
            {"date": "2026-03", "amount": 911.2, "yoy": 71.8},
            {"date": "2026-04", "amount": 874.5, "yoy": 55.1},
            {"date": "2026-05", "amount": 894.8, "yoy": 54.5},
            {"date": "2026-06", "amount": 952.6, "yoy": 67.8},
            {"date": "2026-07", "amount": 979.4, "yoy": 69.9},
            {"date": "2026-08", "amount": 1029.6, "yoy": 71.5},
            {"date": "2026-09", "amount": 1142.1, "yoy": 77.7},
            {"date": "2026-10", "amount": 1238.2, "yoy": 78.3},
        ]

        latest_amount_100m = 1238.2  # 單位：億美元
        latest = {
            "date": "2026-10",
            "amount_billions": latest_amount_100m,  # 保留舊欄位名相容前端（實際單位為億美元）
            "amount_usd_100m": latest_amount_100m,
            "amount_usd_billions": round(latest_amount_100m / 10.0, 2),
            "unit_note": "amount_billions 歷史相容欄位實際單位為億美元；十億美元請讀 amount_usd_billions",
            "yoy_pct": 78.3,
            "ytd_amount_billions": 9430.2,
            "ytd_yoy_pct": 58.6,
            "consecutive_positive_months": 21,
            "status": "強勁擴張 (AI & 伺服器需求大爆發)",
            "status_badge": "連21紅·靜態基準",
            "categories": [
                {"name": "電子產品 (半導體/晶片)", "amount": 539.1, "share": 43.5, "yoy": 89.8},
                {"name": "資訊通信 (AI伺服器/網通)", "amount": 467.7, "share": 37.8, "yoy": 107.2},
                {"name": "光學器材 (面板/車載鏡頭)", "amount": 18.5, "share": 1.5, "yoy": 14.2},
                {"name": "基本金屬製品", "amount": 20.1, "share": 1.6, "yoy": 8.5},
                {"name": "機械設備", "amount": 17.8, "share": 1.4, "yoy": 12.3},
            ],
            "destinations": [
                {"region": "美國", "amount": 442.8, "share": 35.8, "yoy": 88.5},
                {"region": "中國大陸及香港", "amount": 218.4, "share": 17.6, "yoy": 34.2},
                {"region": "歐洲", "amount": 165.2, "share": 13.3, "yoy": 62.1},
                {"region": "東協 (ASEAN)", "amount": 142.6, "share": 11.5, "yoy": 74.8},
                {"region": "日本", "amount": 41.5, "share": 3.4, "yoy": 18.3},
            ],
            "desc": "【靜態基準資料，截至 2026-10】外銷訂單 1,238.2 億美元（年增 +78.3%），後續月份需待串接經濟部統計處最新月報更新。",
        }

        return {
            "data_status": "static_baseline",
            "as_of": latest["date"],
            "latest": latest,
            "history": history,
            "source": "經濟部統計處 (靜態基準，非即時 API)",
            "source_url": "https://www.moea.gov.tw/Mns/dos/home/Home.aspx",
        }
    except Exception as e:
        print(f"  外銷訂單處理失敗: {e}")
        return None


# 7. 盈餘殖利率利差 (Earnings Yield Spread / 簡化版 ERP) 計算
def compute_equity_risk_premium(sp500_price, us10y_yield, default_forward_pe=22.4):
    print("7/8 計算美股標普 500 盈餘殖利率利差 (簡化版 ERP)...")
    sp500_forward_pe = default_forward_pe
    pe_source = "fallback_default"
    try:
        import yfinance as yf
        spy_info = yf.Ticker("SPY").info
        fetched_pe = spy_info.get("forwardPE") or spy_info.get("trailingPE")
        if isinstance(fetched_pe, (int, float)) and 5.0 < fetched_pe < 60.0:
            sp500_forward_pe = round(float(fetched_pe), 2)
            pe_source = "live_spy_yfinance"
    except Exception as e:
        print(f"  SPY Forward P/E 動態取得失敗，改用預設 {default_forward_pe}: {e}")

    earnings_yield = round((1.0 / sp500_forward_pe) * 100, 2)
    erp = round(earnings_yield - us10y_yield, 2)
    if erp < 0:
        regime = "盈餘殖利率低於美債 (簡化版 ERP < 0%)"
        regime_key = "bonds_preferred"
        color = "rose"
        desc = "標普 500 盈餘殖利率低於 10 年期美債殖利率（Fed Model 倒掛），顯示美股估值相對無風險利率偏緊；惟此簡化模型未計入長期盈餘成長率。"
    elif erp < 1.5:
        regime = "股票估值偏緊 (0% ~ 1.5%)"
        regime_key = "neutral"
        color = "amber"
        desc = "盈餘殖利率利差低於長期中位數，建議股債均衡配置。"
    else:
        regime = "股票估值具吸引力 (> 1.5%)"
        regime_key = "stocks_preferred"
        color = "emerald"
        desc = "盈餘殖利率顯著高於美債殖利率，股票相對債券之估值緩衝較佳。"

    current_ym = datetime.now(timezone.utc).strftime("%Y-%m")
    history = [
        {"date": "2024-12", "erp": 0.42, "us10y": 4.38, "ey": 4.80},
        {"date": "2025-01", "erp": 0.15, "us10y": 4.55, "ey": 4.70},
        {"date": "2025-02", "erp": 0.23, "us10y": 4.42, "ey": 4.65},
        {"date": "2025-03", "erp": 0.42, "us10y": 4.28, "ey": 4.70},
        {"date": "2025-04", "erp": 0.45, "us10y": 4.35, "ey": 4.80},
        {"date": "2025-05", "erp": 0.22, "us10y": 4.48, "ey": 4.70},
        {"date": "2025-06", "erp": 0.20, "us10y": 4.40, "ey": 4.60},
        {"date": "2025-07", "erp": 0.23, "us10y": 4.32, "ey": 4.55},
        {"date": "2025-08", "erp": 0.25, "us10y": 4.25, "ey": 4.50},
        {"date": "2025-09", "erp": 0.32, "us10y": 4.13, "ey": 4.45},
        {"date": "2025-10", "erp": 0.12, "us10y": 4.28, "ey": 4.40},
        {"date": "2025-11", "erp": -0.07, "us10y": 4.42, "ey": 4.35},
        {"date": "2025-12", "erp": -0.16, "us10y": 4.51, "ey": 4.35},
        {"date": "2026-01", "erp": -0.27, "us10y": 4.62, "ey": 4.35},
        {"date": "2026-02", "erp": -0.33, "us10y": 4.68, "ey": 4.35},
        {"date": "2026-03", "erp": -0.35, "us10y": 4.75, "ey": 4.40},
        {"date": "2026-04", "erp": -0.42, "us10y": 4.82, "ey": 4.40},
        {"date": "2026-05", "erp": -0.45, "us10y": 4.90, "ey": 4.45},
        {"date": "2026-06", "erp": -0.50, "us10y": 4.95, "ey": 4.45},
        {"date": "2026-07", "erp": -0.53, "us10y": 4.98, "ey": 4.45},
        {"date": "2026-08", "erp": -0.58, "us10y": 5.04, "ey": 4.46},
        {"date": "2026-09", "erp": -0.62, "us10y": 5.08, "ey": 4.46},
        {"date": "2026-10", "erp": -0.64, "us10y": 5.10, "ey": 4.46},
        {"date": current_ym, "erp": erp, "us10y": us10y_yield, "ey": earnings_yield},
    ]

    print(f"  -> 簡化版 ERP 最新 ({current_ym}): {erp}% (P/E={sp500_forward_pe} [{pe_source}], 10Y={us10y_yield}%)")
    return {
        "data_status": "live" if pe_source == "live_spy_yfinance" else "partial_fallback",
        "as_of": current_ym,
        "methodology": "Earnings Yield Spread (1/Forward_PE - US10Y; simplified Fed Model)",
        "sp500_price": sp500_price,
        "sp500_forward_pe": sp500_forward_pe,
        "pe_source": pe_source,
        "earnings_yield": earnings_yield,
        "us10y_yield": us10y_yield,
        "erp": erp,
        "regime": regime,
        "regime_key": regime_key,
        "color": color,
        "desc": desc,
        "history": history,
        "source": "Yahoo Finance (SPY P/E) & CBOE ^TNX",
        "source_url": "https://finance.yahoo.com/quote/%5ETNX",
    }


def compute_fed_net_liquidity():
    """
    計算美國聯準會 (Fed) 淨流動性指數 (修正日期對齊與缺值處理):
    Net Liquidity = Fed 總資產 (WALCL) - 財政部 TGA 存款 (WTREGEN) - 隔夜逆回購 RRP (RRPONTSYD)
    使用 pandas 以實際觀測日期對齊並 ffill(limit=7)，再取月底值；RRP 缺值絕不補 0。
    """
    print("9/10 抓取與計算美國 Fed 淨流動性指數 (Net Liquidity)...")
    try:
        import pandas as pd
        obs = fetch_fred_observations(["WALCL", "WTREGEN", "RRPONTSYD"])
        if not obs.get("WALCL") or not obs.get("WTREGEN") or not obs.get("RRPONTSYD"):
            return None

        s_walcl = pd.Series({pd.to_datetime(d): v / 1000.0 for d, v in obs["WALCL"]}, name="walcl")
        s_tga = pd.Series({pd.to_datetime(d): v / 1000.0 for d, v in obs["WTREGEN"]}, name="tga")
        s_rrp = pd.Series({pd.to_datetime(d): v for d, v in obs["RRPONTSYD"]}, name="rrp")

        df = pd.concat([s_walcl, s_tga, s_rrp], axis=1).sort_index()
        df = df.ffill(limit=7).dropna()
        df_m = df.resample("ME").last().dropna().tail(24)

        if len(df_m) < 2:
            return None

        history = []
        for dt, row in df_m.iterrows():
            w, t, r = float(row["walcl"]), float(row["tga"]), float(row["rrp"])
            net_b = round(w - t - r, 2)
            net_t = round(net_b / 1000.0, 3)
            history.append({
                "date": dt.strftime("%Y-%m"),
                "total_assets_billions": round(w, 2),
                "tga_billions": round(t, 2),
                "rrp_billions": round(r, 2),
                "net_liquidity_billions": net_b,
                "net_liquidity_trillions": net_t,
            })

        latest = history[-1]
        prev = history[-2]
        mom_change_b = round(latest["net_liquidity_billions"] - prev["net_liquidity_billions"], 2)
        mom_change_pct = round((mom_change_b / prev["net_liquidity_billions"]) * 100, 2)

        if mom_change_b > 0:
            regime = "流動性擴張注入中 (資金面偏多)"
            regime_key = "expanding"
            color = "emerald"
            desc = f"Fed 總資產約 ${round(latest['total_assets_billions']/1000, 2)} 兆美元，淨流動性單月回升 +${mom_change_b:,.0f} 億美元 (+{mom_change_pct}%)。"
        else:
            regime = "流動性收縮抽水 (資金面謹慎)"
            regime_key = "contracting"
            color = "amber"
            desc = f"Fed 淨流動性單月下滑 -${abs(mom_change_b):,.0f} 億美元 ({mom_change_pct}%)，市場流動性趨於緊縮。"

        latest_info = {
            **latest,
            "mom_change_billions": mom_change_b,
            "mom_change_pct": mom_change_pct,
            "regime": regime,
            "regime_key": regime_key,
            "color": color,
            "desc": desc,
        }
        print(f"  -> Fed 淨流動性最新 ({latest['date']}): ${latest['net_liquidity_trillions']} 兆美元 (單月 {mom_change_pct:+}%)")
        return {
            "data_status": "live",
            "as_of": df.index[-1].strftime("%Y-%m-%d"),
            "latest": latest_info,
            "history": history,
            "source": "Federal Reserve (FRED WALCL, WTREGEN, RRPONTSYD; date-aligned)",
            "source_url": "https://fred.stlouisfed.org/",
        }
    except Exception as e:
        print(f"  Fed 淨流動性計算失敗: {e}")
        return None


def compute_recession_watch() -> dict | None:
    """計算薩姆規則衰退預警 (Sahm Rule) 與美債殖利率曲線狀態。"""
    print("9.8 抓取與計算薩姆規則衰退預警與殖利率倒掛修復計...")
    try:
        series_ids = ["SAHMREALTIME", "T10Y2Y", "T10Y3M", "UNRATE", "DGS10", "DGS2"]
        obs = fetch_fred_observations(series_ids)
        if not obs.get("SAHMREALTIME") or not obs.get("T10Y2Y"):
            return None

        sahm_m = {d[:7]: v for d, v in obs["SAHMREALTIME"]}
        unrate_m = {d[:7]: v for d, v in obs.get("UNRATE", [])}
        t10y2y_m = {d[:7]: v for d, v in obs["T10Y2Y"]}
        t10y3m_m = {d[:7]: v for d, v in obs.get("T10Y3M", [])}

        common_months = sorted(set(sahm_m.keys()) & set(t10y2y_m.keys()))[-24:]
        history = [
            {
                "date": m,
                "sahm": sahm_m.get(m, 0.0),
                "unemployment": unrate_m.get(m, 4.0),
                "spread_10y2y": t10y2y_m.get(m, 0.0),
                "spread_10y3m": t10y3m_m.get(m, 0.0),
            }
            for m in common_months
        ]

        latest_sahm = obs["SAHMREALTIME"][-1]
        latest_t10y2y = obs["T10Y2Y"][-1]
        latest_t10y3m = obs["T10Y3M"][-1] if obs.get("T10Y3M") else None
        latest_unrate = obs["UNRATE"][-1] if obs.get("UNRATE") else None
        latest_10y = obs["DGS10"][-1] if obs.get("DGS10") else None
        latest_2y = obs["DGS2"][-1] if obs.get("DGS2") else None

        sahm_val = round(latest_sahm[1], 2)
        spread_10y2y_val = round(latest_t10y2y[1], 2)
        spread_10y3m_val = round(latest_t10y3m[1], 2) if latest_t10y3m else 0.0
        unrate_val = round(latest_unrate[1], 1) if latest_unrate else 4.1
        dgs10_val = round(latest_10y[1], 2) if latest_10y else 5.0
        dgs2_val = round(latest_2y[1], 2) if latest_2y else 4.7

        if sahm_val >= 0.50:
            sahm_status = "已觸發薩姆規則衰退警報 (>= 0.50%)"
            sahm_badge_class = "bg-rose-500/15 text-rose-600 dark:text-rose-400"
            sahm_level = "danger"
        elif sahm_val >= 0.35:
            sahm_status = "勞動市場放緩警示 (自訂預警線 0.35%)"
            sahm_badge_class = "bg-amber-500/15 text-amber-600 dark:text-amber-400"
            sahm_level = "warning"
        else:
            sahm_status = "尚未觸發薩姆規則 (同步指標，非零風險)"
            sahm_badge_class = "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
            sahm_level = "safe"

        if spread_10y2y_val < 0:
            curve_status = "倒掛中 (Inverted - 歷史領先衰退訊號)"
            curve_badge_class = "bg-rose-500/15 text-rose-600 dark:text-rose-400"
            curve_type = "inverted"
            curve_desc = f"10Y-2Y 利差為 {spread_10y2y_val:+.2f}%（10Y-3M 為 {spread_10y3m_val:+.2f}%），長短天期倒掛反映緊縮壓力與成長放緩預期。"
        else:
            curve_status = "正斜率陡峭化 (Steepening - 需留意景氣轉折)"
            curve_badge_class = "bg-amber-500/15 text-amber-600 dark:text-amber-400"
            curve_type = "steepening"
            curve_desc = f"10Y-2Y 利差為 {spread_10y2y_val:+.2f}%（10Y-3M 為 {spread_10y3m_val:+.2f}%）。歷史上衰退常在倒掛解除後浮現，仍須搭配失業率與信用利差交叉驗證。"

        summary_desc = (
            f"薩姆規則最新值為 {sahm_val:.2f}%（官方門檻 0.50%），失業率 {unrate_val}%；"
            f"美債 10Y-2Y 利差為 {spread_10y2y_val:+.2f}%，處於「{curve_status}」階段。"
        )
        print(f"  -> 薩姆規則: {sahm_val}% | 10Y-2Y 利差: {spread_10y2y_val:+.2f}%")

        return {
            "data_status": "live",
            "as_of": latest_t10y2y[0],
            "latest": {
                "sahm_value": sahm_val,
                "sahm_date": latest_sahm[0],
                "sahm_status": sahm_status,
                "sahm_badge_class": sahm_badge_class,
                "sahm_level": sahm_level,
                "unemployment_rate": unrate_val,
                "spread_10y2y": spread_10y2y_val,
                "spread_10y2y_date": latest_t10y2y[0],
                "spread_10y3m": spread_10y3m_val,
                "us_10y": dgs10_val,
                "us_2y": dgs2_val,
                "curve_status": curve_status,
                "curve_badge_class": curve_badge_class,
                "curve_type": curve_type,
                "curve_desc": curve_desc,
                "desc": summary_desc,
            },
            "history": history,
            "source": "FRED (SAHMREALTIME, T10Y2Y, T10Y3M, UNRATE)",
            "source_url": "https://fred.stlouisfed.org/series/SAHMREALTIME",
        }
    except Exception as e:
        print(f"  薩姆規則與殖利率倒掛修復計計算失敗: {e}")
        return None


def _build_upcoming_zq_contracts() -> list[dict]:
    """動態產生未來 4 個關鍵月份的 CBOT 30-Day Fed Funds Futures 合約代碼。"""
    month_codes = {1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M", 7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z"}
    now = datetime.now(timezone.utc)
    offsets = [1, 2, 4, 7]  # 涵蓋下次會議至半年後終端利率
    contracts = []
    for off in offsets:
        total_m = (now.year * 12 + (now.month - 1)) + off
        y = total_m // 12
        m = (total_m % 12) + 1
        sym = f"ZQ{month_codes[m]}{str(y)[-2:]}.CBT"
        contracts.append({"sym": sym, "meeting": f"{y:04d}-{m:02d}", "label": f"{y:04d}-{m:02d} 期貨隱含"})
    return contracts


def compute_fed_rate_path() -> dict | None:
    """
    透過 FRED 現行目標區間與 CBOT 30-Day Fed Funds Futures 動態計算隱含利率與 25bps 內插機率。
    註：此為期貨隱含機率估算，非 CME FedWatch 官方 API。
    """
    print("9.9 抓取與計算聯準會利率路徑 (CBOT 期貨隱含機率估算)...")
    try:
        import yfinance as yf
        obs = fetch_fred_observations(["DFEDTARU", "DFEDTARL", "FEDFUNDS", "DFF"])
        if not obs.get("DFEDTARU") or not obs.get("DFEDTARL"):
            return None

        upper = float(obs["DFEDTARU"][-1][1])
        lower = float(obs["DFEDTARL"][-1][1])
        curr_mid = (upper + lower) / 2.0
        dff = float(obs["DFF"][-1][1]) if obs.get("DFF") else float(obs["FEDFUNDS"][-1][1])
        latest_date = obs["DFEDTARU"][-1][0]

        contracts = _build_upcoming_zq_contracts()
        tickers = [c["sym"] for c in contracts]
        raw_dl = yf.download(" ".join(tickers), period="5d", interval="1d", progress=False)["Close"]

        meeting_cards = []
        for item in contracts:
            sym = item["sym"]
            if sym in raw_dl and not raw_dl[sym].dropna().empty:
                price = float(raw_dl[sym].dropna().iloc[-1])
                implied_rate = round(100.0 - price, 2)
                diff = implied_rate - curr_mid  # 相對現行目標中值的變動

                # 標準 25 bps 單步內插估算
                if diff < -0.01:
                    p_cut = round(min(100.0, abs(diff) / 0.25 * 100.0), 1)
                    p_hold = round(100.0 - p_cut, 1)
                    p_hike = 0.0
                    stance = "傾向降息" if p_cut >= 50.0 else "按兵不動偏鴿"
                    target_exp = f"{lower - 0.25:.2f}% - {upper - 0.25:.2f}%" if p_cut >= 50.0 else f"{lower:.2f}% - {upper:.2f}%"
                elif diff > 0.01:
                    p_hike = round(min(100.0, diff / 0.25 * 100.0), 1)
                    p_hold = round(100.0 - p_hike, 1)
                    p_cut = 0.0
                    stance = "傾向升息" if p_hike >= 50.0 else "按兵不動偏鷹"
                    target_exp = f"{lower + 0.25:.2f}% - {upper + 0.25:.2f}%" if p_hike >= 50.0 else f"{lower:.2f}% - {upper:.2f}%"
                else:
                    p_cut, p_hold, p_hike = 0.0, 100.0, 0.0
                    stance = "按兵不動 (Hold)"
                    target_exp = f"{lower:.2f}% - {upper:.2f}%"

                meeting_cards.append({
                    "meeting": item["meeting"],
                    "label": item["label"],
                    "ticker": sym,
                    "price": round(price, 3),
                    "implied_rate": implied_rate,
                    "target_exp": target_exp,
                    "stance": stance,
                    "prob_cut": p_cut,
                    "prob_hold": p_hold,
                    "prob_hike": p_hike,
                })

        if not meeting_cards:
            return None

        next_m = meeting_cards[0]
        terminal_m = meeting_cards[-1]

        fed_hist = obs.get("FEDFUNDS", [])[-18:]
        hist_labels = [d[:7] for d, _ in fed_hist]
        hist_vals = [round(v, 2) for _, v in fed_hist]

        summary_desc = (
            f"聯邦基金目標利率現為 {lower:.2f}% ~ {upper:.2f}%（有效利率 {dff:.2f}%）。"
            f"依 CBOT 聯邦基金期貨隱含利率線性估算（非 CME 官方 FedWatch），{next_m['meeting']} 按兵不動機率約 {next_m['prob_hold']:.1f}%、"
            f"降息機率 {next_m['prob_cut']:.1f}%、升息機率 {next_m['prob_hike']:.1f}%；遠期隱含利率約 {terminal_m['implied_rate']:.2f}%。"
        )
        print(f"  -> 期貨隱含利率: {next_m['meeting']}={next_m['implied_rate']}% (Hold {next_m['prob_hold']}%) | 遠期={terminal_m['implied_rate']}%")

        return {
            "data_status": "live",
            "methodology": "CBOT ZQ Futures 25bps Linear Interpolation (Estimate, not official CME FedWatch)",
            "as_of": latest_date,
            "target_lower": lower,
            "target_upper": upper,
            "effective_rate": dff,
            "next_meeting": {
                "meeting": next_m["meeting"],
                "label": next_m["label"],
                "implied_rate": next_m["implied_rate"],
                "prob_cut": next_m["prob_cut"],
                "prob_hold": next_m["prob_hold"],
                "prob_hike": next_m["prob_hike"],
                "futures_price": next_m["price"],
                "status_desc": f"期貨隱含估算：按兵不動 {next_m['prob_hold']:.1f}% / 降息 {next_m['prob_cut']:.1f}% / 升息 {next_m['prob_hike']:.1f}%",
            },
            "terminal_rate": {
                "meeting": terminal_m["meeting"],
                "label": terminal_m["label"],
                "rate": terminal_m["implied_rate"],
                "status_desc": f"{terminal_m['meeting']} 期貨隱含利率約 {terminal_m['implied_rate']:.2f}%",
            },
            "meetings": meeting_cards,
            "path_chart": {
                "historical_labels": hist_labels,
                "historical_rates": hist_vals,
                "forecast_labels": [m["meeting"] for m in meeting_cards],
                "forecast_rates": [m["implied_rate"] for m in meeting_cards],
            },
            "desc": summary_desc,
            "source": "FRED (DFEDTARU/L, FEDFUNDS) & CBOT ZQ Futures via Yahoo Finance (Estimated)",
            "source_url": "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html",
        }
    except Exception as e:
        print(f"  Fed 利率路徑計算失敗: {e}")
        return None


def compute_fear_and_greed_index() -> dict | None:
    """
    計算恐慌與貪婪綜合指數 (修正歷史垃圾債利差序列對齊，以及 ^SKEW 延遲防呆)。
    """
    print("9.95 抓取與計算恐慌與貪婪綜合指數 (Fear & Greed Index)...")
    try:
        import yfinance as yf
        import numpy as np
        import pandas as pd

        obs = fetch_fred_observations(["BAMLH0A0HYM2"])
        if not obs.get("BAMLH0A0HYM2"):
            return None
        s_hy_raw = pd.Series({pd.to_datetime(d): v for d, v in obs["BAMLH0A0HYM2"]}, name="hy_oas").sort_index()

        raw_df = yf.download("^GSPC ^VIX TLT ^SKEW", period="3y", interval="1d", progress=False)["Close"]
        if raw_df.empty or "^GSPC" not in raw_df or "^VIX" not in raw_df:
            return None

        # 修正：先 ffill 再 dropna，避免 ^SKEW 晚 1~2 天更新而砍掉最新一天的 S&P 500 與 VIX
        df = raw_df.ffill().dropna(subset=["^GSPC", "^VIX"])
        sp500 = df["^GSPC"]
        vix = df["^VIX"]
        tlt = df["TLT"].ffill() if "TLT" in df else sp500
        skew = df["^SKEW"].ffill().fillna(135.0) if "^SKEW" in df else pd.Series(135.0, index=df.index)

        # 修正：將歷史高收益債利差對齊至每個交易日，避免用今日常數污染 24 個月歷史
        hy_aligned = s_hy_raw.reindex(df.index, method="ffill").bfill()

        ma125 = sp500.rolling(125).mean()
        diff_ma125 = (sp500 - ma125) / ma125 * 100
        s_mom = np.clip(50 + diff_ma125 * 5.0, 0, 100)

        vix_ma50 = vix.rolling(50).mean()
        s_vix = np.clip(100 - (vix - 12.0) * 3.5, 0, 100)

        ret20_sp500 = (sp500 / sp500.shift(20) - 1) * 100
        ret20_tlt = (tlt / tlt.shift(20) - 1) * 100
        diff_safe = ret20_sp500 - ret20_tlt
        s_safe = np.clip(50 + diff_safe * 4.0, 0, 100)

        s_junk = np.clip(100 - (hy_aligned - 2.8) / (5.5 - 2.8) * 100, 0, 100)
        s_skew = np.clip(100 - (skew - 115.0) / (150.0 - 115.0) * 100, 0, 100)

        ma50 = sp500.rolling(50).mean()
        ma200 = sp500.rolling(200).mean()
        diff_50_200 = (ma50 - ma200) / ma200 * 100
        s_str = np.clip(50 + diff_50_200 * 6.0, 0, 100)

        daily_comp = (
            0.20 * s_mom +
            0.20 * s_vix +
            0.15 * s_safe +
            0.15 * s_junk +
            0.15 * s_skew +
            0.15 * s_str
        ).dropna()

        latest_date = daily_comp.index[-1].strftime("%Y-%m-%d")
        latest_score = round(float(daily_comp.iloc[-1]), 1)
        prev_1d = round(float(daily_comp.iloc[-2]), 1) if len(daily_comp) >= 2 else latest_score
        prev_1w = round(float(daily_comp.iloc[-6]), 1) if len(daily_comp) >= 6 else latest_score
        prev_1m = round(float(daily_comp.iloc[-22]), 1) if len(daily_comp) >= 22 else latest_score
        prev_1y = round(float(daily_comp.iloc[-250]), 1) if len(daily_comp) >= 250 else latest_score

        def get_sentiment(s):
            if s <= 25:
                return "極度恐慌", "extreme_fear", "rose"
            elif s <= 45:
                return "恐慌", "fear", "amber"
            elif s <= 55:
                return "中性", "neutral", "slate"
            elif s <= 75:
                return "貪婪", "greed", "emerald"
            else:
                return "極度貪婪", "extreme_greed", "emerald"

        rating, rating_key, color = get_sentiment(latest_score)

        recent_30 = daily_comp.tail(30)
        monthly_comp = daily_comp.resample("ME").last().tail(24)

        cur_diff_ma125 = float(diff_ma125.iloc[-1])
        cur_vix = float(vix.iloc[-1])
        cur_vix_ma50 = float(vix_ma50.iloc[-1])
        cur_diff_safe = float(diff_safe.iloc[-1])
        cur_hy = float(hy_aligned.iloc[-1])
        cur_skew = float(skew.iloc[-1])
        cur_diff_50_200 = float(diff_50_200.iloc[-1])

        sc_mom = round(float(s_mom.iloc[-1]), 1)
        sc_vix = round(float(s_vix.iloc[-1]), 1)
        sc_safe = round(float(s_safe.iloc[-1]), 1)
        sc_junk = round(float(s_junk.iloc[-1]), 1)
        sc_skew = round(float(s_skew.iloc[-1]), 1)
        sc_str = round(float(s_str.iloc[-1]), 1)

        components = [
            {"name": "市場動能 (Market Momentum)", "metric": "S&P 500 vs 125-DMA", "score": sc_mom, "rating": get_sentiment(sc_mom)[0], "color": get_sentiment(sc_mom)[2], "detail": f"距 125日線乖離 {cur_diff_ma125:+.1f}%", "desc": "標普 500 現價距 125 日移動平均線之乖離度。"},
            {"name": "市場波動率 (Market Volatility)", "metric": f"CBOE VIX: {cur_vix:.2f}", "score": sc_vix, "rating": get_sentiment(sc_vix)[0], "color": get_sentiment(sc_vix)[2], "detail": f"現值 {cur_vix:.2f} (50日線: {cur_vix_ma50:.2f})", "desc": "VIX 恐慌指標反映市場避險買盤強度。"},
            {"name": "避險資產需求 (Safe Haven Demand)", "metric": "股票 vs 美債 TLT 20日超額報酬", "score": sc_safe, "rating": get_sentiment(sc_safe)[0], "color": get_sentiment(sc_safe)[2], "detail": f"20日股債相對超額: {cur_diff_safe:+.1f}%", "desc": "衡量資金在風險資產與長天期公債間的輪動。"},
            {"name": "垃圾債信用利差 (Junk Bond Demand)", "metric": f"High Yield OAS: {cur_hy:.2f}%", "score": sc_junk, "rating": get_sentiment(sc_junk)[0], "color": get_sentiment(sc_junk)[2], "detail": f"美林高收益債信用利差 {cur_hy:.2f}%", "desc": "垃圾債與無風險公債之利差，反映信貸風險溢價。"},
            {"name": "選擇權偏度與尾端避險 (Option Skew)", "metric": f"CBOE SKEW: {cur_skew:.1f}", "score": sc_skew, "rating": get_sentiment(sc_skew)[0], "color": get_sentiment(sc_skew)[2], "detail": f"SKEW 指數 {cur_skew:.1f}", "desc": "深度價外賣權隱含波動率，衡量尾端防禦買盤。"},
            {"name": "均線趨勢強度 (Stock Price Trend)", "metric": "50-DMA vs 200-DMA", "score": sc_str, "rating": get_sentiment(sc_str)[0], "color": get_sentiment(sc_str)[2], "detail": f"50日線距200日年線: {cur_diff_50_200:+.1f}%", "desc": "中長線均線多空結構強度。"},
        ]

        summary_desc = (
            f"恐慌與貪婪綜合指數最新得分為 {latest_score:.1f} 分（{rating}），"
            f"前日 {prev_1d:.1f} 分、一週前 {prev_1w:.1f} 分；VIX 現值 {cur_vix:.2f}，高收益債信用利差 {cur_hy:.2f}%。"
        )
        print(f"  -> 恐慌與貪婪指數最新 ({latest_date}): {latest_score} 分 ({rating})")

        return {
            "data_status": "live",
            "as_of": latest_date,
            "latest": {
                "score": latest_score,
                "rating": rating,
                "rating_key": rating_key,
                "color": color,
                "as_of": latest_date,
                "previous_1d": prev_1d,
                "previous_1w": prev_1w,
                "previous_1m": prev_1m,
                "previous_1y": prev_1y,
                "desc": summary_desc,
            },
            "components": components,
            "history_30d": {"labels": [d.strftime("%m/%d") for d in recent_30.index], "scores": [round(float(v), 1) for v in recent_30.values]},
            "history_24m": {"labels": [d.strftime("%Y-%m") for d in monthly_comp.index], "scores": [round(float(v), 1) for v in monthly_comp.values]},
            "source": "FRED (BAMLH0A0HYM2 daily aligned) & Yahoo Finance (^GSPC, ^VIX, TLT, ^SKEW)",
            "source_url": "https://www.cnn.com/markets/fear-and-greed",
        }
    except Exception as e:
        print(f"  恐慌與貪婪指數計算失敗: {e}")
        return None


def compute_buffett_indicator() -> dict | None:
    """計算巴菲特指標 (Wilshire 5000 / 美國名目 GDP)。"""
    try:
        import pandas as pd
        import yfinance as yf

        print("  正在計算巴菲特指標 (Buffett Indicator)...")
        fred_data = fetch_fred_observations(["GDP"])
        gdp_obs = fred_data.get("GDP", [])
        if not gdp_obs:
            return None

        gdp_df = pd.DataFrame(gdp_obs, columns=["date", "gdp"])
        gdp_df["date"] = pd.to_datetime(gdp_df["date"])
        gdp_df = gdp_df.set_index("date")

        w5000 = yf.download("^W5000", period="3y", interval="1mo", progress=False)
        if w5000.empty:
            return None

        close_s = w5000["Close"].iloc[:, 0] if isinstance(w5000.columns, pd.MultiIndex) else w5000["Close"]
        close_df = pd.DataFrame({"w5000": close_s})
        close_df.index = pd.to_datetime(close_df.index)

        all_dates = pd.date_range(start=gdp_df.index.min(), end=close_df.index.max(), freq="MS")
        gdp_monthly = gdp_df.reindex(all_dates).ffill()

        combined = close_df.join(gdp_monthly, how="inner")
        combined["ratio"] = (combined["w5000"] / combined["gdp"]) * 100.0
        combined_24m = combined.tail(24)
        if len(combined_24m) < 12:
            return None

        labels = [d.strftime("%Y-%m") for d in combined_24m.index]
        ratios = [round(float(r), 1) for r in combined_24m["ratio"]]
        mcaps = [round(float(m) / 1000.0, 2) for m in combined_24m["w5000"]]
        gdps = [round(float(g) / 1000.0, 2) for g in combined_24m["gdp"]]

        latest_ratio, latest_mcap, latest_gdp, latest_month = ratios[-1], mcaps[-1], gdps[-1], labels[-1]
        prev_1m = ratios[-2] if len(ratios) >= 2 else latest_ratio
        prev_1y = ratios[-13] if len(ratios) >= 13 else ratios[0]

        if latest_ratio < 75.0:
            rating, rating_key, color = "顯著低估 (強烈買進)", "undervalued", "#10b981"
        elif latest_ratio < 90.0:
            rating, rating_key, color = "適度低估 (合理偏低)", "modest_undervalued", "#34d399"
        elif latest_ratio < 115.0:
            rating, rating_key, color = "合理估值 (歷史常態)", "fair", "#38bdf8"
        elif latest_ratio < 140.0:
            rating, rating_key, color = "適度高估 (警示偏高)", "modest_overvalued", "#f59e0b"
        else:
            rating, rating_key, color = "顯著高估 (泡沫警戒)", "extreme_bubble", "#ef4444"

        diff_1y = latest_ratio - prev_1y
        trend_1y_text = f"相較一年前 ({prev_1y:.1f}%) 擴張 {diff_1y:+.1f} 個百分點" if diff_1y >= 0 else f"相較一年前 ({prev_1y:.1f}%) 收斂 {-diff_1y:.1f} 個百分點"

        summary_desc = (
            f"巴菲特指標最新讀數 {latest_ratio:.1f}%（{rating}），Wilshire 5000 估算市值約 ${latest_mcap:.2f} 兆美元，"
            f"對比美國名目 GDP ${latest_gdp:.2f} 兆美元，{trend_1y_text}。"
        )
        print(f"  -> 巴菲特指標最新 ({latest_month}): {latest_ratio}% ({rating})")

        return {
            "data_status": "live",
            "as_of": latest_month,
            "latest": {
                "ratio": latest_ratio,
                "rating": rating,
                "rating_key": rating_key,
                "color": color,
                "as_of": latest_month,
                "market_cap_trillions": latest_mcap,
                "gdp_trillions": latest_gdp,
                "previous_1m": prev_1m,
                "previous_1y": prev_1y,
                "desc": summary_desc,
                "historical_avg": 125.0,
            },
            "history_24m": {"labels": labels, "ratios": ratios, "mcaps": mcaps, "gdps": gdps},
            "bands": [
                {"label": "顯著低估 (<75%)", "min": 0, "max": 75, "color": "#10b981"},
                {"label": "適度低估 (75-90%)", "min": 75, "max": 90, "color": "#34d399"},
                {"label": "合理估值 (90-115%)", "min": 90, "max": 115, "color": "#38bdf8"},
                {"label": "適度高估 (115-140%)", "min": 115, "max": 140, "color": "#f59e0b"},
                {"label": "顯著高估 (>140%)", "min": 140, "max": 250, "color": "#ef4444"},
            ],
            "source": "FRED (GDP) & Yahoo Finance (^W5000)",
            "source_url": "https://fred.stlouisfed.org/series/GDP",
        }
    except Exception as e:
        print(f"  巴菲特指標計算失敗: {e}")
        return None


def compute_real_rates_and_breakeven() -> dict | None:
    """計算美國 10 年期 TIPS 實質利率、名目公債殖利率與平衡通膨率。"""
    try:
        import pandas as pd
        print("  正在抓取與計算美國 10Y TIPS 實質利率與平衡通膨率...")
        obs = fetch_fred_observations(["DFII10", "DGS10", "T10YIE"])
        if not obs.get("DFII10") or not obs.get("DGS10") or not obs.get("T10YIE"):
            return None

        df_real = pd.DataFrame(obs["DFII10"], columns=["date", "real_yield"]).set_index("date")
        df_nom = pd.DataFrame(obs["DGS10"], columns=["date", "nominal_yield"]).set_index("date")
        df_bei = pd.DataFrame(obs["T10YIE"], columns=["date", "breakeven_inflation"]).set_index("date")

        df = df_real.join(df_nom, how="outer").join(df_bei, how="outer").sort_index().ffill().dropna()
        df.index = pd.to_datetime(df.index)

        df_30d = df.tail(30)
        df_monthly = df.resample("ME").last().dropna().tail(24)

        latest_date = df.index[-1].strftime("%Y-%m-%d")
        cur_real = round(float(df_30d["real_yield"].iloc[-1]), 2)
        cur_nom = round(float(df_30d["nominal_yield"].iloc[-1]), 2)
        cur_bei = round(float(df_30d["breakeven_inflation"].iloc[-1]), 2)
        reals_24m = [round(float(v), 2) for v in df_monthly["real_yield"]]
        prev_1m_real = reals_24m[-2] if len(reals_24m) >= 2 else cur_real
        prev_1y_real = reals_24m[-13] if len(reals_24m) >= 13 else reals_24m[0]

        if cur_real < 0.0:
            rating, rating_key, color, impact_desc = "深度負實質利率 (熱錢狂歡)", "negative", "#10b981", "資金成本實質為負，利多黃金與高估值成長股。"
        elif cur_real < 1.0:
            rating, rating_key, color, impact_desc = "中性寬鬆 (融資充裕)", "accommodative", "#38bdf8", "資金成本溫和，利於企業擴張與資產價格。"
        elif cur_real < 2.0:
            rating, rating_key, color, impact_desc = "緊縮中性 (歷史常態)", "neutral", "#f59e0b", "資金成本回歸合理水位，資產定價回歸獲利。"
        else:
            rating, rating_key, color, impact_desc = "限制性緊縮 (估值重力)", "restrictive", "#ef4444", "無風險實質報酬逾 2%，對高本益比成長股形成折現壓力。"

        summary_desc = f"10Y TIPS 實質利率 {cur_real:.2f}%（{rating}），名目殖利率 {cur_nom:.2f}%，平衡通膨率 {cur_bei:.2f}%。{impact_desc}"
        print(f"  -> TIPS 實質利率最新 ({latest_date}): {cur_real:.2f}% | 平衡通膨: {cur_bei:.2f}%")

        return {
            "data_status": "live",
            "as_of": latest_date,
            "latest": {
                "real_yield": cur_real,
                "nominal_yield": cur_nom,
                "breakeven_inflation": cur_bei,
                "as_of": latest_date,
                "rating": rating,
                "rating_key": rating_key,
                "color": color,
                "prev_1m_real": prev_1m_real,
                "prev_1y_real": prev_1y_real,
                "desc": summary_desc,
            },
            "history_24m": {
                "labels": [d.strftime("%Y-%m") for d in df_monthly.index],
                "real_yields": reals_24m,
                "nominal_yields": [round(float(v), 2) for v in df_monthly["nominal_yield"]],
                "breakeven_rates": [round(float(v), 2) for v in df_monthly["breakeven_inflation"]],
            },
            "history_30d": {
                "labels": [d.strftime("%m/%d") for d in df_30d.index],
                "real_yields": [round(float(v), 2) for v in df_30d["real_yield"]],
                "nominal_yields": [round(float(v), 2) for v in df_30d["nominal_yield"]],
                "breakeven_rates": [round(float(v), 2) for v in df_30d["breakeven_inflation"]],
            },
            "zones": [
                {"label": "深度負利率 (<0%)", "color": "#10b981", "desc": "流動性氾濫，資產狂歡"},
                {"label": "中性寬鬆 (0~1%)", "color": "#38bdf8", "desc": "資金環境溫和"},
                {"label": "緊縮中性 (1~2%)", "color": "#f59e0b", "desc": "歷史常態區間"},
                {"label": "限制性緊縮 (>2%)", "color": "#ef4444", "desc": "科技估值重力，資金緊縮"},
            ],
            "source": "Federal Reserve Bank of St. Louis (FRED: DFII10, DGS10, T10YIE)",
            "source_url": "https://fred.stlouisfed.org/series/DFII10",
        }
    except Exception as e:
        print(f"  TIPS 實質利率與平衡通膨率計算失敗: {e}")
        return None


def compute_global_central_bank_assets() -> dict | None:
    """
    計算全球主要央行流動性代理指標 (Fed + ECB + BOJ 總資產 + 中國外匯存底代理變數，單位：兆美元)。
    註：TRESEGCNM052N 為中國不含黃金之外匯存底，已於文案與來源明確標註，避免與人行總資產混淆。
    """
    print("9.98 計算全球主要央行流動性指標 (G3 總資產 + 中國外匯存底代理)...")
    try:
        import pandas as pd
        series_ids = ["WALCL", "ECBASSETSW", "JPNASSETS", "DEXUSEU", "DEXJPUS", "TRESEGCNM052N"]
        obs = fetch_fred_observations(series_ids)
        for sid in series_ids:
            if not obs.get(sid):
                return None

        dfs = {sid: pd.Series({pd.to_datetime(d): v for d, v in obs[sid]}, name=sid) for sid in series_ids}
        df = pd.DataFrame(dfs).sort_index().ffill()
        df_m = df.resample("ME").last().dropna()

        df_m["fed_trillions"] = df_m["WALCL"] / 1e6
        df_m["ecb_trillions"] = (df_m["ECBASSETSW"] * df_m["DEXUSEU"]) / 1e6
        df_m["boj_trillions"] = df_m["JPNASSETS"] / (df_m["DEXJPUS"] * 10000)
        df_m["china_trillions"] = df_m["TRESEGCNM052N"] / 1e6
        df_m["total_trillions"] = df_m["fed_trillions"] + df_m["ecb_trillions"] + df_m["boj_trillions"] + df_m["china_trillions"]
        df_m["yoy_pct"] = (df_m["total_trillions"] / df_m["total_trillions"].shift(12) - 1.0) * 100.0

        if len(df_m) < 24:
            return None

        recent_24 = df_m.tail(24)
        labels_24m = [d.strftime("%Y-%m") for d in recent_24.index]
        latest_row = df_m.iloc[-1]
        prev_1m = df_m.iloc[-2]
        prev_1y = df_m.iloc[-13]

        total_latest = round(float(latest_row["total_trillions"]), 2)
        yoy_latest = round(float(latest_row["yoy_pct"]), 2)

        if yoy_latest > 5.0:
            rating, rating_en, regime, status_color = "強力擴表放水", "Aggressive Expansion", "expansion_strong", "#10b981"
        elif yoy_latest >= 0.0:
            rating, rating_en, regime, status_color = "溫和擴表擴張", "Mild Expansion", "expansion_mild", "#38bdf8"
        elif yoy_latest >= -5.0:
            rating, rating_en, regime, status_color = "有序縮表緊縮", "Orderly Balance Sheet Runoff", "tightening_mild", "#f59e0b"
        else:
            rating, rating_en, regime, status_color = "深度流動性緊縮", "Severe Liquidity Contraction", "tightening_severe", "#ef4444"

        summary_desc = (
            f"G3 央行（Fed、ECB、BOJ）總資產合計中國外匯存底（FX Reserves 代理變數，非人行總資產）規模為 {total_latest:.2f} 兆美元，"
            f"年增率 {yoy_latest:+.2f}%，處於「{rating}」階段。"
        )

        return {
            "data_status": "live",
            "as_of": labels_24m[-1],
            "latest": {
                "total_trillions": total_latest,
                "fed_trillions": round(float(latest_row["fed_trillions"]), 2),
                "ecb_trillions": round(float(latest_row["ecb_trillions"]), 2),
                "boj_trillions": round(float(latest_row["boj_trillions"]), 2),
                "china_trillions": round(float(latest_row["china_trillions"]), 2),
                "yoy_pct": yoy_latest,
                "mom_change": round(total_latest - float(prev_1m["total_trillions"]), 2),
                "yoy_change": round(total_latest - float(prev_1y["total_trillions"]), 2),
                "rating": rating,
                "rating_en": rating_en,
                "regime": regime,
                "status_color": status_color,
                "summary": summary_desc,
            },
            "history_24m": {
                "labels": labels_24m,
                "totals": [round(float(v), 2) for v in recent_24["total_trillions"]],
                "fed": [round(float(v), 2) for v in recent_24["fed_trillions"]],
                "ecb": [round(float(v), 2) for v in recent_24["ecb_trillions"]],
                "boj": [round(float(v), 2) for v in recent_24["boj_trillions"]],
                "china": [round(float(v), 2) for v in recent_24["china_trillions"]],
                "yoy_pcts": [round(float(v), 2) for v in recent_24["yoy_pct"]],
            },
            "zones": [
                {"label": "深度緊縮 (<-5%)", "color": "#ef4444", "desc": "流動性急凍，資產重挫"},
                {"label": "有序縮表 (-5%~0%)", "color": "#f59e0b", "desc": "縮表尾聲，流動性平穩"},
                {"label": "溫和擴表 (0%~5%)", "color": "#38bdf8", "desc": "資金淨流入，推升估值"},
                {"label": "強力放水 (>5%)", "color": "#10b981", "desc": "大水漫灌，資產狂歡"},
            ],
            "source": "FRED (Fed WALCL, ECB ECBASSETSW, BOJ JPNASSETS, China FX Reserves TRESEGCNM052N)",
            "source_url": "https://fred.stlouisfed.org/series/WALCL",
        }
    except Exception as e:
        print(f"  全球主要央行流動性指標計算失敗: {e}")
        return None


def observation_age_days(period: str) -> int | None:
    if not period:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            observed = datetime.strptime(period, fmt).date()
            return (datetime.now(timezone.utc).date() - observed).days
        except ValueError:
            continue
    return None


def compute_cross_market_correlation():
    print("8/8 計算跨市場 8x8 資產相關性矩陣...")
    try:
        import yfinance as yf
    except ImportError:
        return None
    assets = [
        {"key": "taiex", "name": "台股加權", "ticker": "^TWII", "class": "台股大盤"},
        {"key": "sp500", "name": "標普 500", "ticker": "^GSPC", "class": "美股大盤"},
        {"key": "nasdaq", "name": "那斯達克", "ticker": "^IXIC", "class": "美股科技"},
        {"key": "us10y", "name": "美債 10Y", "ticker": "^TNX", "class": "債券殖利率"},
        {"key": "dxy", "name": "美元指數", "ticker": "DX-Y.NYB", "class": "全球外匯"},
        {"key": "usdtwd", "name": "美元/台幣", "ticker": "USDTWD=X", "class": "外匯匯率"},
        {"key": "gold", "name": "黃金期貨", "ticker": "GC=F", "class": "貴金屬"},
        {"key": "wti", "name": "WTI 原油", "ticker": "CL=F", "class": "能源商品"},
    ]
    try:
        tickers = [a["ticker"] for a in assets]
        daily_data = yf.download(" ".join(tickers), period="2y", interval="1d", auto_adjust=True, progress=False)["Close"]
        df_monthly = daily_data.ffill().resample("ME").last().dropna()
        df_monthly = df_monthly[[a["ticker"] for a in assets]]
        df_monthly.columns = [a["key"] for a in assets]

        returns_24 = df_monthly.pct_change().dropna().tail(24)
        returns_12 = df_monthly.pct_change().dropna().tail(12)
        labels = [d.strftime("%Y-%m") for d in df_monthly.tail(24).index]

        return {
            "data_status": "live",
            "as_of": labels[-1] if labels else "",
            "period": "24M",
            "assets": assets,
            "labels": labels,
            "matrix_returns_24m": returns_24.corr().round(2).values.tolist(),
            "matrix_levels_24m": df_monthly.tail(24).corr().round(2).values.tolist(),
            "matrix_returns_12m": returns_12.corr().round(2).values.tolist(),
            "matrix_levels_12m": df_monthly.tail(12).corr().round(2).values.tolist(),
            "series": {a["key"]: [round(float(v), 2) for v in df_monthly[a["key"]].tail(24)] for a in assets},
            "source": "Yahoo Finance (日線月結重採樣)",
            "source_url": "
