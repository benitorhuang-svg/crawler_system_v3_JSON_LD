# Crawler System V3 文件索引 (Documentation Index)

> [!NOTE]
> 本目錄包含專案的所有核心規範、架構設計與維運指南。所有文件皆遵循 **SDD (Specification-Driven Development)** 標準。

## 核心規範 (Core Specifications)

- **[SDLC 流程總綱](../.rule/SDD_SDLC_SPEC.md)**: 專案開發流程、版本管理與根目錄規範的全域總綱。
- **[開發標準與結構](SDD_STANDARDS.md)**: 詳細的命名、型別、註釋規範，以及專案目錄與組件結構說明。
- **[資料庫綱要](DATABASE_SCHEMA.md)**: tb_jobs, tb_companies 等 4 表架構的詳細欄位定義。

## 架構與實作 (Architecture & Implementation)

- **[系統架構詳解](SDD_ARCHITECTURE.md)**: 包含核心序列圖、資料流向 (Data Flow) 與 AI 隔離機制。
- **[API 與錯誤碼](SDD_API_SPEC.md)**: Service 介面定義、HTTP 狀態碼及內部日誌標記建議。
- **[程式碼範例](SDD_CODE_EXAMPLES.md)**: 提供快速開發新平台適配器與手動偵錯的 Code Snippets。

## 維運與指南 (Ops & Guides)

- **[測試與驗收指南](TESTING_GUIDE.md)**: 說明如何執行回歸測試、基準測試及日常維運指令。
- **[測試進出管理登記簿](../test/test_file_list.md)**: 基於 SDD 規範的測試檔案全清單與層級導覽。
- **[演進藍圖](ROADMAP.md)**: 記錄已達成目標與未來 AI 自動化發展方向。

## 範本與歷史紀錄 (Templates & History)

- **[提案範本](PROPOSAL_TEMPLATE.md)**: 用於提交新功能或架構變更建議的 Markdown 模板。
- **[歷史：數據合規修復](HISTORICAL_COMPLIANCE_FIXES.md)**: 記錄 2026-01-26 的資料核查與優化過程。
- **[歷史：系統一致性](HISTORICAL_SYSTEM_CONSISTENCY.md)**: 早期關於系統一致性的優化提案。

---
*最後更新日期：2026-01-28*
