# MacroPulse 總經決策雷達 (GitHub Pages 自動更新版)

## 部署步驟
1. 將本資料夾內的所有檔案（包含隱藏資料夾 `.github/workflows/update.yml`）上傳至公開的 GitHub Repository 根目錄。
2. 前往 `Settings -> Actions -> General`，將 `Workflow permissions` 設為 **Read and write permissions** 並儲存。
3. 前往 `Settings -> Pages`，將 `Source` 設為 `Deploy from a branch`，Branch 選 `main` / `/ (root)`。
4. 前往 `Actions` 分頁，點選 `Update Macro & Market Data` → `Run workflow` 立即執行第一次抓數，之後即會每日定時自動更新。
