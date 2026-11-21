# MacroPulse 總經脈動 (MacroPulse Decision Radar)

[![GitHub Pages](https://img.shields.io/badge/Live%20Demo-GitHub%20Pages-blue?style=for-the-badge&logo=github)](https://masonhung8888.github.io/macropulse/)
[![Update Workflow](https://img.shields.io/badge/Automated%20Data-GitHub%20Actions-brightgreen?style=for-the-badge&logo=githubactions)](https://github.com/MasonHung8888/macropulse/actions)
[![Data Authenticity](https://img.shields.io/badge/Data%20Source-100%25%20Verified%20Official-success?style=for-the-badge)](https://masonhung8888.github.io/macropulse/)
[![License](https://img.shields.io/badge/License-MIT-amber?style=for-the-badge)](LICENSE)

> **全自動化・100% 官方真實數據・機構級跨國總體經濟決策雷達與資產配置分析平台**  
> 線上即時體驗：[https://masonhung8888.github.io/macropulse/](https://masonhung8888.github.io/macropulse/)

---

## 📌 平台核心定位與設計理念

**MacroPulse** 專為總經研究員、專業投資人與量化交易者打造。平台摒棄所有虛構模擬（Zero Mock Data）與固定假數字，整合美、台、歐、中、日多國央行與部會級官方數據源，並透過 GitHub Actions 雲端自動化排程引擎，每日在台美股盤後自動抓取、校驗並發布最新總經情勢與資產走勢。

---

## 🚀 核心功能與專業儀表板模組

### 1. 💧 美國 Fed 淨流動性指數（Fed Net Liquidity Tracker）
* **經濟模型**：
  $$\text{Fed 淨流動性} = \text{Fed 總資產 (WALCL)} - \text{財政部 TGA 存款 (WTREGEN)} - \text{隔夜逆回購 (RRPONTSYD)}$$
* **功能特色**：
  - 扣除財政部與貨幣基金停泊在聯準會之「死錢」，量化推動標普 500 (S&P 500) 估值定價的真實美元活水水位。
  - 雙軸走勢圖同步疊加標普 500 指數，精確捕捉「水庫放水 → 估值擴張」與「水庫抽水 → 股市承壓」之流動性週期轉換。
  - 即時呈現最新淨流動性總量、單月增減額與擴張／收縮狀態徽章。

### 2. 🛡️ 薩姆規則衰退預警 ＆ 殖利率倒掛修復計（Recession Radar）
* **薩姆規則 (Sahm Rule)**：
  - 追蹤 Claudia Sahm 官方失業率動能指標（3 個月移動平均 vs 過去 12 個月低點之差值）。
  - 當指標 $\ge 0.50\%$ 即觸發衰退警戒。過去半世紀歷史命中率 100%。
* **美債殖利率倒掛修復計 (Yield Curve Meter)**：
  - 整合美債 10Y-2Y 與 10Y-3M 殖利率利差。
  - 監控倒掛解除後的「陡峭化（Steepening）階段」——深入判斷是硬著陸緊急降息驅動的「牛陡」，亦或軟著陸擴張驅動的「正常化修復」。

### 3. 📦 台灣外銷訂單領先指標（Taiwan Export Orders Leading Indicator）
* **經濟部統計處官方權威發布**：
  - 台灣為全球 AI 與半導體硬體製造中樞，國際大廠提前 1~3 個月下單。外銷訂單年增率（YoY）為「台股加權指數 (TAIEX)」獲利成長最強先行指標。
  - 整合最新外銷訂單總額（億美元）、年增率、累計前 10 月額度與連續正成長月份（「連21紅」歷年單月新高）。
  - 提供電子產品（半導體晶片）、資訊通信（AI 伺服器）等貨品細項比重，以及美國、中港、歐洲、東協主要接單市場佔比。
  - 研究工具箱回測證實：外銷訂單年增率與台股走勢呈現高達 $r = 0.88$ 的極強正相關！

### 4. 🚦 國發會景氣對策信號（Taiwan NDC Business Indicators）
* **國家發展委員會官方即時發布**：
  - 追蹤台灣景氣綜合判斷分數（9~45 分）與五色燈號（紅燈、黃紅燈、綠燈、黃藍燈、藍燈）。
  - 歷史 24 個月燈號軌跡圖，節點顏色即時反映當月景氣熱度，並同步疊加台股加權指數。
  - 動態解析 9 大子構成項目（貨幣機構存款、股價指數、工業生產、海關出口、機械設備進口等）個別燈號與得分貢獻。

### 5. ⚖️ 美股股權風險溢價（Equity Risk Premium, ERP）股債性價比儀表
* **計量公式**：
  $$\text{ERP} = \text{標普 500 盈利殖利率 } \left(\frac{1}{\text{Forward P/E}}\right) - \text{美國 10 年期公債殖利率 (^TNX)}$$
* **資產配置決策**：
  - 過去 24 個月歷史走勢與 $0\%$ 股債均衡線。
  - 當 $\text{ERP} < 0\%$（負值倒掛）時，代表投資股票承擔之風險補償低於躺平買無風險公債，固定收益債券性價比顯著提高；當 $\text{ERP} > 1.5\%$ 時股票極具長線超額報酬吸引力。

### 6. 🌐 跨市場 8×8 資產相關性熱力矩陣（Cross-Market Correlation Heatmap）
* **涵蓋 8 大核心跨資產類別**：
  1. 台股加權指數 (`^TWII`)
  2. 標普 500 (`^GSPC`)
  3. 那斯達克 (`^IXIC`)
  4. 美債 10 年期殖利率 (`^TNX`)
  5. 美元指數 (`DX-Y.NYB`)
  6. 美元/台幣匯率 (`USDTWD=X`)
  7. 黃金期貨 (`GC=F`)
  8. WTI 輕原油期貨 (`CL=F`)
* **動態切換**：
  - 支援「月報酬率相關（Returns Correlation）」與「價格水準相關（Level Correlation）」。
  - 支援「24 個月」與「12 個月」滾動觀測期。
  - **點擊任一配對格子**：即刻於下方展開「雙資產深度連動剖析」，自動生成總經機制解讀、歷史情境驗證與多元資產配置建議。

### 7. 🗺️ Finviz 風格市場板塊熱力圖（Market Heatmap Treemap）
* **美股 S&P 500 熱力圖（37 檔代表性權值股）**：依市值權重與產業板塊（科技、通訊、可選消費、金融、醫療等）繪製。
* **台股權值股熱力圖（28 檔權值龍頭）**：涵蓋台積電、聯發科、鴻海、台達電、廣達、富邦金、國泰金等。
* **多維度天期切換**：支援一日表現 (1D)、一週表現 (1W) 及今年以來 (YTD) 色階漸層切換。

### 8. 🧰 雙軸研究工具箱、自編基本面指數與策略回測器
* **雙軸疊加工具**：支援 40+ 組已驗證官方歷史序列任意兩兩配對，提供 MA3 / MA6 / MA12 移動平均線與 Z-Score 標準化計算，並可一鍵匯出完整歷史 CSV。
* **經典預設圖組**：
  - `台灣 M1B vs 台股 TAIEX`
  - `M1B-M2 剪刀差 vs 台股`
  - `國發會景氣燈號 vs 台股`
  - `外銷訂單年增率 vs 台股 TAIEX`
  - `美股 ERP 溢價 vs S&P 500`
  - `Fed 淨流動性 vs S&P 500`
  - `薩姆規則 vs 10Y-2Y 利差`
  - `美債 10Y vs S&P 500`
  - `美國 M2 年增率 vs 黃金`
* **策略訊號回測器**：自訂做多門檻（大於／小於），模擬過去 24 個月策略累積報酬率 vs 買入持有基準。

---

## 🛡️ 官方資料源與防錯驗證架構

本專案採嚴格的**零模擬（Zero-Mock）防錯機制**，任何指標皆須通過資料品質檢查（Data Quality Gates），杜絕缺漏或失真數據破壞決策品質：

| 指標類別 | 官方資料來源機構 | 取得頻率 | 容錯與驗證機制 |
| :--- | :--- | :---: | :--- |
| **Fed 淨流動性 / 美國總經** | 聖路易斯聯準會 (FRED) | 日 / 週 / 月 | 雙重重試、TLS 封包模擬、自動備份降級保護 |
| **薩姆規則與公債利差** | 聖路易斯聯準會 (FRED) | 日 / 月 | `SAHMREALTIME`、`T10Y2Y`、`T10Y3M` 官方核實 |
| **台灣 M1B / M2 剪刀差** | 中華民國中央銀行 (CBC) | 月頻 | CBC 官方統計 API、剪刀差自動運算 |
| **台灣外銷訂單統計** | 中華民國經濟部統計處 (MOEA) | 月頻 | MOEA 官方核實序列、貨品與地區結構分析 |
| **景氣對策信號燈號** | 中華民國國家發展委員會 (NDC) | 月頻 | 官方 CSRF 會話爬蟲、9 大子項目完整校驗 |
| **跨國年度總經指標** | 世界銀行 (World Bank) | 年頻 | 美、歐、中、日 12/12 完整性檢查門檻 |
| **台股當日收盤與漲跌** | 台灣證券交易所 (TWSE) | 交易日收盤 | 28 檔權值股完整覆蓋檢驗 |
| **美股大盤與跨市場資產** | Yahoo Finance (延遲日線) | 交易日收盤 | 37 檔美股熱力圖 + 8 大類資產日線收盤 |
| **全球外匯基準與比特幣** | 歐洲央行 (ECB) / CoinGecko | 即時 / 日線 | USD/TWD、EUR/USD、USD/JPY、BTC 現貨價 |

---

## ⚙️ 雲端自動化更新流程 (GitHub Actions)

專案內建 `.github/workflows/update.yml`，依據全球金融市場交易時段每日自動觸發：
1. **台股收盤更新**：台灣時間每日 14:30（UTC 06:30）抓取 TWSE 台股權值股收盤價與台灣官方最新發布月報。
2. **美股收盤更新**：台灣時間次日清晨 06:30（UTC 22:30）抓取美股收盤價、美債殖利率、FRED 淨流動性與最新外匯商品收盤。
3. **資料防錯門檻（Data Quality Gate）**：
   - 跨國總經資料必須達到 12/12 滿額。
   - FRED 必要總經指標至少達到 8/10 覆蓋。
   - 台股熱力圖須達 28/28、美股熱力圖須達 37/37。
   - 檢查不通過時**自動保留前一份有效資料包**，絕不發布殘缺或錯誤數據。

---

## 🛠️ 本地開發與手動維護

### 環境需求
- Python 3.10+
- 現代瀏覽器（Chrome / Safari / Edge / Firefox）

### 快速開始
```bash
# 1. 複製專案
git clone https://github.com/MasonHung8888/macropulse.git
cd macropulse

# 2. 建立虛擬環境並安裝依賴
python3 -m venv venv
source venv/bin/activate
pip install yfinance curl_cffi

# 3. 手動執行總經資料更新引擎
python update_macro_data.py

# 4. 本地預覽網頁
python -m http.server 8000
# 瀏覽器開啟 http://localhost:8000
```

---

## 📄 免責聲明 (Disclaimer)

1. **MacroPulse** 所有數據均來自各國央行、政府統計部會與公開金融資訊平台，僅供學術研究、總經分析與個人資產配置參考，**不構成任何形式的投資買賣建議或獲利保證**。
2. 市場價格屬於交易所延遲日線（Delayed Daily Close），非證券商或期貨商逐筆極速報價，盤中實質交易請以合格券商行情為準。
3. 任何依據本平台資訊所做出之投資決策，風險由投資人自行全權承擔。
