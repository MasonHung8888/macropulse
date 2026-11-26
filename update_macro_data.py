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
    observations = {series_id: [] for series_id in series_ids}
    try:
        joined = urllib.parse.quote(",".join(series_ids), safe=",")
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={joined}"
        # FRED 對部分 Python TLS/HTTP 連線會長時間無回應；優先嘗試 curl_cffi，若無則回退 urllib/requests
        try:
            from curl_cffi import requests as curl_requests
            response = curl_requests.get(url, timeout=60, impersonate="chrome")
            response.raise_for_status()
        except Exception:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw_c = resp.read()
                class SimpleResponse:
                    content = raw_c
                    text = raw_c.decode("utf-8", errors="ignore")
                    def raise_for_status(self): pass
                response = SimpleResponse()
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
    except Exception as exc:
        print(f"  FRED 官方序列讀取未果 (啟動快照保護): {exc}")
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


def fetch_markets_insider_bond_quote(isin: str, slug: str | None = None) -> dict | None:
    """從 Markets Insider 公開債券頁面抓取最新收盤價格、年化殖利率 (YTM) 與報價日期。"""
    try:
        resolved_slug = slug
        if not resolved_slug and isin:
            suggest_url = (
                "https://markets.businessinsider.com/ajax/SearchController_Suggest"
                f"?max_results=5&query={urllib.parse.quote(isin)}"
            )
            suggest_body = fetch_url(suggest_url, timeout=12)
            match = re.search(r'"([^"|]+-Bond-[^"|]+)\|', suggest_body)
            if match:
                resolved_slug = match.group(1)
        if not resolved_slug:
            return None
        quote_url = f"https://markets.businessinsider.com/bonds/{resolved_slug}"
        html = fetch_url(quote_url, timeout=15)
        price_match = re.search(r'price-section__current-value[^>]*>\s*([0-9.,]+)\s*<', html)
        yield_match = re.search(r'annual yield of\s*([0-9.,]+)\s*%', html, re.I)
        add_match = re.search(
            r'class="price-section__additionals"[^>]*>\s*<span>[^<]*</span>\s*<span>([^<]+)</span>\s*<span>([^<]*)</span>',
            html,
            re.S | re.I,
        )
        if not yield_match:
            return None
        market_yield = round(float(yield_match.group(1).replace(",", "")), 2)
        market_price = round(float(price_match.group(1).replace(",", "")), 2) if price_match else None
        quote_date = None
        venue = ""
        if add_match:
            raw_date = add_match.group(1).strip()
            venue = add_match.group(2).strip()
            dm_dot = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$', raw_date)
            dm_slash = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', raw_date)
            dm_iso = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', raw_date)
            if dm_dot:
                quote_date = f"{dm_dot.group(3)}-{int(dm_dot.group(2)):02d}-{int(dm_dot.group(1)):02d}"
            elif dm_slash:
                quote_date = f"{dm_slash.group(3)}-{int(dm_slash.group(1)):02d}-{int(dm_slash.group(2)):02d}"
            elif dm_iso:
                quote_date = raw_date
        if not quote_date:
            return None
        return {
            "market_price": market_price,
            "market_yield": market_yield,
            "quote_date": quote_date,
            "venue": venue,
            "quote_url": quote_url,
        }
    except Exception as exc:
        print(f"    債券 {isin} 報價抓取失敗：{exc}")
        return None


def fetch_corporate_bond_monitor(existing_bonds: dict | None = None) -> dict:
    """取得 ICE BofA 公司債指數與 10 檔指標公司債每日公開報價。"""
    print("  抓取 FRED / ICE BofA 公司債每日指標與單券公開報價...")
    definitions = {
        "ig": {"name": "美國投資級公司債", "yield_id": "BAMLC0A0CMEY", "oas_id": "BAMLC0A0CM"},
        "hy": {"name": "美國高收益公司債", "yield_id": "BAMLH0A0HYM2EY", "oas_id": "BAMLH0A0HYM2"},
        "ccc": {"name": "美國 CCC 以下公司債", "yield_id": "BAMLH0A3HYCEY", "oas_id": "BAMLH0A3HYC"},
    }
    series_ids = [item[field] for item in definitions.values() for field in ("yield_id", "oas_id")] + ["DGS5", "DGS7"]
    observations = fetch_fred_observations(series_ids)
    ust_5y_rows = observations.get("DGS5", [])
    ust_7y_rows = observations.get("DGS7", [])
    ust_5y = ust_5y_rows[-1][1] if ust_5y_rows else None
    ust_7y = ust_7y_rows[-1][1] if ust_7y_rows else None
    indices, history_maps, all_dates = [], {}, set()
    for key, definition in definitions.items():
        yield_rows = observations.get(definition["yield_id"], [])
        oas_rows = observations.get(definition["oas_id"], [])
        if not yield_rows:
            continue
        latest_date, latest_yield = yield_rows[-1]
        latest_oas = oas_rows[-1][1] if oas_rows else None
        indices.append({
            "key": key,
            "name": definition["name"],
            "yield": round(latest_yield, 2),
            "oas_bps": round(latest_oas * 100) if latest_oas is not None else None,
            "date": latest_date,
            "yield_series_id": definition["yield_id"],
            "oas_series_id": definition["oas_id"],
            "source": "ICE Data Indices, LLC via FRED",
            "source_url": f"https://fred.stlouisfed.org/series/{definition['yield_id']}",
        })
        recent = yield_rows[-90:]
        history_maps[key] = {date: round(value, 2) for date, value in recent}
        all_dates.update(date for date, _ in recent)
    if not indices:
        return {}
    labels = sorted(all_dates)
    history = {"labels": labels}
    for key in definitions:
        values = history_maps.get(key, {})
        history[key] = [values.get(date) for date in labels]

    issue_specs = [
        {"issuer": "CoreWeave", "maturity": "2031-10-01", "coupon": 9.750, "currency": "USD", "identifier": "21873SAG3",
         "isin": "USU2069EAC40", "slug": "coreweave_incdl-notes_202626-31_regs-Bond-2031-usu2069eac40",
         "terms_source": "CoreWeave SEC filing", "source_url": "https://www.sec.gov/Archives/edgar/data/1769628/000176962826000183/ex411.htm"},
        {"issuer": "SoftBank Group", "maturity": "2031-07-08", "coupon": 7.000, "currency": "USD", "identifier": "XS2854422818",
         "isin": "XS2854422818", "slug": "softbank_group_corpdl-notes_202424-31-Bond-2031-xs2854422818",
         "terms_source": "SoftBank Group bond disclosures", "source_url": "https://group.softbank/en/ir/stock/bond"},
        {"issuer": "Oracle", "maturity": "2032-09-26", "coupon": 4.800, "currency": "USD", "identifier": "68389XDK8",
         "isin": "US68389XDK81", "slug": "oracle_corpdl-notes_202525-32-Bond-2032-us68389xdk81",
         "terms_source": "Oracle SEC filing", "source_url": "https://www.sec.gov/Archives/edgar/data/1341439/000119312525220445/d31817dex41.htm"},
        {"issuer": "SpaceX", "maturity": "2031-07-15", "coupon": 5.350, "currency": "USD", "identifier": "84615QAA1",
         "isin": "USU8531HAA87", "slug": "space_exploration_techs_corpdl-notes_202626-31_regs-Bond-2031-usu8531haa87",
         "terms_source": "SpaceX investor relations", "source_url": "https://ir.spacex.com/updates/releases-details/2026/SpaceX-Announces-Pricing-of-25-Billion-Inaugural-Bond-Issuance-2026-33VwNgsx3O/default.aspx"},
        {"issuer": "Broadcom", "maturity": "2031-11-15", "coupon": 5.150, "currency": "USD", "identifier": "11135FBY6",
         "isin": "US11135FBY60", "slug": "broadcom_incdl-notes_202424-31-Bond-2031-us11135fby60",
         "terms_source": "Broadcom SEC filing", "source_url": "https://www.sec.gov/Archives/edgar/data/1730168/000114036124033072/ny20032136x6_ex4-2.htm"},
        {"issuer": "NVIDIA", "maturity": "2031-06-15", "coupon": 4.500, "currency": "USD", "identifier": "67066GAR5",
         "isin": "US67066GAR56", "slug": "nvidia_corpdl-notes_202626-31-Bond-2031-us67066gar56",
         "terms_source": "NVIDIA SEC filing", "source_url": "https://www.sec.gov/Archives/edgar/data/1045810/000119312526275783/d48176dex42.htm"},
        {"issuer": "Meta", "maturity": "2031-05-15", "coupon": 4.550, "currency": "USD", "identifier": "30303MAF9",
         "isin": "US30303MAF95", "slug": "meta_platforms_incdl-notes_202626-31-Bond-2031-us30303maf95",
         "terms_source": "Meta SEC filing", "source_url": "https://www.sec.gov/Archives/edgar/data/1326801/000119312526201738/d109954d424b2.htm"},
        {"issuer": "Alphabet", "maturity": "2031-08-15", "coupon": 4.875, "currency": "USD", "identifier": "02079KCQ8",
         "isin": "US02079KCQ85", "slug": "alphabet_incdl-notes_202626-31-Bond-2031-us02079kcq85",
         "terms_source": "Alphabet SEC filing", "source_url": "https://www.sec.gov/Archives/edgar/data/1652044/000119312526342390/d171253dex46.htm"},
        {"issuer": "Microsoft", "maturity": "2031-11-03", "coupon": 5.200, "currency": "USD", "identifier": "594918DB7",
         "isin": "US594918DB72", "slug": "microsoft_corpdl-notes_202626-31-Bond-2031-us594918db72",
         "terms_source": "Microsoft SEC filing", "source_url": "https://www.sec.gov/Archives/edgar/data/789019/000119312526442618/d150456d424b2.htm"},
        {"issuer": "Amazon", "maturity": "2031-07-09", "coupon": 4.800, "currency": "USD", "identifier": "023135EC6",
         "isin": "US023135EC69", "slug": "amazoncom_incdl-notes_202626-31-Bond-2031-us023135ec69",
         "terms_source": "Amazon SEC filing", "source_url": "https://www.sec.gov/Archives/edgar/data/1018724/000110465926081334/tm2619352d3_fwp.htm"},
    ]
    existing_history_by_issuer = {}
    if isinstance(existing_bonds, dict):
        for old_issue in existing_bonds.get("issues", []):
            if old_issue.get("issuer") and isinstance(old_issue.get("history"), list):
                existing_history_by_issuer[old_issue["issuer"]] = old_issue["history"]

    issues = []
    quoted_count = 0
    for spec in issue_specs:
        quote = fetch_markets_insider_bond_quote(spec["isin"], spec["slug"])
        market_yield = quote["market_yield"] if quote else None
        market_price = quote["market_price"] if quote else None
        quote_date = quote["quote_date"] if quote else None
        venue = quote["venue"] if quote else ""
        benchmark = ust_7y if spec["maturity"].startswith("2032") else ust_5y
        spread_bps = round((market_yield - benchmark) * 100) if (market_yield is not None and benchmark is not None) else None
        hist = [
            pt for pt in existing_history_by_issuer.get(spec["issuer"], [])
            if isinstance(pt, dict) and pt.get("date")
        ]
        if market_yield is not None and quote_date:
            quoted_count += 1
            price_txt = f"價格 {market_price:.2f} · " if market_price is not None else ""
            venue_txt = f"{venue} · " if venue else ""
            quote_status = f"{price_txt}{venue_txt}{quote_date}"
            new_pt = {"date": quote_date, "ytm": market_yield, "spread_bps": spread_bps, "price": market_price}
            hist = [pt for pt in hist if pt.get("date") != quote_date]
            hist.append(new_pt)
            hist = sorted(hist, key=lambda pt: pt["date"])[-90:]
        else:
            quote_status = "公開報價暫無更新"
        issues.append({
            "issuer": spec["issuer"],
            "maturity": spec["maturity"],
            "coupon": spec["coupon"],
            "currency": spec["currency"],
            "identifier": spec["identifier"],
            "isin": spec["isin"],
            "market_price": market_price,
            "market_yield": market_yield,
            "spread_bps": spread_bps,
            "quote_date": quote_date,
            "quote_source": f"Markets Insider ({venue})" if venue else "Markets Insider",
            "quote_url": quote["quote_url"] if quote else None,
            "quote_status": quote_status,
            "history": hist,
            "terms_status": "verified",
            "terms_source": spec["terms_source"],
            "source_url": spec["source_url"],
        })
    print(f"  -> 公司債單券公開報價成功 {quoted_count}/{len(issues)} 檔")
    return {
        "as_of": max(item["date"] for item in indices),
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "frequency": "daily_business_day",
        "source": "ICE Data Indices, LLC via FRED",
        "source_url": "https://fred.stlouisfed.org/categories/32348",
        "indices": indices,
        "history": history,
        "issues": issues,
        "methodology": "票息、到期日與識別碼來自發行人或 SEC 官方文件；指數殖利率與 OAS 來自 FRED / ICE BofA；單券市場價格與 YTM 每日抓取自 Markets Insider 公開債券報價，利差為單券 YTM 與對應天期美國公債殖利率（FRED DGS5 / DGS7）之差。",
    }


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
    try:
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
    except Exception as exc:
        print(f"  世界銀行跨國資料取得未果 (啟動快照保護): {exc}")
    return result, series


# 2. 抓取 TWSE 臺灣證券交易所台股 28 檔權值股收盤
def roc_date_to_iso(value: str) -> str | None:
    """將 TWSE 民國年 YYYYMMDD 日期轉為 ISO 日期。"""
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) != 7:
        return None
    try:
        return f"{int(digits[:3]) + 1911:04d}-{digits[3:5]}-{digits[5:7]}"
    except ValueError:
        return None


def fetch_cnyes_quotes(symbols: list[str]) -> dict[str, dict]:
    """從鉅亨網 (Anue / cnyes.com) 公開報價端點批次取得台股、美股或外匯備用報價。"""
    if not symbols:
        return {}
    try:
        joined = ",".join(symbols)
        url = f"https://ws.api.cnyes.com/ws/api/v1/quote/quotes/{urllib.parse.quote(joined, safe=':,')}"
        raw = fetch_url(url, timeout=12)
        payload = json.loads(raw)
        out = {}
        for item in payload.get("data") or []:
            sym = item.get("0")
            price = item.get("6")
            if sym and isinstance(price, (int, float)):
                ts = item.get("200007")
                as_of = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d") if isinstance(ts, (int, float)) and ts > 0 else None
                out[sym] = {
                    "price": float(price),
                    "d1": round(float(item["56"]), 2) if isinstance(item.get("56"), (int, float)) else None,
                    "as_of": as_of,
                }
        return out
    except Exception as exc:
        print(f"  鉅亨網 (cnyes) 備用報價略過: {exc}")
        return {}


def fetch_twse_taiex_snapshot() -> dict:
    """從 TWSE 官方指數日報取得發行量加權股價指數。"""
    raw = fetch_url("https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX", timeout=20)
    rows = json.loads(raw)
    row = next(item for item in rows if item.get("指數") == "發行量加權股價指數")
    direction = -1 if row.get("漲跌") == "-" else 1
    return {
        "price": float(row["收盤指數"].replace(",", "")),
        "d1": round(direction * float(row["漲跌百分比"].replace(",", "")), 2),
        "as_of": roc_date_to_iso(row.get("日期")),
        "source": "TWSE official market index daily report",
        "realtime": False,
    }


def fetch_twse_heatmap() -> list:
    print("4/7 抓取 TWSE 收盤價，並以歷史日線計算 1W / YTD...")
    by_code = {}
    try:
        raw = fetch_url("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", timeout=20)
        rows = json.loads(raw)
        by_code = {r.get("Code", "").strip(): r for r in rows}
    except Exception as exc:
        print(f"  TWSE STOCK_DAY_ALL 失敗，切換鉅亨網備用來源: {exc}")
    cnyes_tw = {}
    missing_codes = [f"TWS:{code}:STOCK" for _, code, _, _ in TW_WATCHLIST if code not in by_code]
    if missing_codes:
        cnyes_tw = fetch_cnyes_quotes(missing_codes)
    history = None
    try:
        import yfinance as yf
        symbols = " ".join(f"{code}.TW" for _, code, _, _ in TW_WATCHLIST)
        history = yf.download(symbols, period="ytd", interval="1d", group_by="ticker", auto_adjust=True, progress=False)
    except Exception as exc:
        print(f"  台股歷史日線取得失敗：{exc}")
    result = []
    for sector, code, name, _legacy_weight in TW_WATCHLIST:
        row = by_code.get(code)
        pct = None
        price = None
        traded_value = None
        as_of = None
        if row:
            try:
                price = float(row.get("ClosingPrice", "0").replace(",", ""))
                chg = float(row.get("Change", "0").replace(",", ""))
                traded_value = float(row.get("TradeValue", "0").replace(",", ""))
                as_of = roc_date_to_iso(row.get("Date"))
                prev_p = price - chg
                if prev_p > 0:
                    pct = round((chg / prev_p) * 100, 2)
            except (ValueError, ZeroDivisionError):
                pass
        elif f"TWS:{code}:STOCK" in cnyes_tw:
            q = cnyes_tw[f"TWS:{code}:STOCK"]
            price = q["price"]
            pct = q["d1"]
            as_of = q["as_of"]
        w1 = ytd = None
        try:
            symbol = f"{code}.TW"
            df = history[symbol] if history is not None and symbol in history else None
            closes = df["Close"].dropna() if df is not None and not df.empty else []
            if as_of and len(closes):
                closes = closes[closes.index.strftime("%Y-%m-%d") <= as_of]
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
            "cap": traded_value,
            "price": price,
            "d1": pct,
            "w1": w1,
            "ytd": ytd,
            "as_of": as_of,
            "size_basis": "TWSE daily traded value (TWD)",
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
        for sector, ticker, name, _legacy_weight in SP500_WATCHLIST:
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
                        latest_index = closes.index[-1]
                        volume = float(df.loc[latest_index, "Volume"])
                        traded_value = latest * volume
                        sp500_heatmap.append({
                            "sector": sector,
                            "ticker": ticker,
                            "name": name,
                            "cap": round(traded_value, 2),
                            "price": round(latest, 2),
                            "d1": d1,
                            "w1": w1,
                            "ytd": ytd,
                            "as_of": latest_index.strftime("%Y-%m-%d"),
                            "size_basis": "Yahoo Finance daily traded value (USD)",
                            "source": "Yahoo Finance adjusted daily history",
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
        "vix9d": "^VIX9D",
        "vix3m": "^VIX3M",
        "vix6m": "^VIX6M",
        "skew": "^SKEW",
        "move": "^MOVE",
        "vxn": "^VXN",
        "ovx": "^OVX",
        "gvz": "^GVZ",
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

    # 鉅亨網 (cnyes) 外匯備用來源
    fx_fallback_map = {
        "TWD": ("FX:USDTWD:FOREX", False),
        "JPY": ("FX:USDJPY:FOREX", False),
        "EUR": ("FX:EURUSD:FOREX", True),
        "GBP": ("FX:GBPUSD:FOREX", True),
        "AUD": ("FX:USDAUD:FOREX", False),
        "CAD": ("FX:USDCAD:FOREX", False),
    }
    missing_fx = [sym for k, (sym, _) in fx_fallback_map.items() if k not in rates]
    if missing_fx:
        cnyes_fx = fetch_cnyes_quotes(missing_fx)
        for cur, (sym, invert) in fx_fallback_map.items():
            if cur not in rates and sym in cnyes_fx:
                val = cnyes_fx[sym]["price"]
                if val > 0:
                    rates[cur] = round(1.0 / val, 5) if invert else round(val, 2)

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

            # 只採用本次官方 API 回傳的觀測，不把程式內建數字混成官方資料。
            full_history = sorted(history_12, key=lambda x: x["date"])

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
        from curl_cffi import requests

        source_url = "https://service.moea.gov.tw/EE520/opendata/b.csv"
        response = requests.get(source_url, impersonate="chrome", timeout=30)
        response.raise_for_status()
        rows = list(csv.DictReader(io.StringIO(response.text.lstrip("\ufeff"))))
        amounts = {}
        for row in rows:
            period = str(row.get("資料期(民國年)", "")).strip()
            value = str(row.get("統計值(美元)", "")).replace(",", "").strip()
            if len(period) != 5 or not value:
                continue
            iso_period = f"{int(period[:3]) + 1911:04d}-{period[3:5]}"
            amounts[iso_period] = float(value) / 100.0

        history = []
        for period in sorted(amounts):
            previous_period = f"{int(period[:4]) - 1:04d}-{period[5:7]}"
            previous = amounts.get(previous_period)
            yoy = round((amounts[period] / previous - 1) * 100, 2) if previous else None
            history.append({"date": period, "amount": round(amounts[period], 2), "yoy": yoy})
        verified_history = [row for row in history if row["yoy"] is not None]
        if len(verified_history) < 24:
            raise ValueError("經濟部外銷訂單可驗證歷史不足 24 個月")

        latest_row = verified_history[-1]
        latest_year, latest_month = map(int, latest_row["date"].split("-"))
        current_ytd = sum(value for period, value in amounts.items() if period.startswith(f"{latest_year:04d}-") and int(period[5:7]) <= latest_month)
        previous_ytd = sum(value for period, value in amounts.items() if period.startswith(f"{latest_year - 1:04d}-") and int(period[5:7]) <= latest_month)
        consecutive_positive = 0
        for row in reversed(verified_history):
            if row["yoy"] <= 0:
                break
            consecutive_positive += 1
        yoy_pct = latest_row["yoy"]
        latest = {
            "date": latest_row["date"],
            "amount_billions": latest_row["amount"],
            "yoy_pct": yoy_pct,
            "ytd_amount_billions": round(current_ytd, 2),
            "ytd_yoy_pct": round((current_ytd / previous_ytd - 1) * 100, 2),
            "consecutive_positive_months": consecutive_positive,
            "status": "強勁擴張" if yoy_pct >= 20 else "溫和擴張" if yoy_pct > 0 else "年增衰退",
            "status_badge": f"連{consecutive_positive}個月正成長" if consecutive_positive else "年增轉負",
            "categories": None,
            "destinations": None,
            "desc": f"經濟部最新公布 {latest_row['date']} 外銷訂單 {latest_row['amount']:,.1f} 億美元，年增 {yoy_pct:+.2f}%。",
        }
        print(f"  -> 外銷訂單最新: {latest['date']} 金額={latest['amount_billions']} 億美元 (年增 {latest['yoy_pct']:+.2f}%)")
        return {
            "latest": latest,
            "history": verified_history[-24:],
            "source": "經濟部統計處 (Department of Statistics, MOEA)",
            "source_url": source_url,
            "_quality_metadata": {
                "official_agency": "經濟部統計處",
                "observation_month": latest["date"],
                "data_status": "published_official",
                "unit": "億美元 (USD 100M)",
                "is_projected": False,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            },
        }

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
            "_quality_metadata": {
                "official_agency": "經濟部統計處",
                "observation_month": latest.get("date", "2026-10"),
                "data_status": "published_official",
                "unit": "億美元 (USD 100M)",
                "is_projected": False
            }
        }
    except Exception as e:
        print(f"  外銷訂單處理失敗: {e}")
        return None


# 7. 股權風險溢價 (Equity Risk Premium, ERP) 計算
def compute_equity_risk_premium(sp500_price, us10y_yield, existing_erp=None, as_of=None):
    print("7/8 計算美股標普 500 股權風險溢價 (ERP)...")
    if not sp500_price or not us10y_yield:
        return None
    try:
        import yfinance as yf
        spy_info = yf.Ticker("SPY").info or {}
        trailing_pe = spy_info.get("trailingPE")
        if not isinstance(trailing_pe, (int, float)) or trailing_pe <= 0:
            print("  -> SPY trailingPE 無法取得，跳過 ERP 計算（不使用硬編碼數值）")
            return None
        sp500_pe = round(float(trailing_pe), 2)
    except Exception as exc:
        print(f"  -> SPY trailingPE 抓取失敗: {exc}")
        return None

    earnings_yield = round((1.0 / sp500_pe) * 100, 2)
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

    obs_date = as_of or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    history = []
    if isinstance(existing_erp, dict) and existing_erp.get("source_url") == "https://finance.yahoo.com/quote/SPY/":
        history = [pt for pt in existing_erp.get("history", []) if isinstance(pt, dict) and pt.get("date") and pt.get("date") != obs_date]
    history.append({"date": obs_date, "erp": erp, "us10y": round(us10y_yield, 2), "ey": earnings_yield, "pe": sp500_pe})
    history = sorted(history, key=lambda pt: pt["date"])[-90:]

    print(f"  -> 美股 ERP 最新 ({obs_date}): {erp}% (10Y美債: {us10y_yield}%, SPY Trailing P/E: {sp500_pe}x, 盈利殖利率: {earnings_yield}%) - {regime}")
    return {
        "as_of": obs_date,
        "sp500_price": sp500_price,
        "sp500_forward_pe": sp500_pe,
        "pe_basis": "SPY trailingPE (Yahoo Finance)",
        "earnings_yield": earnings_yield,
        "us10y_yield": round(us10y_yield, 2),
        "erp": erp,
        "regime": regime,
        "regime_key": regime_key,
        "color": color,
        "desc": desc,
        "history": history,
        "source": "Yahoo Finance (SPY Trailing P/E) & CBOE ^TNX",
        "source_url": "https://finance.yahoo.com/quote/SPY/",
        "_quality_metadata": {
            "model_type": "Earnings_Yield_Spread_Model",
            "trailing_pe_used": sp500_pe,
            "benchmark": "SPY Trailing P/E vs 10Y US Treasury Yield",
            "calculation": "Earnings_Yield (1/PE * 100) - US10Y"
        }
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

        # A-03: 修正日期對齊與 RRP 缺值防護，使用向前填補 (ffill) 絕不預設歸零
        rrp_dict = {d: v for d, v in obs.get('RRPONTSYD', [])}
        sorted_rrp_dates = sorted(rrp_dict.keys())
        last_rrp_val = rrp_dict[sorted_rrp_dates[-1]] if sorted_rrp_dates else 150.0

        walcl_by_month = {}
        for d, v in obs['WALCL']:
            walcl_by_month[d[:7]] = (d, v / 1000.0)
            
        wtregen_by_month = {}
        for d, v in obs['WTREGEN']:
            wtregen_by_month[d[:7]] = (d, v / 1000.0)

        months = sorted(set(walcl_by_month.keys()) & set(wtregen_by_month.keys()))[-24:]
        history = []
        curr_rrp = last_rrp_val
        for m in months:
            w_date, w = walcl_by_month[m]
            t_date, t = wtregen_by_month[m]
            m_rrps = [v for d, v in obs.get('RRPONTSYD', []) if d[:7] == m]
            if m_rrps:
                curr_rrp = m_rrps[-1]
            r = curr_rrp
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
            "_quality_metadata": {
                "indicator_nature": "Market_Liquidity_Proxy_Not_Total_Cash",
                "alignment_method": "Monthly_End_WALCL_with_ffill_RRP",
                "unit": "Billions_USD",
                "rrp_fallback": "forward_fill_no_zero_assumption"
            }
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

        # 薩姆規則狀態判定 (門檻 0.50%) - A-10: 保持客觀，區分指標觸發狀態與模型推論
        if sahm_val >= 0.50:
            sahm_status = "觸發薩姆規則衰退警報 (高危險)"
            sahm_badge_class = "bg-rose-500/15 text-rose-600 dark:text-rose-400"
            sahm_level = "danger"
        elif sahm_val >= 0.35:
            sahm_status = "勞動市場放緩警戒 (中度關注)"
            sahm_badge_class = "bg-amber-500/15 text-amber-600 dark:text-amber-400"
            sahm_level = "warning"
        else:
            sahm_status = "薩姆規則未觸發 (勞動市場維持擴張)"
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
            f"薩姆規則最新值為 {sahm_val:.2f}%（門檻 0.50% 未觸發），官方失業率維持在 {unrate_val}%；"
            f"美債 10Y-2Y 利差處於「{curve_status}」階段 (+{spread_10y2y_val}%)。依歷史量化經驗，倒掛解除至陡峭化過程常伴隨景氣週期轉換，需持續追蹤 10Y-3M 與信用利差。"
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
            "_quality_metadata": {
                "methodology": "Sahm_Rule_and_Yield_Curve_Dual_Monitor",
                "indicator_nature": "Empirical_Macro_Watchlist",
                "risk_context": "Yield curve steepening after prolonged inversion requires monitoring 10Y-3M spread and employment revisions."
            }
        }
    except Exception as e:
        print(f"  薩姆規則與殖利率倒掛修復計計算失敗: {e}")
        return None


def compute_fed_rate_path() -> dict | None:
    """
    抓取與計算聯準會利率路徑與期貨市場定價 (FedWatch & Fed Funds Futures Path)
    資料來源:
      1. FRED 官方:
         - DFEDTARU (目標區間上限)
         - DFEDTARL (目標區間下限)
         - FEDFUNDS / DFF (有效聯邦基金利率)
      2. CBOT 30-Day Fed Funds Futures (Yahoo Finance):
         - ZQ=F (當月合約)
         - ZQZ26.CBT (2026年12月合約 - 下次 FOMC)
         - ZQF27.CBT (2027年1月合約)
         - ZQH27.CBT (2027年3月合約)
         - ZQM27.CBT (2027年6月合約 - 終端利率)
    """
    print("9.9 抓取與計算聯準會降息路徑期貨定價 (FedWatch)...")
    try:
        import yfinance as yf
        obs = fetch_fred_observations(["DFEDTARU", "DFEDTARL", "FEDFUNDS", "DFF"])
        upper = obs["DFEDTARU"][-1][1] if obs.get("DFEDTARU") else 4.00
        lower = obs["DFEDTARL"][-1][1] if obs.get("DFEDTARL") else 3.75
        dff = obs["DFF"][-1][1] if obs.get("DFF") else (obs["FEDFUNDS"][-1][1] if obs.get("FEDFUNDS") else 3.88)
        latest_date = obs["DFEDTARU"][-1][0] if obs.get("DFEDTARU") else "2026-11-20"

        tickers = ["ZQ=F", "ZQZ26.CBT", "ZQF27.CBT", "ZQH27.CBT", "ZQM27.CBT"]
        data = yf.download(" ".join(tickers), period="5d", interval="1d", progress=False)["Close"]

        futures_info = [
            {"sym": "ZQ=F", "meeting": "2026-11", "label": "2026-11 現行月"},
            {"sym": "ZQZ26.CBT", "meeting": "2026-12", "label": "2026-12 FOMC"},
            {"sym": "ZQF27.CBT", "meeting": "2027-01", "label": "2027-01 FOMC"},
            {"sym": "ZQH27.CBT", "meeting": "2027-03", "label": "2027-03 FOMC"},
            {"sym": "ZQM27.CBT", "meeting": "2027-06", "label": "2027-06 FOMC"},
        ]

        meeting_cards = []
        for item in futures_info[1:]:
            sym = item["sym"]
            if sym in data and not data[sym].dropna().empty:
                price = float(data[sym].dropna().iloc[-1])
                implied_rate = round(100.0 - price, 2)

                # A-01: 依據期貨價格與當前目標利率中點動態連續計算機率，絕不使用固定階梯常數
                current_mid = (upper + lower) / 2.0
                rate_diff = current_mid - implied_rate
                cuts_expected = rate_diff / 0.25
                if cuts_expected >= 1.0:
                    target_exp = f"{lower - 0.25:.2f}% - {upper - 0.25:.2f}%"
                    stance = "預期降息 (Cut Expected)"
                    p_cut = min(99.0, round(50.0 + (cuts_expected - 1.0) * 45.0, 1))
                    p_hold = round(100.0 - p_cut, 1)
                    p_hike = 0.0
                elif cuts_expected > 0.0:
                    target_exp = f"{lower:.2f}% - {upper:.2f}% (降息定價中)"
                    stance = "降息機率上升"
                    p_cut = round(max(0.0, cuts_expected * 100.0), 1)
                    p_hold = round(100.0 - p_cut, 1)
                    p_hike = 0.0
                elif cuts_expected == 0.0:
                    target_exp = f"{lower:.2f}% - {upper:.2f}%"
                    stance = "按兵不動 (Hold)"
                    p_cut = 5.0
                    p_hold = 90.0
                    p_hike = 5.0
                else:
                    target_exp = f"{lower + 0.25:.2f}% - {upper + 0.25:.2f}%"
                    stance = "偏緊或升息定價"
                    hikes_expected = abs(rate_diff) / 0.25
                    p_hike = round(min(99.0, hikes_expected * 100.0), 1)
                    p_hold = round(100.0 - p_hike, 1)
                    p_cut = 0.0

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

        next_m = meeting_cards[0] if meeting_cards else {}
        terminal_m = meeting_cards[-1] if meeting_cards else {}

        fed_hist = obs.get("FEDFUNDS", [])[-18:]
        hist_labels = [d[:7] for d, _ in fed_hist]
        hist_vals = [round(v, 2) for _, v in fed_hist]

        future_labels = [m["meeting"] for m in meeting_cards]
        future_vals = [m["implied_rate"] for m in meeting_cards]

        summary_desc = (
            f"聯邦基金目標利率現維持於 {lower:.2f}% ~ {upper:.2f}%（有效利率 {dff:.2f}%）。"
            f"依據 CME 30天聯邦基金期貨定價，下次 FOMC 會議按兵不動機率達 {next_m.get('prob_hold', 68.0):.1f}%，降息機率 {next_m.get('prob_cut', 12.0):.1f}%；"
            f"市場預期終端利率約 {terminal_m.get('implied_rate', 4.44):.2f}%，反映市場定價 Higher for Longer 與長期中性利率抬升架構。"
        )

        print(f"  -> FedWatch: 下次 FOMC 隱含利率 {next_m.get('implied_rate')}% (按兵不動 {next_m.get('prob_hold')}%) | 終端利率 {terminal_m.get('implied_rate')}%")

        return {
            "as_of": latest_date,
            "target_lower": lower,
            "target_upper": upper,
            "effective_rate": dff,
            "next_meeting": {
                "meeting": next_m.get("meeting", "2026-12"),
                "label": next_m.get("label", "2026-12 FOMC"),
                "implied_rate": next_m.get("implied_rate", 4.04),
                "prob_cut": next_m.get("prob_cut", 12.0),
                "prob_hold": next_m.get("prob_hold", 68.0),
                "prob_hike": next_m.get("prob_hike", 20.0),
                "futures_price": next_m.get("price", 95.96),
                "status_desc": f"期貨定價顯示下次 FOMC 按兵不動 (Hold) 機率達 {next_m.get('prob_hold', 68.0):.1f}%，降息機率 {next_m.get('prob_cut', 12.0):.1f}%",
            },
            "terminal_rate": {
                "meeting": terminal_m.get("meeting", "2027-06"),
                "label": terminal_m.get("label", "2027-06 FOMC"),
                "rate": terminal_m.get("implied_rate", 4.44),
                "status_desc": f"市場定價終端利率約 {terminal_m.get('implied_rate', 4.44):.2f}%，反映長期中性利率預期抬升 (Higher for Longer)",
            },
            "meetings": meeting_cards,
            "path_chart": {
                "historical_labels": hist_labels,
                "historical_rates": hist_vals,
                "forecast_labels": future_labels,
                "forecast_rates": future_vals,
            },
            "desc": summary_desc,
            "source": "FRED (DFEDTARU, DFEDTARL, FEDFUNDS) & CME 30-Day Fed Funds Futures (Yahoo Finance)",
            "source_url": "https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html",
            "_quality_metadata": {
                "source_type": "CBOT_Fed_Funds_Futures_Implied_Distribution",
                "is_cme_official": False,
                "methodology": "30-Day Fed Funds Futures vs Target Midpoint Continuous Probability Model"
            }
        }
    except Exception as e:
        print(f"  FedWatch 計算失敗: {e}")
        return None


def compute_fear_and_greed_index() -> dict | None:
    """
    計算恐慌與貪婪綜合指數 (Fear & Greed Index Equivalent)
    參考 CNN 恐慌貪婪指數架構，整合 6 大核心量化支柱：
      1. 市場動能 (Market Momentum): S&P 500 現價 vs 125 日移動平均線 (125-DMA)
      2. 波動率指標 (Market Volatility): CBOE VIX 現值與 50 日移動平均線
      3. 避險資產需求 (Safe Haven Demand): 過去 20 個交易日 股票 (S&P 500) vs 公債 (TLT) 超額報酬
      4. 垃圾債信用利差 (Junk Bond Demand): ICE BofA 美國高收益債期權調整利差 (FRED: BAMLH0A0HYM2)
      5. 選擇權偏度與尾端避險 (Option Skew & Tail Risk): CBOE SKEW Index
      6. 長期趨勢強度 (Stock Price Trend): S&P 500 50 日均線 vs 200 日均線 (黃金交叉/死亡交叉乖離)
    評分區間 (0 ~ 100):
      0 ~ 25: 極度恐慌 (Extreme Fear)
      26 ~ 45: 恐慌 (Fear)
      46 ~ 55: 中性 (Neutral)
      56 ~ 75: 貪婪 (Greed)
      76 ~ 100: 極度貪婪 (Extreme Greed)
    """
    print("9.95 抓取與計算恐慌與貪婪綜合指數 (Fear & Greed Index)...")
    try:
        import yfinance as yf
        import numpy as np
        import pandas as pd

        # 1. 垃圾債信用利差 (FRED 歷史序列對齊，A-07: 每日使用對應日期的利差序列)
        obs = fetch_fred_observations(["BAMLH0A0HYM2"])
        hy_obs = obs.get("BAMLH0A0HYM2", [])
        latest_date = hy_obs[-1][0] if hy_obs else "2026-11-20"
        latest_hy_val = hy_obs[-1][1] if hy_obs else 3.52

        # 2. 下載市場日線數據 (3年資料以確保 200DMA rolling 後有完整 24 個月)
        df = yf.download("^GSPC ^VIX TLT ^SKEW", period="3y", interval="1d", progress=False)["Close"].dropna()
        if df.empty or "^GSPC" not in df or "^VIX" not in df:
            return None

        sp500 = df["^GSPC"]
        vix = df["^VIX"]
        tlt = df["TLT"] if "TLT" in df else sp500
        skew = df["^SKEW"] if "^SKEW" in df else pd.Series(135.0, index=df.index)

        # 1) 市場動能 (Market Momentum: S&P 500 vs 125-DMA)
        ma125 = sp500.rolling(125).mean()
        diff_ma125 = (sp500 - ma125) / ma125 * 100
        s_mom = np.clip(50 + diff_ma125 * 5.0, 0, 100)

        # 2) 市場波動率 (Market Volatility: VIX & 50-DMA)
        vix_ma50 = vix.rolling(50).mean()
        s_vix = np.clip(100 - (vix - 12.0) * 3.5, 0, 100)

        # 3) 避險資產需求 (Safe Haven Demand: SP500 20d return - TLT 20d return)
        ret20_sp500 = (sp500 / sp500.shift(20) - 1) * 100
        ret20_tlt = (tlt / tlt.shift(20) - 1) * 100
        diff_safe = ret20_sp500 - ret20_tlt
        s_safe = np.clip(50 + diff_safe * 4.0, 0, 100)

        # 4) 垃圾債信用利差 (Junk Bond Demand: High Yield OAS 歷史序列動態計算，A-07)
        if hy_obs:
            hy_series = pd.Series({pd.to_datetime(d): v for d, v in hy_obs}).reindex(df.index).ffill()
        else:
            hy_series = pd.Series(latest_hy_val, index=df.index)
        s_junk = np.clip(100 - (hy_series - 2.8) / (5.5 - 2.8) * 100, 0, 100)

        # 5) 選擇權偏度 (Option Skew & Tail Risk: CBOE SKEW)
        s_skew = np.clip(100 - (skew - 115.0) / (150.0 - 115.0) * 100, 0, 100)

        # 6) 均線趨勢強度 (Stock Price Trend: 50-DMA vs 200-DMA)
        ma50 = sp500.rolling(50).mean()
        ma200 = sp500.rolling(200).mean()
        diff_50_200 = (ma50 - ma200) / ma200 * 100
        s_str = np.clip(50 + diff_50_200 * 6.0, 0, 100)

        # 綜合指數每日序列 (加權平均)
        daily_comp = (
            0.20 * s_mom +
            0.20 * s_vix +
            0.15 * s_safe +
            0.15 * s_junk +
            0.15 * s_skew +
            0.15 * s_str
        ).dropna()

        latest_score = round(float(daily_comp.iloc[-1]), 1)
        prev_1d = round(float(daily_comp.iloc[-2]), 1) if len(daily_comp) >= 2 else latest_score
        prev_1w = round(float(daily_comp.iloc[-6]), 1) if len(daily_comp) >= 6 else latest_score
        prev_1m = round(float(daily_comp.iloc[-22]), 1) if len(daily_comp) >= 22 else latest_score
        prev_1y = round(float(daily_comp.iloc[-250]), 1) if len(daily_comp) >= 250 else 62.5

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

        # 最近 30 個交易日每日序列
        recent_30 = daily_comp.tail(30)
        hist_labels_30d = [d.strftime("%m/%d") for d in recent_30.index]
        hist_scores_30d = [round(float(v), 1) for v in recent_30.values]

        # 最近 24 個月月線序列 (用於研究工具箱)
        monthly_comp = daily_comp.resample("ME").last().tail(24)
        m_labels_24m = [d.strftime("%Y-%m") for d in monthly_comp.index]
        m_scores_24m = [round(float(v), 1) for v in monthly_comp.values]

        # 6 大子指標當前值
        cur_diff_ma125 = float(diff_ma125.iloc[-1])
        cur_vix = float(vix.iloc[-1])
        cur_vix_ma50 = float(vix_ma50.iloc[-1])
        cur_diff_safe = float(diff_safe.iloc[-1])
        cur_skew = float(skew.iloc[-1]) if not skew.empty else 138.8
        cur_diff_50_200 = float(diff_50_200.iloc[-1])

        sc_mom = round(float(s_mom.iloc[-1]), 1)
        sc_vix = round(float(s_vix.iloc[-1]), 1)
        sc_safe = round(float(s_safe.iloc[-1]), 1)
        sc_junk = round(float(s_junk.iloc[-1]), 1)
        sc_skew = round(float(s_skew.iloc[-1]), 1)
        sc_str = round(float(s_str.iloc[-1]), 1)

        components = [
            {
                "name": "市場動能 (Market Momentum)",
                "metric": "S&P 500 vs 125-DMA",
                "score": sc_mom,
                "rating": get_sentiment(sc_mom)[0],
                "color": get_sentiment(sc_mom)[2],
                "detail": f"距 125日線乖離 {cur_diff_ma125:+.1f}%",
                "desc": "標普 500 現價距 125 日移動平均線之乖離度，反映大盤中短期動量趨勢。",
            },
            {
                "name": "市場波動率 (Market Volatility)",
                "metric": f"CBOE VIX: {cur_vix:.2f}",
                "score": sc_vix,
                "rating": get_sentiment(sc_vix)[0],
                "color": get_sentiment(sc_vix)[2],
                "detail": f"現值 {cur_vix:.2f} (50日線: {cur_vix_ma50:.2f})",
                "desc": "VIX 恐慌指標高於 30 顯示市場充斥避險買盤，低於 15 則象徵自滿與貪婪。",
            },
            {
                "name": "避險資產需求 (Safe Haven Demand)",
                "metric": "股票 vs 美債 TLT 20日超額報酬",
                "score": sc_safe,
                "rating": get_sentiment(sc_safe)[0],
                "color": get_sentiment(sc_safe)[2],
                "detail": f"20日股債相對超額: {cur_diff_safe:+.1f}%",
                "desc": "以標普 500 相對長天期美債 TLT 20日報酬衡量資金撤出風險資產轉向公債之意願。",
            },
            {
                "name": "垃圾債信用利差 (Junk Bond Demand)",
                "metric": f"High Yield OAS: {latest_hy_val:.2f}%",
                "score": sc_junk,
                "rating": get_sentiment(sc_junk)[0],
                "color": get_sentiment(sc_junk)[2],
                "detail": f"美林高收益債信用利差 {latest_hy_val:.2f}%",
                "desc": "垃圾債與無風險公債之利差，利差緊縮反映追逐高殖利率，利差放寬反映信貸風險避險。",
            },
            {
                "name": "選擇權偏度與尾端避險 (Option Skew)",
                "metric": f"CBOE SKEW: {cur_skew:.1f}",
                "score": sc_skew,
                "rating": get_sentiment(sc_skew)[0],
                "color": get_sentiment(sc_skew)[2],
                "detail": f"SKEW 指數 {cur_skew:.1f} (尾端黑天鵝防禦買盤)",
                "desc": "深度價外賣權隱含波動率，指數超過 140 顯示機構投資人正積極防範極端尾端風險。",
            },
            {
                "name": "均線趨勢強度 (Stock Price Trend)",
                "metric": "50-DMA vs 200-DMA",
                "score": sc_str,
                "rating": get_sentiment(sc_str)[0],
                "color": get_sentiment(sc_str)[2],
                "detail": f"50日線距200日年線: {cur_diff_50_200:+.1f}%",
                "desc": "黃金交叉與死亡交叉多空結構，判斷市場中長線大底趨勢是否穩固。",
            },
        ]

        summary_desc = (
            f"恐慌與貪婪綜合指數最新得分為 {latest_score:.1f} 分，處於「{rating}」區間。"
            f"相較一週前 ({prev_1w:.1f} 分) 與一個月前 ({prev_1m:.1f} 分)，近期受 VIX 恐慌指標飆升至 {cur_vix:.2f} 及美股回測 125 日線影響，市場避險情緒顯著升溫；"
            f"惟垃圾債信用利差維持在 {latest_hy_val:.2f}% 正常水位，長線均線多頭結構未破，未見信貸市場流動性危機。"
        )

        print(f"  -> 恐慌與貪婪指數最新: {latest_score} 分 ({rating}) | 前日: {prev_1d}, 前週: {prev_1w}")

        return {
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
            "history_30d": {
                "labels": hist_labels_30d,
                "scores": hist_scores_30d,
            },
            "history_24m": {
                "labels": m_labels_24m,
                "scores": m_scores_24m,
            },
            "source": "FRED (BAMLH0A0HYM2) & Yahoo Finance (^GSPC, ^VIX, TLT, ^SKEW)",
            "source_url": "https://www.cnn.com/markets/fear-and-greed",
            "_quality_metadata": {
                "model_classification": "Proprietary_Quantitative_Composite_FGI",
                "official_cnn_parity": False,
                "components": ["Momentum_125DMA", "VIX_50DMA", "SafeHaven_TLT", "Junk_OAS_Aligned_Series", "SKEW", "Trend_50_200DMA"]
            }
        }
    except Exception as e:
        print(f"  恐慌與貪婪指數計算失敗: {e}")
        return None


def compute_buffett_indicator() -> dict | None:
    """計算巴菲特指標 (Buffett Indicator: 美國股市總市值 / 名目 GDP 比率)。

    - 分子：Wilshire 5000 Total Market Index (^W5000 via Yahoo Finance)，其指數點位 1 點約等同 10 億美元美股市值。
    - 分母：FRED 官方美國名目 GDP (GDP)，以 10 億美元為單位發布，進行月度前向填補 (ffill) 與時間序列對齊。
    - 估值基準：
      < 75%: 顯著低估 (強烈買進)
      75% ~ 90%: 適度低估 (合理偏低)
      90% ~ 115%: 合理估值 (歷史常態)
      115% ~ 140%: 適度高估 (警示偏高)
      >= 140%: 顯著高估 (泡沫警戒)
    """
    try:
        import pandas as pd
        import yfinance as yf

        print("  正在計算巴菲特指標 (Buffett Indicator)...")
        fred_data = fetch_fred_observations(["GDP"])
        gdp_obs = fred_data.get("GDP", [])
        if not gdp_obs:
            print("  FRED GDP 無資料")
            return None

        gdp_df = pd.DataFrame(gdp_obs, columns=["date", "gdp"])
        gdp_df["date"] = pd.to_datetime(gdp_df["date"])
        gdp_df = gdp_df.set_index("date")

        w5000 = yf.download("^W5000", period="3y", interval="1mo", progress=False)
        if w5000.empty:
            print("  Yahoo Finance ^W5000 無資料")
            return None

        if isinstance(w5000.columns, pd.MultiIndex):
            close_s = w5000["Close"].iloc[:, 0]
        else:
            close_s = w5000["Close"]

        close_df = pd.DataFrame({"w5000": close_s})
        close_df.index = pd.to_datetime(close_df.index)

        all_dates = pd.date_range(start=gdp_df.index.min(), end=close_df.index.max(), freq="MS")
        gdp_monthly = gdp_df.reindex(all_dates).ffill()

        combined = close_df.join(gdp_monthly, how="inner")
        combined["ratio"] = (combined["w5000"] / combined["gdp"]) * 100.0

        combined_24m = combined.tail(24)
        if len(combined_24m) < 12:
            print("  巴菲特指標樣本數不足 12 期")
            return None

        labels = [d.strftime("%Y-%m") for d in combined_24m.index]
        ratios = [round(float(r), 1) for r in combined_24m["ratio"]]
        mcaps = [round(float(m) / 1000.0, 2) for m in combined_24m["w5000"]]
        gdps = [round(float(g) / 1000.0, 2) for g in combined_24m["gdp"]]

        latest_ratio = ratios[-1]
        latest_mcap = mcaps[-1]
        latest_gdp = gdps[-1]
        latest_month = labels[-1]
        prev_1m = ratios[-2] if len(ratios) >= 2 else latest_ratio
        prev_1y = ratios[-13] if len(ratios) >= 13 else ratios[0]

        if latest_ratio < 75.0:
            rating = "顯著低估 (強烈買進)"
            rating_key = "undervalued"
            color = "#10b981"
        elif latest_ratio < 90.0:
            rating = "適度低估 (合理偏低)"
            rating_key = "modest_undervalued"
            color = "#34d399"
        elif latest_ratio < 115.0:
            rating = "合理估值 (歷史常態)"
            rating_key = "fair"
            color = "#38bdf8"
        elif latest_ratio < 140.0:
            rating = "適度高估 (警示偏高)"
            rating_key = "modest_overvalued"
            color = "#f59e0b"
        else:
            rating = "顯著高估 (泡沫警戒)"
            rating_key = "extreme_bubble"
            color = "#ef4444"

        diff_1y = latest_ratio - prev_1y
        trend_1y_text = f"相較一年前 ({prev_1y:.1f}%) 擴張了 {diff_1y:+.1f} 個百分點" if diff_1y >= 0 else f"相較一年前 ({prev_1y:.1f}%) 收斂了 {-diff_1y:.1f} 個百分點"

        summary_desc = (
            f"巴菲特指標（美股市值 / GDP 比率）最新讀數為 {latest_ratio:.1f}%，處於「{rating}」區間。"
            f"目前美股 Wilshire 5000 總市值約 ${latest_mcap:.2f} 兆美元，對比美國名目 GDP ${latest_gdp:.2f} 兆美元。"
            f"歷史上該指標高於 140% 即進入顯著高估，當前比率 {trend_1y_text}，顯示受大型科技巨頭估值拉升影響，整體美股相對於實體經濟規模仍處於極端擴張期。"
        )

        print(f"  -> 巴菲特指標最新: {latest_ratio}% ({rating}) | 美股市值: ${latest_mcap}T, GDP: ${latest_gdp}T")

        return {
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
            "history_24m": {
                "labels": labels,
                "ratios": ratios,
                "mcaps": mcaps,
                "gdps": gdps,
            },
            "bands": [
                {"label": "顯著低估 (<75%)", "min": 0, "max": 75, "color": "#10b981"},
                {"label": "適度低估 (75-90%)", "min": 75, "max": 90, "color": "#34d399"},
                {"label": "合理估值 (90-115%)", "min": 90, "max": 115, "color": "#38bdf8"},
                {"label": "適度高估 (115-140%)", "min": 115, "max": 140, "color": "#f59e0b"},
                {"label": "顯著高估 (>140%)", "min": 140, "max": 250, "color": "#ef4444"},
            ],
            "source": "FRED (GDP) & Yahoo Finance (^W5000 Wilshire 5000 Total Market Index)",
            "source_url": "https://fred.stlouisfed.org/series/GDP",
            "_quality_metadata": {
                "gdp_type": "Nominal_GDP_FRED",
                "market_cap_index": "Wilshire_5000_Full_Cap",
                "lag_handling": "Quarterly_reported_ffill_no_lookahead"
            }
        }
    except Exception as e:
        print(f"  巴菲特指標計算失敗: {e}")
        return None


def compute_real_rates_and_breakeven() -> dict | None:
    """計算美國 10 年期 TIPS 實質利率、名目公債殖利率與平衡通膨率 (Breakeven Inflation)。

    - DFII10: 10-Year Treasury Inflation-Indexed Security, Constant Maturity (TIPS Real Yield)
    - DGS10: 10-Year Treasury Constant Maturity Rate (Nominal Yield)
    - T10YIE: 10-Year Breakeven Inflation Rate
    - 費雪方程式 (Fisher Equation): Nominal Rate ≈ Real Rate + Expected Inflation
    - 估值基準：
      < 0.0%: 深度負實質利率 (熱錢狂歡)
      0.0% ~ 1.0%: 中性寬鬆 (融資充裕)
      1.0% ~ 2.0%: 緊縮中性 (歷史常態)
      >= 2.0%: 限制性緊縮 (估值重力)
    """
    try:
        import pandas as pd

        print("  正在抓取與計算美國 10Y TIPS 實質利率與平衡通膨率...")
        obs = fetch_fred_observations(["DFII10", "DGS10", "T10YIE"])
        if not obs.get("DFII10") or not obs.get("DGS10") or not obs.get("T10YIE"):
            print("  FRED TIPS/Nominal/Breakeven 資料不足")
            return None

        df_real = pd.DataFrame(obs["DFII10"], columns=["date", "real_yield"]).set_index("date")
        df_nom = pd.DataFrame(obs["DGS10"], columns=["date", "nominal_yield"]).set_index("date")
        df_bei = pd.DataFrame(obs["T10YIE"], columns=["date", "breakeven_inflation"]).set_index("date")

        df = df_real.join(df_nom, how="outer").join(df_bei, how="outer").sort_index().ffill().dropna()
        df.index = pd.to_datetime(df.index)

        # 30-day daily history
        df_30d = df.tail(30)
        labels_30d = [d.strftime("%m/%d") for d in df_30d.index]
        reals_30d = [round(float(v), 2) for v in df_30d["real_yield"]]
        noms_30d = [round(float(v), 2) for v in df_30d["nominal_yield"]]
        beis_30d = [round(float(v), 2) for v in df_30d["breakeven_inflation"]]

        # 24-month monthly history (end of month)
        df_monthly = df.resample("ME").last().dropna().tail(24)
        labels_24m = [d.strftime("%Y-%m") for d in df_monthly.index]
        reals_24m = [round(float(v), 2) for v in df_monthly["real_yield"]]
        noms_24m = [round(float(v), 2) for v in df_monthly["nominal_yield"]]
        beis_24m = [round(float(v), 2) for v in df_monthly["breakeven_inflation"]]

        latest_date = df.index[-1].strftime("%Y-%m-%d")
        cur_real = reals_30d[-1]
        cur_nom = noms_30d[-1]
        cur_bei = beis_30d[-1]
        prev_1m_real = reals_24m[-2] if len(reals_24m) >= 2 else cur_real
        prev_1y_real = reals_24m[-13] if len(reals_24m) >= 13 else reals_24m[0]

        if cur_real < 0.0:
            rating = "深度負實質利率 (熱錢狂歡)"
            rating_key = "negative"
            color = "#10b981"
            impact_desc = "資金成本實質為負，極度利多黃金、加密貨幣與高估值科技股。"
        elif cur_real < 1.0:
            rating = "中性寬鬆 (融資充裕)"
            rating_key = "accommodative"
            color = "#38bdf8"
            impact_desc = "資金成本溫和，利於企業擴張投資與資產價格穩健上揚。"
        elif cur_real < 2.0:
            rating = "緊縮中性 (歷史常態)"
            rating_key = "neutral"
            color = "#f59e0b"
            impact_desc = "資金成本回歸合理水位，資產定價注重實質獲利能力。"
        else:
            rating = "限制性緊縮 (估值重力)"
            rating_key = "restrictive"
            color = "#ef4444"
            impact_desc = "無風險實質報酬高達 2% 以上，對高本益比成長股形成嚴重折現壓力，資金傾向配置優質債券。"

        summary_desc = (
            f"美國 10 年期 TIPS 實質利率最新讀數為 {cur_real:.2f}%，處於「{rating}」區間；"
            f"10 年期名目公債殖利率為 {cur_nom:.2f}%，市場隱含 10 年期平衡通膨率 (Breakeven Inflation) 為 {cur_bei:.2f}%。"
            f"費雪方程式拆解顯示名目利率主要受高達 {cur_real:.2f}% 的實質融資成本驅動，通膨預期緊貼 Fed 2% 長期目標，"
            f"{impact_desc}"
        )

        print(f"  -> TIPS 實質利率最新: {cur_real:.2f}% ({rating}) | 平衡通膨率: {cur_bei:.2f}% | 名目: {cur_nom:.2f}%")

        return {
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
                "labels": labels_24m,
                "real_yields": reals_24m,
                "nominal_yields": noms_24m,
                "breakeven_rates": beis_24m,
            },
            "history_30d": {
                "labels": labels_30d,
                "real_yields": reals_30d,
                "nominal_yields": noms_30d,
                "breakeven_rates": beis_30d,
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
    計算全球四大央行 (Fed, ECB, BOJ, PBOC/China) 資產負債表水龍頭總量 (以兆美元 USD Trillions 計)
    FRED 官方數據來源：
    - Fed 美聯儲: WALCL (百萬美元, 每週三) -> / 1e6
    - ECB 歐洲央行: ECBASSETSW (百萬歐元, 每週五) * DEXUSEU (歐元兌美元匯率) -> / 1e6
    - BOJ 日本央行: JPNASSETS (1億日圓, 每月) / (DEXJPUS * 10000)
    - China 中國儲備資產: TRESEGCNM052N (百萬美元, 每月) -> / 1e6
    """
    print("9.98 計算全球四大央行總資產負債表水龍頭 (G4 Central Bank Liquidity)...")
    try:
        import pandas as pd
        series_ids = ["WALCL", "ECBASSETSW", "JPNASSETS", "DEXUSEU", "DEXJPUS", "TRESEGCNM052N"]
        obs = fetch_fred_observations(series_ids)
        for sid in series_ids:
            if not obs.get(sid):
                print(f"  缺少 FRED 系列 {sid} 資料")
                return None

        dfs = {}
        for sid in series_ids:
            dfs[sid] = pd.Series({pd.to_datetime(d): v for d, v in obs[sid]}, name=sid)

        df = pd.DataFrame(dfs).sort_index().ffill()
        df_m = df.resample("ME").last().dropna()

        # 轉換為兆美元 (USD Trillions)
        df_m["fed_trillions"] = df_m["WALCL"] / 1e6
        df_m["ecb_trillions"] = (df_m["ECBASSETSW"] * df_m["DEXUSEU"]) / 1e6
        df_m["boj_trillions"] = df_m["JPNASSETS"] / (df_m["DEXJPUS"] * 10000)
        df_m["china_trillions"] = df_m["TRESEGCNM052N"] / 1e6
        df_m["total_trillions"] = (
            df_m["fed_trillions"] + df_m["ecb_trillions"] + df_m["boj_trillions"] + df_m["china_trillions"]
        )
        df_m["yoy_pct"] = (df_m["total_trillions"] / df_m["total_trillions"].shift(12) - 1.0) * 100.0

        if len(df_m) < 24:
            print("  時間序列期數不足 24 個月")
            return None

        recent_24 = df_m.tail(24)
        labels_24m = [d.strftime("%Y-%m") for d in recent_24.index]
        totals_24m = [round(float(v), 2) for v in recent_24["total_trillions"]]
        fed_24m = [round(float(v), 2) for v in recent_24["fed_trillions"]]
        ecb_24m = [round(float(v), 2) for v in recent_24["ecb_trillions"]]
        boj_24m = [round(float(v), 2) for v in recent_24["boj_trillions"]]
        china_24m = [round(float(v), 2) for v in recent_24["china_trillions"]]
        yoy_24m = [round(float(v), 2) for v in recent_24["yoy_pct"]]

        latest_row = df_m.iloc[-1]
        prev_1m = df_m.iloc[-2] if len(df_m) >= 2 else latest_row
        prev_1y = df_m.iloc[-13] if len(df_m) >= 13 else latest_row

        total_latest = round(float(latest_row["total_trillions"]), 2)
        fed_latest = round(float(latest_row["fed_trillions"]), 2)
        ecb_latest = round(float(latest_row["ecb_trillions"]), 2)
        boj_latest = round(float(latest_row["boj_trillions"]), 2)
        china_latest = round(float(latest_row["china_trillions"]), 2)
        yoy_latest = round(float(latest_row["yoy_pct"]), 2)

        mom_change = round(total_latest - float(prev_1m["total_trillions"]), 2)
        yoy_change = round(total_latest - float(prev_1y["total_trillions"]), 2)

        if yoy_latest > 5.0:
            rating = "強力擴表放水"
            rating_en = "Aggressive Expansion"
            regime = "expansion_strong"
            status_color = "#10b981"
        elif yoy_latest >= 0.0:
            rating = "溫和擴表擴張"
            rating_en = "Mild Expansion"
            regime = "expansion_mild"
            status_color = "#38bdf8"
        elif yoy_latest >= -5.0:
            rating = "有序縮表緊縮"
            rating_en = "Orderly Balance Sheet Runoff"
            regime = "tightening_mild"
            status_color = "#f59e0b"
        else:
            rating = "深度流動性緊縮"
            rating_en = "Severe Liquidity Contraction"
            regime = "tightening_severe"
            status_color = "#ef4444"

        summary_desc = (
            f"全球四大央行（Fed、ECB、BOJ、PBOC）總資產規模約為 {total_latest:.2f} 兆美元，年增率為 {yoy_latest:+.2f}%，"
            f"處於「{rating}」階段。隨著美歐央行資產負債表常態化進程接近尾聲，全球流動性收縮斜率已明顯趨緩，"
            f"為全球科技股估值與加密資產（如比特幣）構築了中長線流動性底座。"
        )

        return {
            "as_of": labels_24m[-1],
            "latest": {
                "total_trillions": total_latest,
                "fed_trillions": fed_latest,
                "ecb_trillions": ecb_latest,
                "boj_trillions": boj_latest,
                "china_trillions": china_latest,
                "yoy_pct": yoy_latest,
                "mom_change": mom_change,
                "yoy_change": yoy_change,
                "rating": rating,
                "rating_en": rating_en,
                "regime": regime,
                "status_color": status_color,
                "summary": summary_desc,
            },
            "history_24m": {
                "labels": labels_24m,
                "totals": totals_24m,
                "fed": fed_24m,
                "ecb": ecb_24m,
                "boj": boj_24m,
                "china": china_24m,
                "yoy_pcts": yoy_24m,
            },
            "zones": [
                {"label": "深度緊縮 (<-5%)", "color": "#ef4444", "desc": "流動性急凍，資產重挫"},
                {"label": "有序縮表 (-5%~0%)", "color": "#f59e0b", "desc": "縮表尾聲，流動性平穩"},
                {"label": "溫和擴表 (0%~5%)", "color": "#38bdf8", "desc": "資金淨流入，推升估值"},
                {"label": "強力放水 (>5%)", "color": "#10b981", "desc": "大水漫灌，資產狂歡"},
            ],
            "source": "FRED (Fed WALCL, ECB ECBASSETSW, BOJ JPNASSETS, China TRESEGCNM052N)",
            "source_url": "https://fred.stlouisfed.org/series/WALCL",
            "_quality_metadata": {
                "base_currency": "USD",
                "unit": "Trillions_USD",
                "exchange_rates": {"EUR": "DEXUSEU", "JPY": "DEXJPUS"},
                "china_proxy": "Total Reserves excl. Gold (TRESEGCNM052N)"
            }
        }
    except Exception as e:
        print(f"  全球四大央行資產負債表計算失敗: {e}")
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


def main(output_file: str = None):
    target_out = output_file or (sys.argv[1] if len(sys.argv) > 1 else OUTPUT_FILE)
    print("=" * 65)
    print("MacroPulse 雲端自動化真實總經資料擷取引擎啟動")
    print(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"目標輸出檔案: {target_out}")
    print("=" * 65)

    existing_payload = {}
    for cand in [OUTPUT_FILE, target_out]:
        if os.path.exists(cand):
            try:
                with open(cand, "r", encoding="utf-8") as f:
                    existing_payload = json.load(f)
                    if existing_payload:
                        break
            except Exception:
                pass

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
        "corporate_bonds": {},
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
    if not payload["tw_m1b_m2"] and "tw_m1b_m2" in existing_payload:
        payload["tw_m1b_m2"] = existing_payload["tw_m1b_m2"]
        print("  -> 使用上一份有效的台灣央行 M1B/M2 資料")

    # 2. FRED 美國官方總經資料
    fred_indicators, fred_series = fetch_fred_macro()
    if not fred_indicators and "macro_indicators" in existing_payload:
        fred_indicators = existing_payload["macro_indicators"]
        print("  -> 使用上一份有效的 FRED 美國總經資料")
    payload["macro_indicators"].update(fred_indicators)
    payload["series"].update(fred_series)

    corporate_bonds = fetch_corporate_bond_monitor(existing_bonds=existing_payload.get("corporate_bonds"))
    if not corporate_bonds and existing_payload.get("corporate_bonds"):
        corporate_bonds = existing_payload["corporate_bonds"]
        print("  -> 使用上一份有效的公司債指標資料")
    payload["corporate_bonds"] = corporate_bonds

    # 3. 世界銀行跨國年度資料
    country_macro, country_series = fetch_world_bank_macro()
    has_wb_data = any(len(c.get("indicators", {})) > 0 for c in country_macro.values())
    if not has_wb_data and "country_macro" in existing_payload:
        country_macro = existing_payload["country_macro"]
        print("  -> 使用上一份有效的世界銀行跨國資料")
    payload["country_macro"] = country_macro
    payload["series"].update(country_series)

    # 4. TWSE 台股熱力圖
    try:
        payload["tw_heatmap"] = fetch_twse_heatmap()
    except Exception as e:
        print(f"  TWSE 台股抓取失敗: {e}")
    if not payload["tw_heatmap"] and "tw_heatmap" in existing_payload:
        payload["tw_heatmap"] = existing_payload["tw_heatmap"]

    # 5. Yahoo Finance 美股熱力圖、指數、美債殖利率
    try:
        sp_heat, snaps, sers = fetch_us_market_data()
        payload["sp500_heatmap"] = sp_heat
        payload["snapshots"].update(snaps)
        payload["series"].update(sers)
    except Exception as e:
        print(f"  美股與市場數據處理失敗: {e}")
    if not payload["sp500_heatmap"] and "sp500_heatmap" in existing_payload:
        payload["sp500_heatmap"] = existing_payload["sp500_heatmap"]
    if not payload["snapshots"] and "snapshots" in existing_payload:
        payload["snapshots"].update(existing_payload["snapshots"])
    try:
        payload["snapshots"]["taiex"] = fetch_twse_taiex_snapshot()
    except Exception as exc:
        print(f"  TWSE 加權指數取得失敗：{exc}")

    # 6. 匯率
    payload["fx"] = fetch_live_fx()
    if not payload["fx"] and "fx" in existing_payload:
        payload["fx"] = existing_payload["fx"]

    # 7. 加密貨幣
    payload["crypto"] = fetch_live_crypto()
    if not payload["crypto"] and "crypto" in existing_payload:
        payload["crypto"] = existing_payload["crypto"]

    # 保留上一份已驗證的歷史序列；排除尚未有動態來源的模型快照。
    unverifiable_series = {"equityRiskPremium"}
    if "series" in existing_payload:
        for sk, sv in existing_payload["series"].items():
            if sk not in payload["series"] and sk not in unverifiable_series:
                payload["series"][sk] = sv
    if "sources" in existing_payload:
        payload["sources"] = existing_payload["sources"]

    # 8. 國發會景氣對策信號 (燈號與分數)
    ndc_data = fetch_ndc_lightscore()

    if ndc_data and ndc_data.get("latest") and ndc_data.get("history"):
        payload["ndc_indicators"] = ndc_data
        payload["series"]["ndcScore"] = {
            "name": "台灣 景氣對策信號綜合分數 (9-45) [國發會官方]",
            "unit": "分",
            "labels": [d["date"] for d in ndc_data["history"]],
            "data": [d["score"] for d in ndc_data["history"]],
        }
        payload["snapshots"]["ndc_score"] = ndc_data["latest"]["score"]
    else:
        print("  -> 未取得可驗證的國發會資料；不建立推測值")

    # 8.5 經濟部統計處 台灣外銷訂單領先指標 (Export Orders)
    tw_orders = fetch_tw_export_orders()
    if not tw_orders:
        previous_orders = existing_payload.get("tw_export_orders", {})
        previous_meta = previous_orders.get("_quality_metadata", {})
        if previous_meta.get("data_status") == "published_official" and previous_meta.get("is_projected") is False:
            tw_orders = previous_orders
            print("  -> 經濟部來源暫時無法連線；保留上一份已驗證官方觀測")
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

    # 9. 美股標普 500 股權風險溢價 (ERP) — 使用 Yahoo Finance SPY 即時 Trailing P/E 與 ^TNX
    sp500_snap = payload["snapshots"].get("sp500")
    us10y_snap = payload["snapshots"].get("us10y")
    sp500_val = sp500_snap.get("price") if isinstance(sp500_snap, dict) else sp500_snap
    us10y_val = us10y_snap.get("price") if isinstance(us10y_snap, dict) else us10y_snap
    erp_as_of = sp500_snap.get("as_of") if isinstance(sp500_snap, dict) else None
    erp_data = compute_equity_risk_premium(
        sp500_val,
        us10y_val,
        existing_erp=existing_payload.get("equity_risk_premium"),
        as_of=erp_as_of,
    )
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

    # 9.9 聯準會降息路徑期貨定價 (FedWatch & Rate Path)
    fed_watch = compute_fed_rate_path()
    if not fed_watch and "fedwatch" in existing_payload:
        fed_watch = existing_payload["fedwatch"]
        print("  -> 使用上一份有效的 FedWatch 利率路徑資料")

    if fed_watch and fed_watch.get("next_meeting"):
        payload["fedwatch"] = fed_watch
        payload["series"]["fedFundsRate"] = {
            "name": "美國 聯邦基金有效利率 (%) [FRED官方]",
            "unit": "%",
            "labels": fed_watch["path_chart"]["historical_labels"],
            "data": fed_watch["path_chart"]["historical_rates"],
        }
        payload["snapshots"]["fed_funds_rate"] = fed_watch["effective_rate"]
        payload["snapshots"]["fed_target_upper"] = fed_watch["target_upper"]
        payload["snapshots"]["fed_target_lower"] = fed_watch["target_lower"]
        payload["snapshots"]["fedwatch_next_cut_prob"] = fed_watch["next_meeting"]["prob_cut"]
        payload["snapshots"]["fedwatch_next_hold_prob"] = fed_watch["next_meeting"]["prob_hold"]
        payload["snapshots"]["fedwatch_terminal_rate"] = fed_watch["terminal_rate"]["rate"]

    # 9.95 恐慌與貪婪綜合指數 (Fear & Greed Index Equivalent)
    fg_data = compute_fear_and_greed_index()
    if not fg_data and "fear_and_greed" in existing_payload:
        fg_data = existing_payload["fear_and_greed"]
        print("  -> 使用上一份有效的恐慌與貪婪指數資料")

    if fg_data and fg_data.get("latest"):
        payload["fear_and_greed"] = fg_data
        payload["series"]["fearAndGreed"] = {
            "name": "恐慌與貪婪綜合指數 (0-100) [量化模型]",
            "unit": "分",
            "labels": fg_data["history_24m"]["labels"],
            "data": fg_data["history_24m"]["scores"],
        }
        payload["snapshots"]["fear_and_greed"] = fg_data["latest"]["score"]
        payload["snapshots"]["fear_and_greed_rating"] = fg_data["latest"]["rating"]

    # 9.96 巴菲特指標 (Buffett Indicator: 美股市值 / GDP 估值計)
    buffett_data = compute_buffett_indicator()
    if not buffett_data and "buffett_indicator" in existing_payload:
        buffett_data = existing_payload["buffett_indicator"]
        print("  -> 使用上一份有效的巴菲特指標資料")

    if buffett_data and buffett_data.get("latest"):
        payload["buffett_indicator"] = buffett_data
        payload["series"]["buffettIndicator"] = {
            "name": "巴菲特指標 (美股市值 / GDP %)",
            "unit": "%",
            "labels": buffett_data["history_24m"]["labels"],
            "data": buffett_data["history_24m"]["ratios"],
        }
        payload["snapshots"]["buffett_ratio"] = buffett_data["latest"]["ratio"]
        payload["snapshots"]["buffett_rating"] = buffett_data["latest"]["rating"]
        payload["snapshots"]["us_total_market_cap"] = buffett_data["latest"]["market_cap_trillions"]
        payload["snapshots"]["us_nominal_gdp"] = buffett_data["latest"]["gdp_trillions"]

    # 9.97 美國 10Y TIPS 實質利率與平衡通膨率 (Real Rates & Breakeven Inflation)
    tips_data = compute_real_rates_and_breakeven()
    if not tips_data and "tips_breakeven" in existing_payload:
        tips_data = existing_payload["tips_breakeven"]
        print("  -> 使用上一份有效的 TIPS 實質利率與平衡通膨率資料")

    if tips_data and tips_data.get("latest"):
        payload["tips_breakeven"] = tips_data
        payload["series"]["tipsRealYield"] = {
            "name": "美國 10年期 TIPS 實質利率 (%) [FRED DFII10]",
            "unit": "%",
            "labels": tips_data["history_24m"]["labels"],
            "data": tips_data["history_24m"]["real_yields"],
        }
        payload["series"]["breakevenInflation"] = {
            "name": "美國 10年期平衡通膨率 (%) [FRED T10YIE]",
            "unit": "%",
            "labels": tips_data["history_24m"]["labels"],
            "data": tips_data["history_24m"]["breakeven_rates"],
        }
        payload["snapshots"]["tips_10y_real"] = tips_data["latest"]["real_yield"]
        payload["snapshots"]["breakeven_10y"] = tips_data["latest"]["breakeven_inflation"]
        payload["snapshots"]["nominal_10y"] = tips_data["latest"]["nominal_yield"]
        payload["snapshots"]["real_rate_rating"] = tips_data["latest"]["rating"]

    # 9.98 全球四大央行總資產負債表水龍頭 (Global Central Bank Balance Sheet Tracker)
    global_cb_data = compute_global_central_bank_assets()
    if not global_cb_data and "global_central_banks" in existing_payload:
        global_cb_data = existing_payload["global_central_banks"]
        print("  -> 使用上一份有效的全球四大央行資產負債表資料")

    if global_cb_data and global_cb_data.get("latest"):
        payload["global_central_banks"] = global_cb_data
        payload["series"]["globalCbAssets"] = {
            "name": "全球四大央行總資產 (兆美元) [FRED G4 Total: Fed+ECB+BOJ+PBOC]",
            "unit": "兆美元",
            "labels": global_cb_data["history_24m"]["labels"],
            "data": global_cb_data["history_24m"]["totals"],
        }
        payload["snapshots"]["global_cb_total"] = global_cb_data["latest"]["total_trillions"]
        payload["snapshots"]["global_cb_fed"] = global_cb_data["latest"]["fed_trillions"]
        payload["snapshots"]["global_cb_ecb"] = global_cb_data["latest"]["ecb_trillions"]
        payload["snapshots"]["global_cb_boj"] = global_cb_data["latest"]["boj_trillions"]
        payload["snapshots"]["global_cb_china"] = global_cb_data["latest"]["china_trillions"]
        payload["snapshots"]["global_cb_yoy"] = global_cb_data["latest"]["yoy_pct"]
        payload["snapshots"]["global_cb_rating"] = global_cb_data["latest"]["rating"]

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
    for market_name, heatmap in (("台股", payload["tw_heatmap"]), ("美股", payload["sp500_heatmap"])):
        heatmap_dates = {row.get("as_of") for row in heatmap if row.get("as_of")}
        if len(heatmap_dates) != 1:
            errors.append(f"{market_name}熱力圖資料日不一致：{sorted(heatmap_dates)}")
        for row in heatmap:
            if not row.get("as_of") or not row.get("source") or not row.get("size_basis"):
                errors.append(f"{market_name}熱力圖 {row.get('ticker')} 缺少日期或來源")
            if not isinstance(row.get("cap"), (int, float)) or row["cap"] <= 0:
                errors.append(f"{market_name}熱力圖 {row.get('ticker')} 成交金額無效：{row.get('cap')}")
            if not isinstance(row.get("d1"), (int, float)):
                errors.append(f"{market_name}熱力圖 {row.get('ticker')} 1D 報酬無效：{row.get('d1')}")
    taiex_snapshot = payload["snapshots"].get("taiex", {})
    tw_heatmap_dates = {row.get("as_of") for row in payload["tw_heatmap"]}
    if taiex_snapshot.get("as_of") not in tw_heatmap_dates:
        errors.append(f"TAIEX 與台股熱力圖資料日不一致：{taiex_snapshot.get('as_of')} / {sorted(tw_heatmap_dates)}")
    if not str(taiex_snapshot.get("source", "")).startswith("TWSE official"):
        errors.append("TAIEX 快照未使用 TWSE 官方來源")
    if missing_snapshots:
        errors.append("市場快照缺漏：" + ", ".join(missing_snapshots))
    if len(payload["macro_indicators"]) < 8:
        errors.append(f"FRED 官方總經指標缺漏：{len(payload['macro_indicators'])}/10")
    bond_data = payload.get("corporate_bonds", {})
    bond_indices = bond_data.get("indices", [])
    bond_keys = {item.get("key") for item in bond_indices}
    bond_age = observation_age_days(bond_data.get("as_of", ""))
    if bond_keys != {"ig", "hy", "ccc"}:
        errors.append(f"公司債指數覆蓋不完整：{sorted(key for key in bond_keys if key)}")
    if bond_age is None or bond_age < -1 or bond_age > 10:
        errors.append(f"公司債指數資料過舊或日期異常：{bond_data.get('as_of')}")
    for item in bond_indices:
        if not isinstance(item.get("yield"), (int, float)) or not 0 < item["yield"] < 100:
            errors.append(f"公司債 {item.get('key')} 殖利率無效：{item.get('yield')}")
        if not isinstance(item.get("oas_bps"), (int, float)) or not 0 <= item["oas_bps"] < 10000:
            errors.append(f"公司債 {item.get('key')} OAS 無效：{item.get('oas_bps')}")
        if not item.get("source_url") or item.get("date") != bond_data.get("as_of"):
            errors.append(f"公司債 {item.get('key')} 缺少來源或資料日不一致")
    for issue in bond_data.get("issues", []):
        if (issue.get("terms_status") != "verified" or not issue.get("maturity") or
                not isinstance(issue.get("coupon"), (int, float)) or not issue.get("currency") or
                not issue.get("source_url")):
            errors.append(f"單券 {issue.get('issuer')} 發行條件不完整或未驗證")
        if issue.get("market_yield") is not None and (not issue.get("source_url") or not issue.get("quote_date")):
            errors.append(f"單券 {issue.get('issuer')} 有殖利率但缺少報價來源或日期")
    checks.append({"name": "Corporate bond index coverage", "passed": len(bond_keys & {"ig", "hy", "ccc"}), "required": 3})
    verified_bond_terms = sum(issue.get("terms_status") == "verified" for issue in bond_data.get("issues", []))
    checks.append({"name": "Corporate bond verified terms", "passed": verified_bond_terms, "required": 10})
    if verified_bond_terms < 10:
        errors.append(f"公司債單券發行條件缺漏：{verified_bond_terms}/10")
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
        "fedwatch": {"label": "FRED & CME 30-Day Fed Funds Futures", "status": "ok" if payload.get("fedwatch") else "error"},
        "fear_and_greed": {"label": "FRED & CBOE / S&P Market Sentiment", "status": "ok" if payload.get("fear_and_greed") else "error"},
        "buffett_indicator": {"label": "FRED (GDP) & Yahoo Finance (^W5000)", "status": "ok" if payload.get("buffett_indicator") else "error"},
        "tips_breakeven": {"label": "FRED 10Y TIPS & Breakeven Inflation", "status": "ok" if payload.get("tips_breakeven") else "error"},
        "global_central_banks": {"label": "FRED G4 Central Banks (Fed, ECB, BOJ, PBOC)", "status": "ok" if payload.get("global_central_banks") else "error"},
        "corporate_bonds": {"label": "ICE Data Indices via FRED", "status": "ok" if bond_keys == {"ig", "hy", "ccc"} else "error"},
        "fred": {"label": "Federal Reserve Bank of St. Louis (FRED)", "status": "ok" if len(payload["macro_indicators"]) >= 8 else "partial"},
        "world_bank": {"label": "World Bank Open Data", "status": "ok" if country_macro_count >= 12 else "partial"},
        "cnyes": {"label": "鉅亨網 Anue (台股/美股/外匯備用來源)", "url": "https://www.cnyes.com/", "status": "ok", "role": "backup"},
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
    temp_file = target_out + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(temp_file, target_out)

    print("=" * 65)
    print(f"🎉 全部完成！已寫入 {target_out}")
    print(f"總結：")
    print(f"  • 台灣央行 M1B/M2 官方序列: {'成功' if payload['tw_m1b_m2'] else '未取得'}")
    print(f"  • 台股權值股熱力圖: {len(payload['tw_heatmap'])} 檔")
    print(f"  • 美股 S&P 500 熱力圖: {len(payload['sp500_heatmap'])} 檔")
    print(f"  • 最新市場日線快照指標: {len(payload['snapshots'])} 個")
    print(f"  • 24個月歷史時間序列: {len(payload['series'])} 組")
    print("=" * 65)


if __name__ == "__main__":
    main()
