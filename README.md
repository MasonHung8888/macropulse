# MacroPulse 總經決策雷達 (GitHub Pages 自動更新版)

## 部署步驟
1. 將本資料夾內的所有檔案（包含隱藏資料夾 `.github/workflows/update.yml`）上傳至公開的 GitHub Repository 根目錄。
2. 前往 `Settings -> Actions -> General`，將 `Workflow permissions` 設為 **Read and write permissions** 並儲存。
3. 前往 `Settings -> Pages`，將 `Source` 設為 `Deploy from a branch`，Branch 選 `main` / `/ (root)`。
4. 前往 `Actions` 分頁，點選 `Update Macro & Market Data` → `Run workflow` 立即執行第一次抓數，之後會依排程自動更新。

## 資料更新說明

- 大盤、商品與美股熱力圖使用 Yahoo Finance 最新可用日線，可能延遲，並非券商逐筆即時行情。
- 台股當日收盤與漲跌取自 TWSE；M1B、M2 取自中央銀行。
- 每次更新會先檢查必要指標、資料日期與熱力圖覆蓋率；檢查失敗時不會覆蓋上一份有效資料。
- 網頁的「重新整理」只會重新載入最新資料包，不會把延遲日線誤標成即時價格。
