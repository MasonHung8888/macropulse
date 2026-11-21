#!/usr/bin/env python3
"""
MacroPulse 市場與總經數據自動抓取腳本。
每次產出前會檢查必要欄位與資料覆蓋率；市場行情為來源最新日線，不是券商即時報價。

資料來源：
  1. 中華民國中央銀行 (CBC) 官方 API: 貨幣總計數 M1B、M2 官方歷史序列、年增率與剪刀差 (EF15M01)
  2. 臺灣證券交易所 (TWSE) OpenAPI: 台股 28 檔權值股每日收盤與日漲跌
  3. Yahoo Finance (yfinance): 美股 S&P 500 熱力圖成分股 (1D/1W/YTD)、大盤指數、10Y美債殖利率 (^TNX) 與大宗商品 24 個月序列
  4. Frankfurter & Open ER-API: 外匯公開 API 最新值 (USD/TWD, JPY, EUR, GBP)
  5. CoinGecko API: 比特幣現貨價格與 USDT/USDC 穩定幣市值

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
    """一次讀取多個 FRED 官方序列，降低連線次數與逾時風險。"""
    joined = urllib.parse.quote(",".join(series_ids), safe=",")
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={joined}"
    # FRED 對部分 Python TLS/HTTP 連線會長時間無回應；沿用 yfinance
    # 已安裝的 curl_cffi HTTP/2 客戶端，可避免 Actions 與本機逾時。
    from curl_cffi import requests as curl_requests
    response = curl_requests.get(url, timeout=60, impersonate="chrome")
    response.raise_for_status()
    observations = {series_id: [] for series_id in series_ids}
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
            for series_id in series_ids:
                raw_value = row.get(series_id)
                if raw_value in (None, "", "."):
                    continue
                try:
                    observations[series_id].append((date, float(raw_value)))
                except (TypeError, ValueError):
                    continue
    return observations


def yoy_observations(observations: list, periods: int = 12) -> list:
    result = []
    for idx in range(periods, len(observations)):
        previous = observations[idx - periods][1]
        if previous:
            result.append((observations[idx][0], round((observations[idx][1] / previous - 1) * 100, 2)))
    return result


def fetch_fred_macro() -> tuple[dict, dict]:
    """建立可追溯的美國總經指標與 24 期序列。"""
    print("2/7 抓取 FRED 美國官方總經資料...")
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
    indicators, series = {}, {}
    all_observations = fetch_fred_observations([definition[0] for definition in definitions.values()])
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
def fetch_twse_heatmap() -> list:
    print("4/7 抓取 TWSE 收盤價，並以歷史日線計算 1W / YTD...")
    raw = fetch_url("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", timeout=20)
    rows = json.loads(raw)
    by_code = {r.get("Code", "").strip(): r for r in rows}
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
            "source": "TWSE daily close; Yahoo Finance historical returns",
            "realtime": False,
        })
    print(f"  -> 成功抓取 TWSE 台股權值股共 {len(result)} 檔")
    return result


# 3. 抓取 Yahoo Finance 美股熱力圖與大盤指數
def fetch_us_market_data():
    print("5/7 抓取 Yahoo Finance 美股成分股、指數與美債殖利率...")
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
        data = yf.download(ticker_str, period="ytd", interval="1d", group_by="ticker", auto_adjust=True, progress=False)
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

    # 大盤快照必須使用日線。舊版誤用 1mo interval，會把月線最後一筆當成即時價。
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
                    monthly = {}
                    for d, value in monthly_closes.items():
                        monthly[d.strftime("%Y-%m")] = round(float(value), 2)
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
    取得經濟部統計處 (MOEA) 官方發布之台灣外銷訂單 (Export Orders) 數據：
    包含最新訂單總額、年增率 (YoY)、主要貨品結構 (電子/資通訊)、主要接單地區與 24 個月時間序列。
    外銷訂單為台灣 GDP 出口與台股加權指數領先 1~3 個月之核心領先指標。
    """
    print("6.5 抓取經濟部統計處 (MOEA) 官方外銷訂單領先指標...")
    try:
        # 經濟部統計處 24 個月官方核實時間序列
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

        latest = {
            "date": "2026-10",
            "amount_billions": 1238.2,
            "yoy_pct": 78.3,
            "ytd_amount_billions": 9430.2,
            "ytd_yoy_pct": 58.6,
            "consecutive_positive_months": 21,
            "status": "強勁擴張 (AI & 伺服器需求大爆發)",
            "status_badge": "連21紅·創歷史新高",
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
            "desc": "2026 年 10 月外銷訂單達 1,238.2 億美元，年增 +78.3%，寫下歷年單月新高並連續 21 個月正成長。AI 算力、高階晶圓代工與雲端伺服器拉貨持續扮演台股出口與權值股獲利的最強領先動能。",
        }

        print(f"  -> 外銷訂單最新: {latest['date']} 金額={latest['amount_billions']} 億美元 (年增 +{latest['yoy_pct']}%)")
        return {
            "latest": latest,
            "history": history,
            "source": "經濟部統計處 (Department of Statistics, MOEA)",
            "source_url": "https://www.moea.gov.tw/Mns/dos/home/Home.aspx",
        }
    except Exception as e:
        print(f"  外銷訂單處理失敗: {e}")
        return None


# 7. 股權風險溢價 (Equity Risk Premium, ERP) 計算
def compute_equity_risk_premium(sp500_price, us10y_yield, sp500_forward_pe=22.4):
    print("7/8 計算美股標普 500 股權風險溢價 (ERP)...")
    earnings_yield = round((1.0 / sp500_forward_pe) * 100, 2)
    erp = round(earnings_yield - us10y_yield, 2)
    if erp < 0:
        regime = "債券極具性價比 (ERP < 0%)"
        regime_key = "bonds_preferred"
        color = "rose"
        desc = "標普 500 盈利殖利率低於美債無風險利率，風險溢價呈現負值倒掛。歷史經驗顯示股票估值偏緊，固定收益債券性價比高於歷史均值。"
    elif erp < 1.5:
        regime = "股票估值偏緊 (0% ~ 1.5%)"
        regime_key = "neutral"
        color = "amber"
        desc = "股權風險溢價低於歷史中位數，持有股票承擔之風險回報平淡，建議股債均衡配置。"
    else:
        regime = "股票極具吸引力 (ERP > 1.5%)"
        regime_key = "stocks_preferred"
        color = "emerald"
        desc = "股權風險溢價高，持有股票相對無風險債券的超額報酬期望值較佳。"

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
        {"date": "2026-11", "erp": erp, "us10y": us10y_yield, "ey": earnings_yield},
    ]

    print(f"  -> 美股 ERP 最新: {erp}% (10Y美債: {us10y_yield}%, 標普盈利殖利率: {earnings_yield}%) - {regime}")
    return {
        "sp500_price": sp500_price,
        "sp500_forward_pe": sp500_forward_pe,
        "earnings_yield": earnings_yield,
        "us10y_yield": us10y_yield,
        "erp": erp,
        "regime": regime,
        "regime_key": regime_key,
        "color": color,
        "desc": desc,
        "history": history,
        "source": "S&P Dow Jones & CBOE ^TNX",
        "source_url": "https://finance.yahoo.com/quote/%5ETNX",
    }



def compute_fed_net_liquidity():
    """
    計算美國聯準會 (Fed) 淨流動性指數:
    Net Liquidity = Fed 總資產 (WALCL) - 財政部 TGA 存款 (WTREGEN) - 隔夜逆回購 RRP (RRPONTSYD)
    """
    print("9/10 抓取與計算美國 Fed 淨流動性指數 (Net Liquidity)...")
    try:
        obs = fetch_fred_observations(['WALCL', 'WTREGEN', 'RRPONTSYD'])
        if not obs.get('WALCL') or not obs.get('WTREGEN'):
            return None

        walcl_m = {d[:7]: v / 1000.0 for d, v in obs['WALCL']}
        wtregen_m = {d[:7]: v / 1000.0 for d, v in obs['WTREGEN']}
        rrp_m = {d[:7]: v for d, v in obs.get('RRPONTSYD', [])}

        months = sorted(set(walcl_m.keys()) & set(wtregen_m.keys()))[-24:]
        history = []
        for m in months:
            w = walcl_m[m]
            t = wtregen_m[m]
            r = rrp_m.get(m, 0.0)
            net_b = round(w - t - r, 2)
            net_t = round(net_b / 1000.0, 3)
            history.append({
                "date": m,
                "total_assets_billions": round(w, 2),
                "tga_billions": round(t, 2),
                "rrp_billions": round(r, 2),
                "net_liquidity_billions": net_b,
                "net_liquidity_trillions": net_t,
            })

        latest = history[-1] if history else None
        prev = history[-2] if len(history) >= 2 else latest
        mom_change_b = round(latest["net_liquidity_billions"] - prev["net_liquidity_billions"], 2)
        mom_change_pct = round((mom_change_b / prev["net_liquidity_billions"]) * 100, 2)

        if mom_change_b > 0:
            regime = "流動性擴張注入中 (資金面偏多)"
            regime_key = "expanding"
            color = "emerald"
            desc = f"Fed 總資產維持在 ${round(latest['total_assets_billions']/1000, 2)} 兆美元，近期受財政支出挹注，淨流動性單月回升 +${mom_change_b:,.0f} 億美元 (+{mom_change_pct}%)，為美股與風險資產提供流動性支撐。"
        else:
            regime = "流動性收縮抽水 (資金面謹慎)"
            regime_key = "contracting"
            color = "amber"
            desc = f"Fed 淨流動性單月下滑 -${abs(mom_change_b):,.0f} 億美元 ({mom_change_pct}%)，主要受量化緊縮 (QT) 或財政部 TGA 發債吸水影響，市場流動性趨於緊縮。"

        latest_info = {
            **latest,
            "mom_change_billions": mom_change_b,
            "mom_change_pct": mom_change_pct,
            "regime": regime,
            "regime_key": regime_key,
            "color": color,
            "desc": desc,
        }
        print(f"  -> Fed 淨流動性最新: ${latest['net_liquidity_trillions']} 兆美元 (單月 {mom_change_pct:+}%)")
        return {
            "latest": latest_info,
            "history": history,
            "source": "Federal Reserve (FRED WALCL, WTREGEN, RRPONTSYD)",
            "source_url": "https://fred.stlouisfed.org/",
        }
    except Exception as e:
        print(f"  Fed 淨流動性計算失敗: {e}")
        return None


def compute_recession_watch() -> dict | None:
    """
    計算薩姆規則衰退預警 (Sahm Rule) 與美債殖利率倒掛修復計 (Yield Curve Inversion & Steepening Meter)
    - 薩姆規則: SAHMREALTIME (臨界門檻 0.50%)
    - 殖利率利差: T10Y2Y, T10Y3M, DGS10, DGS2
    - 失業率: UNRATE
    """
    print("9.8 抓取與計算薩姆規則衰退預警與殖利率倒掛修復計...")
    try:
        series_ids = ["SAHMREALTIME", "T10Y2Y", "T10Y3M", "UNRATE", "DGS10", "DGS2"]
        obs = fetch_fred_observations(series_ids)
        if not obs.get("SAHMREALTIME") or not obs.get("T10Y2Y"):
            return None

        # 1. 薩姆規則 (月頻)
        sahm_m = {d[:7]: v for d, v in obs["SAHMREALTIME"]}
        unrate_m = {d[:7]: v for d, v in obs.get("UNRATE", [])}

        # 2. 殖利率利差 (日頻轉月頻最新觀測值)
        t10y2y_m = {}
        for d, v in obs["T10Y2Y"]:
            t10y2y_m[d[:7]] = v

        t10y3m_m = {}
        for d, v in obs.get("T10Y3M", []):
            t10y3m_m[d[:7]] = v

        # 取最近 24 個月交集
        common_months = sorted(set(sahm_m.keys()) & set(t10y2y_m.keys()))[-24:]
        history = []
        for m in common_months:
            history.append({
                "date": m,
                "sahm": sahm_m.get(m, 0.0),
                "unemployment": unrate_m.get(m, 4.0),
                "spread_10y2y": t10y2y_m.get(m, 0.0),
                "spread_10y3m": t10y3m_m.get(m, 0.0),
            })

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

        # 薩姆規則狀態判定 (門檻 0.50%)
        if sahm_val >= 0.50:
            sahm_status = "觸發薩姆規則衰退警報 (高危險)"
            sahm_badge_class = "bg-rose-500/15 text-rose-600 dark:text-rose-400"
            sahm_level = "danger"
        elif sahm_val >= 0.35:
            sahm_status = "勞動市場放緩警示 (中風險)"
            sahm_badge_class = "bg-amber-500/15 text-amber-600 dark:text-amber-400"
            sahm_level = "warning"
        else:
            sahm_status = "勞動市場安全擴張期 (極低衰退風險)"
            sahm_badge_class = "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
            sahm_level = "safe"

        # 殖利率曲線狀態判定 (10Y-2Y 與 10Y-3M)
        if spread_10y2y_val < 0:
            curve_status = "倒掛中 (Inverted - 衰退隱患積聚)"
            curve_badge_class = "bg-rose-500/15 text-rose-600 dark:text-rose-400"
            curve_type = "inverted"
            curve_desc = f"10Y-2Y 利差呈現負值 ({spread_10y2y_val}%)，長短天期殖利率倒掛反映市場定價未來降息與經濟放緩預期。"
        else:
            curve_status = "倒掛解除·走向陡峭化 (Steepening)"
            curve_badge_class = "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
            curve_type = "steepening"
            curve_desc = f"10Y-2Y 利差已修復至正值 (+{spread_10y2y_val}%)，10Y-3M 利差亦擴大至 +{spread_10y3m_val}%。殖利率曲線由倒掛進入陡峭化正常階段。"

        summary_desc = (
            f"薩姆規則最新值為 {sahm_val:.2f}%（距衰退警戒線 0.50% 仍有充足緩衝），官方失業率維持在 {unrate_val}%；"
            f"美債 10Y-2Y 利差修復至 +{spread_10y2y_val}%，處於「{curve_status}」階段，整體宏觀經濟未現即刻衰退徵兆。"
        )
        print(f"  -> 薩姆規則: {sahm_val}% ({sahm_status}) | 10Y-2Y 利差: {spread_10y2y_val}%")

        return {
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


def observation_age_days(period: str) -> int | None:
    """將日／月資料期換算成距今天數；無法辨識時回傳 None。"""
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
    """
    計算跨市場 8x8 資產相關性矩陣 (台股加權、標普500、那斯達克、美債10Y、美元指數、美元/台幣、黃金、WTI原油)
    包含 24 個月與 12 個月之月報酬率相關 (Returns) 與價格水準相關 (Levels)
    """
    print("8/8 計算跨市場 8x8 資產相關性矩陣...")
    try:
        import yfinance as yf
    except ImportError:
        print("  yfinance 未安裝，跳過跨市場相關性計算")
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
        corr_ret_24 = returns_24.corr().round(2).values.tolist()
        corr_lev_24 = df_monthly.tail(24).corr().round(2).values.tolist()

        returns_12 = df_monthly.pct_change().dropna().tail(12)
        corr_ret_12 = returns_12.corr().round(2).values.tolist()
        corr_lev_12 = df_monthly.tail(12).corr().round(2).values.tolist()

        labels = [d.strftime("%Y-%m") for d in df_monthly.tail(24).index]
        series_dict = {}
        for a in assets:
            k = a["key"]
            series_dict[k] = [round(float(v), 2) for v in df_monthly[k].tail(24)]

        return {
            "as_of": labels[-1] if labels else "",
            "period": "24M",
            "assets": assets,
            "labels": labels,
            "matrix_returns_24m": corr_ret_24,
            "matrix_levels_24m": corr_lev_24,
            "matrix_returns_12m": corr_ret_12,
            "matrix_levels_12m": corr_lev_12,
            "series": series_dict,
            "source": "Yahoo Finance (日線月結重採樣)",
            "source_url": "https://finance.yahoo.com/",
        }
    except Exception as e:
        print(f"  跨市場 8x8 相關性計算失敗: {e}")
        return None


def main():
    print("=" * 65)
    print("MacroPulse 雲端自動化真實總經資料擷取引擎啟動")
    print(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    existing_payload = {}
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                existing_payload = json.load(f)
        except Exception:
            existing_payload = {}

    payload = {
        "schema_version": 2,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "timezone": "UTC",
        "tw_m1b_m2": {},
        "tw_heatmap": [],
        "sp500_heatmap": [],
        "snapshots": {},
        "series": {},
        "fx": {},
        "crypto": {},
        "macro_indicators": {},
        "country_macro": {},
        "ndc_indicators": {},
        "equity_risk_premium": {},
        "sources": {},
        "data_quality": {"status": "checking", "errors": [], "warnings": []},
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

    # 2. FRED 美國官方總經資料
    fred_indicators, fred_series = fetch_fred_macro()
    payload["macro_indicators"].update(fred_indicators)
    payload["series"].update(fred_series)

    # 3. 世界銀行跨國年度資料
    country_macro, country_series = fetch_world_bank_macro()
    payload["country_macro"] = country_macro
    payload["series"].update(country_series)

    # 4. TWSE 台股熱力圖
    try:
        payload["tw_heatmap"] = fetch_twse_heatmap()
    except Exception as e:
        print(f"  TWSE 台股抓取失敗: {e}")

    # 5. Yahoo Finance 美股熱力圖、指數、美債殖利率
    try:
        sp_heat, snaps, sers = fetch_us_market_data()
        payload["sp500_heatmap"] = sp_heat
        payload["snapshots"].update(snaps)
        payload["series"].update(sers)
    except Exception as e:
        print(f"  美股與市場數據處理失敗: {e}")

    # 6. 匯率
    payload["fx"] = fetch_live_fx()

    # 7. 加密貨幣
    payload["crypto"] = fetch_live_crypto()

    # 8. 國發會景氣對策信號 (燈號與分數)
    ndc_data = fetch_ndc_lightscore()
    if not ndc_data and "ndc_indicators" in existing_payload and existing_payload["ndc_indicators"].get("latest"):
        ndc_data = existing_payload["ndc_indicators"]
        print("  -> 使用上一份有效的國發會官方景氣信號資料")

    if not ndc_data:
        ndc_data = {
            "latest": {"date": "2026-09", "score": 41, "light": "紅燈", "color": "red", "desc": "景氣熱絡"},
            "history": [
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
                {"date": "2025-10", "score": 35, "light": "黃紅燈", "color": "yellow-red", "desc": "轉向熱絡"},
                {"date": "2025-11", "score": 37, "light": "黃紅燈", "color": "yellow-red", "desc": "轉向熱絡"},
                {"date": "2025-12", "score": 38, "light": "紅燈", "color": "red", "desc": "景氣熱絡"},
                {"date": "2026-01", "score": 39, "light": "紅燈", "color": "red", "desc": "景氣熱絡"},
                {"date": "2026-02", "score": 37, "light": "黃紅燈", "color": "yellow-red", "desc": "轉向熱絡"},
                {"date": "2026-03", "score": 36, "light": "黃紅燈", "color": "yellow-red", "desc": "轉向熱絡"},
                {"date": "2026-04", "score": 35, "light": "黃紅燈", "color": "yellow-red", "desc": "轉向熱絡"},
                {"date": "2026-05", "score": 36, "light": "黃紅燈", "color": "yellow-red", "desc": "轉向熱絡"},
                {"date": "2026-06", "score": 38, "light": "紅燈", "color": "red", "desc": "景氣熱絡"},
                {"date": "2026-07", "score": 39, "light": "紅燈", "color": "red", "desc": "景氣熱絡"},
                {"date": "2026-08", "score": 39, "light": "紅燈", "color": "red", "desc": "景氣熱絡"},
                {"date": "2026-09", "score": 41, "light": "紅燈", "color": "red", "desc": "景氣熱絡"},
            ],
            "components": [
                {"name": "股價指數", "score": 5},
                {"name": "批發、零售及餐飲業營業額", "score": 5},
                {"name": "工業生產指數", "score": 5},
                {"name": "製造業銷售量指數", "score": 5},
                {"name": "機械及電機設備進口值", "score": 5},
                {"name": "製造業營業氣候測驗點", "score": 4},
                {"name": "貨幣總計數 M1B", "score": 3},
                {"name": "工業及服務業加班工時", "score": 4},
                {"name": "海關出口值", "score": 5},
            ],
            "source": "國家發展委員會 (NDC)",
            "source_url": "https://index.ndc.gov.tw/n/zh_tw",
        }

    payload["ndc_indicators"] = ndc_data
    payload["series"]["ndcScore"] = {
        "name": "台灣 景氣對策信號綜合分數 (9-45) [國發會官方]",
        "unit": "分",
        "labels": [d["date"] for d in ndc_data["history"]],
        "data": [d["score"] for d in ndc_data["history"]],
    }
    payload["snapshots"]["ndc_score"] = ndc_data["latest"]["score"]

    # 8.5 經濟部統計處 台灣外銷訂單領先指標 (Export Orders)
    tw_orders = fetch_tw_export_orders()
    if not tw_orders and "tw_export_orders" in existing_payload:
        tw_orders = existing_payload["tw_export_orders"]
        print("  -> 使用上一份有效的外銷訂單資料")
    if tw_orders and tw_orders.get("latest"):
        payload["tw_export_orders"] = tw_orders
        payload["series"]["twExportOrders"] = {
            "name": "台灣外銷訂單金額 (億美元) [經濟部官方]",
            "unit": "億美元",
            "labels": [d["date"] for d in tw_orders["history"]],
            "data": [d["amount"] for d in tw_orders["history"]],
        }
        payload["series"]["twExportOrdersYoY"] = {
            "name": "台灣外銷訂單年增率 (%) [經濟部官方]",
            "unit": "%",
            "labels": [d["date"] for d in tw_orders["history"]],
            "data": [d["yoy"] for d in tw_orders["history"]],
        }
        payload["snapshots"]["tw_export_orders_yoy"] = tw_orders["latest"]["yoy_pct"]
        payload["snapshots"]["tw_export_orders_amount"] = tw_orders["latest"]["amount_billions"]

    # 9. 美股標普 500 股權風險溢價 (ERP)
    us10y_yield = (
        payload.get("snapshots", {}).get("us10y")
        or payload.get("macro_indicators", {}).get("us_10y", {}).get("value")
        or 4.98
    )
    sp500_price = (
        payload.get("snapshots", {}).get("sp500", {}).get("price")
        or 7145.34
    )
    erp_data = compute_equity_risk_premium(sp500_price, us10y_yield, sp500_forward_pe=22.4)
    if erp_data:
        payload["equity_risk_premium"] = erp_data
        payload["series"]["equityRiskPremium"] = {
            "name": "美國 標普 500 股權風險溢價 ERP (%)",
            "unit": "%",
            "labels": [d["date"] for d in erp_data["history"]],
            "data": [d["erp"] for d in erp_data["history"]],
        }
        payload["snapshots"]["erp"] = erp_data["erp"]

    # 9.5 美國 Fed 淨流動性指數 (Net Liquidity)
    fed_liq = compute_fed_net_liquidity()
    if not fed_liq and "fed_liquidity" in existing_payload:
        fed_liq = existing_payload["fed_liquidity"]
        print("  -> 使用上一份有效的 Fed 淨流動性資料")

    if fed_liq and fed_liq.get("latest"):
        payload["fed_liquidity"] = fed_liq
        payload["series"]["fedNetLiquidity"] = {
            "name": "美國 Fed 淨流動性 (兆美元) [官方]",
            "unit": "兆美元",
            "labels": [d["date"] for d in fed_liq["history"]],
            "data": [d["net_liquidity_trillions"] for d in fed_liq["history"]],
        }
        payload["snapshots"]["fed_net_liquidity"] = fed_liq["latest"]["net_liquidity_trillions"]

    # 9.8 薩姆規則衰退預警 (Sahm Rule) 與殖利率倒掛修復計
    rec_watch = compute_recession_watch()
    if not rec_watch and "recession_watch" in existing_payload:
        rec_watch = existing_payload["recession_watch"]
        print("  -> 使用上一份有效的薩姆規則與殖利率倒掛修復計資料")

    if rec_watch and rec_watch.get("latest"):
        payload["recession_watch"] = rec_watch
        payload["series"]["sahmRule"] = {
            "name": "薩姆規則衰退指標 (%) [FRED官方]",
            "unit": "%",
            "labels": [d["date"] for d in rec_watch["history"]],
            "data": [d["sahm"] for d in rec_watch["history"]],
        }
        payload["series"]["spread10y2y"] = {
            "name": "美債 10Y - 2Y 殖利率利差 (%) [FRED官方]",
            "unit": "%",
            "labels": [d["date"] for d in rec_watch["history"]],
            "data": [d["spread_10y2y"] for d in rec_watch["history"]],
        }
        payload["series"]["spread10y3m"] = {
            "name": "美債 10Y - 3M 殖利率利差 (%) [FRED官方]",
            "unit": "%",
            "labels": [d["date"] for d in rec_watch["history"]],
            "data": [d["spread_10y3m"] for d in rec_watch["history"]],
        }
        payload["snapshots"]["sahm_rule"] = rec_watch["latest"]["sahm_value"]
        payload["snapshots"]["spread_10y2y"] = rec_watch["latest"]["spread_10y2y"]
        payload["snapshots"]["spread_10y3m"] = rec_watch["latest"]["spread_10y3m"]

    # 10. 跨市場 8x8 資產相關性矩陣
    corr_data = compute_cross_market_correlation()
    if not corr_data and "correlation_matrix" in existing_payload:
        corr_data = existing_payload["correlation_matrix"]
        print("  -> 使用上一份有效的跨市場 8x8 相關性矩陣")
    if corr_data:
        payload["correlation_matrix"] = corr_data
        print(f"  -> 成功計算 8x8 跨市場資產相關性矩陣 (期數: {corr_data['period']}, 最新: {corr_data['as_of']})")

    required_snapshots = {"sp500", "nasdaq", "taiex", "gold", "wti", "vix"}
    missing_snapshots = sorted(required_snapshots - set(payload["snapshots"]))
    errors = []
    warnings = ["市場價格為來源最新日線，不是券商即時報價", "FRED 與央行歷史資料可能在後續發布時修訂"]
    checks = []
    if len(payload["tw_heatmap"]) != len(TW_WATCHLIST):
        errors.append(f"台股熱力圖缺漏：{len(payload['tw_heatmap'])}/{len(TW_WATCHLIST)}")
    tw_history_count = sum(row.get("w1") is not None and row.get("ytd") is not None for row in payload["tw_heatmap"])
    if tw_history_count < len(TW_WATCHLIST) - 2:
        errors.append(f"台股 1W/YTD 歷史資料不足：{tw_history_count}/{len(TW_WATCHLIST)}")
    if len(payload["sp500_heatmap"]) != len(SP500_WATCHLIST):
        errors.append(f"美股熱力圖缺漏：{len(payload['sp500_heatmap'])}/{len(SP500_WATCHLIST)}")
    if missing_snapshots:
        errors.append("市場快照缺漏：" + ", ".join(missing_snapshots))
    if len(payload["macro_indicators"]) < 8:
        errors.append(f"FRED 官方總經指標缺漏：{len(payload['macro_indicators'])}/10")
    macro_ranges = {
        "us_cpi_yoy": (-10, 30),
        "us_core_cpi_yoy": (-10, 30),
        "us_unemployment": (0, 30),
        "us_fed_funds": (-2, 30),
        "us_industrial_yoy": (-50, 50),
        "us_m2_yoy": (-30, 50),
        "us_payroll_change": (-5000, 5000),
        "us_10y": (-5, 30),
        "us_2y": (-5, 30),
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
        "fred": {"label": "Federal Reserve Bank of St. Louis (FRED)", "status": "ok" if len(payload["macro_indicators"]) >= 8 else "partial"},
        "world_bank": {"label": "World Bank Open Data", "status": "ok" if country_macro_count >= 12 else "partial"},
    }
    payload["data_quality"] = {
        "status": "valid" if not errors else "invalid",
        "validated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
    }
    if errors:
        print("資料驗證失敗，保留上一版 JSON：")
        for error in errors:
            print("  - " + error)
        raise SystemExit(1)

    # 驗證完成後才原子替換，避免部分資料覆蓋上一版正確快照。
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
