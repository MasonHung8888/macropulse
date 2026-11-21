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

### 3. 🎯 聯準會降息路徑期貨定價（CME FedWatch & Fed Funds Futures Rate Path）
* **芝加哥商業交易所 (CME) 30 天聯邦基金期貨 (`ZQ`) 即時定價**：
  - 合約結算公式：$100 - \text{結算月平均有效利率}$，由全球機構真實資金交易倒推對未來每次 FOMC 政策利率之無偏定價。
  - 整合 FRED 官方政策目標區間上限 (`DFEDTARU`)、下限 (`DFEDTARL`) 與有效利率 (`FEDFUNDS` / `DFF`)。
  - 即時計算下次 FOMC 會議按兵不動機率、降息 1 碼機率、升息機率，以及期貨市場定價之「終端利率高點（Terminal Rate）」。
  - 雙軸路徑圖：視覺化過去 18 個月聯邦基金利率實績與未來半年的期貨隱含利率預期曲線，清晰辨識 Higher for Longer 或寬鬆週期節奏。

### 4. 🧭 恐慌與貪婪綜合指數（Fear & Greed Sentiment Radar）
* **對齊 CNN 恐慌貪婪指數架構之 6 大客觀量化支柱**：
  1. **市場動能 (Market Momentum)**：S&P 500 現價距 125 日移動平均線 (125-DMA) 乖離率。
  2. **市場波動率 (Market Volatility)**：CBOE VIX 恐慌指數現值與 50 日均線乖離。
  3. **避險資產需求 (Safe Haven Demand)**：過去 20 個交易日 美股 (`^GSPC`) vs 長天期美債 (`TLT`) 相對超額報酬。
  4. **垃圾債信用利差 (Junk Bond Demand)**：美林高收益債期權調整利差 (FRED `BAMLH0A0HYM2`)，衡量信用違約恐慌。
  5. **選擇權偏度與尾端避險 (Option Skew)**：CBOE SKEW 偏度指數，偵測大機構對極端黑天鵝暴跌之避險買盤。
  6. **均線趨勢強度 (Stock Price Trend)**：S&P 500 50 日均線 vs 200 日年線黃金交叉／死亡交叉多空結構。
* **評分區間與五色指標儀表盤**：
  - `0 ~ 25`：極度恐慌（Extreme Fear，逆向超賣左側價值買點）
  - `26 ~ 45`：恐慌（Fear）
  - `46 ~ 55`：中性（Neutral，觀望震盪）
  - `56 ~ 75`：貪婪（Greed）
  - `76 ~ 100`：極度貪婪（Extreme Greed，自滿過熱右側追高風險）
* **視覺化呈現**：具備 5 級五色指針量表、前日／前週／前月歷史對比卡片、6 大因子動態進度條，以及過去 30 個交易日每日情緒走勢圖。

### 5. ⚖️ 巴菲特指標：美股市值 / GDP 估值計（Buffett Indicator）
* **華爾街長線總體估值公認基準**：
  - 由股神華倫·巴菲特（Warren Buffett）於 2001 年在《財富》（Fortune）雜誌提出，被其譽為「衡量任何時刻股市整體估值水準的最佳單一指標」。
  - **分子（美股總市值）**：採用官方 Wilshire 5000 Total Market Index (`^W5000` via Yahoo Finance)，其指數 1 點約等同 10 億美元全美企業市值。
  - **分母（美國名目 GDP）**：採用聖路易斯聯準會 FRED 官方發布之美國名目 GDP（FRED `GDP`，十億美元），以月頻前向填補（ffill）完成時間序列精確對齊。
* **五大估值分級體系**：
  - `< 75%`：**顯著低估**（Significantly Undervalued，極致安全邊際，強烈買進區間）
  - `75% ~ 90%`：**適度低估**（Modestly Undervalued，合理偏低，優質佈局期）
  - `90% ~ 115%`：**合理估值**（Fair Valued，歷史常態均衡定價）
  - `115% ~ 140%`：**適度高估**（Modestly Overvalued，警示偏高，成長溢價擴張）
  - `> 140%`：**顯著高估**（Significantly Overvalued，歷史泡沫警戒線，小心玩火）
* **專業圖表與工具箱連動**：
  - 4 KPI 卡片：最新比率、全美總市值（兆美元）、名目 GDP（兆美元）、一年前同期對比。
  - 雙軸歷史曲線：過去 24 個月比率軌跡圖，疊加 140% 泡沫警戒線與 100% 歷史常態基準線。
  - 整合至「研究工具箱（Research Toolbox）」與「歷史量化回測（Backtest）」，支援與標普 500 或其他總經因子進行跨期交叉檢驗。

### 6. 📉 美國實質利率與平衡通膨率計（US TIPS Real Yield & Breakeven Inflation）
* **金融資產估值的核心引力（Gravity）**：
  - 實質利率代表資本的「真實無風險報酬率」，是現代金融資產定價模型（CAPM）與現金流折現模型（DCF）的最關鍵折現因子。
  - **10 年期 TIPS 實質利率 (`DFII10`)**：美國財政部發行抗通膨公債之市場真實殖利率，當實質利率飆高（> 2.0%）時，高本益比科技股折現壓力急劇升溫。
  - **10 年期名目公債殖利率 (`DGS10`)**：無風險基準殖利率。
  - **10 年期平衡通膨率 (`T10YIE`)**：由名目殖利率扣除 TIPS 實質利率推算之市場隱含長線通膨預期。
* **費雪方程式資產定價拆解**：
  $$\text{名目殖利率} \approx \text{TIPS 實質利率} + \text{平衡通膨率 (Breakeven)}$$
  - 精確辨識美債高殖利率背後的驅動力：是「通膨預期失控」還是「實質資金成本緊縮」。
  - 4 級實質利率量表：`<0%` 深度負利率（流動性狂歡）、`0%~1%` 中性寬鬆、`1%~2%` 緊縮中性、`>2%` 限制性緊縮（估值重力壓制）。
* **四大資產配置影響連動**：
  - 科技成長股（折現率敏感度最高）、黃金與貴金屬（實質利率負相關敏感度）、抗通膨債券 TIPS（實質票息保護）。
  - 研究工具箱提供「TIPS 實質利率 vs 黃金」與「平衡通膨率 vs S&P 500」經典圖組分析。

### 7. 📦 台灣外銷訂單領先指標（Taiwan Export Orders Leading Indicator）
* **經濟部統計處官方權威發布**：
  - 台灣為全球 AI 與半導體硬體製造中樞，國際大廠提前 1~3 個月下單。外銷訂單年增率（YoY）為「台股加權指數 (TAIEX)」獲利成長最強先行指標。
  - 整合最新外銷訂單總額（億美元）、年增率、累計前 10 月額度與連續正成長月份（「連21紅」歷年單月新高）。
  - 提供電子產品（半導體晶片）、資訊通信（AI 伺服器）等貨品細項比重，以及美國、中港、歐洲、東協主要接單市場佔比。
  - 研究工具箱回測證實：外銷訂單年增率與台股走勢呈現高達 $r = 0.88$ 的極強正相關！

### 6. 🚦 國發會景氣對策信號（Taiwan NDC Business Indicators）
* **國家發展委員會官方即時發布**：
  - 追蹤台灣景氣綜合判斷分數（9~45 分）與五色燈號（紅燈、黃紅燈、綠燈、黃藍燈、藍燈）。
  - 歷史 24 個月燈號軌跡圖，節點顏色即時反映當月景氣熱度，並同步疊加台股加權指數。
  - 動態解析 9 大子構成項目（貨幣機構存款、股價指數、工業生產、海關出口、機械設備進口等）個別燈號與得分貢獻。

### 7. ⚖️ 美股股權風險溢價（Equity Risk Premium, ERP）股債性價比儀表
* **計量公式**：
  $$\text{ERP} = \text{標普 500 盈利殖利率 } \left(\frac{1}{\text{Forward P/E}}\right) - \text{美國 10 年期公債殖利率 (^TNX)}$$
* **資產配置決策**：
  - 過去 24 個月歷史走勢與 $0\%$ 股債均衡線。
  - 當 $\text{ERP} < 0\%$（負值倒掛）時，代表投資股票承擔之風險補償低於躺平買無風險公債，固定收益債券性價比顯著提高；當 $\text{ERP} > 1.5\%$ 時股票極具長線超額報酬吸引力。

### 8. 🌐 跨市場 8×8 資產相關性熱力矩陣（Cross-Market Correlation Heatmap）
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

### 9. 🗺️ Finviz 風格市場板塊熱力圖（Market Heatmap Treemap）
* **美股 S&P 500 熱力圖（37 檔代表性權值股）**：依市值權重與產業板塊（科技、通訊、可選消費、金融、醫療等）繪製。
* **台股權值股熱力圖（28 檔權值龍頭）**：涵蓋台積電、聯發科、鴻海、台達電、廣達、富邦金、國泰金等。
* **多維度天期切換**：支援一日表現 (1D)、一週表現 (1W) 及今年以來 (YTD) 色階漸層切換。

### 10. 🧰 雙軸研究工具箱、自編基本面指數與策略回測器
* **雙軸疊加工具**：支援 40+ 組已驗證官方歷史序列任意兩兩配對，提供 MA3 / MA6 / MA12 移動平均線與 Z-Score 標準化計算，並可一鍵匯出完整歷史 CSV。
* **經典預設圖組**：
  - `恐慌貪婪指數 vs S&P 500`
  - `Fed 政策利率 vs 10Y 美債`
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
| **聯準會降息期貨定價** | 芝加哥商業交易所 (CME) / FRED | 日線 / 交易即時 | CBOT `ZQ` 30天聯邦基金期貨結算價倒推隱含路徑 |
| **恐慌與貪婪綜合指數** | FRED ＆ CBOE / S&P 500 | 日線 | 整合 VIX、HY OAS、SKEW、股債超額 6 因子量化 |
| **巴菲特指標估值計** | FRED (GDP) ＆ Yahoo Finance (^W5000) | 月頻 / 季度 | Wilshire 5000 全美總市值對比美國名目 GDP |
| **TIPS 實質利率與平衡通膨率** | 聖路易斯聯準會 (FRED) | 日線 / 月頻 | `DFII10`、`DGS10`、`T10YIE` 費雪方程式分解 |
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
