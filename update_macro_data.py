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
import io
import json
import os
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
                    if key in ["sp500", "taiex", "gold", "wti", "us10y_tnx"]:
                        series[key] = {
                            "name": f"[Yahoo 延遲市場資料] {sym}",
                            "unit": "%" if "tnx" in key else "USD" if key in ["gold", "wti"] else "點",
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


def main():
    print("=" * 65)
    print("MacroPulse 雲端自動化真實總經資料擷取引擎啟動")
    print(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

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
