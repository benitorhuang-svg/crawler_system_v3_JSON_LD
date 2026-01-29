# 測試總目錄進出管理登記簿

本目錄存放專案的所有測試相關檔案，包含規範驗證、單元測試、系統測試、樣本資料及維護腳本。

## 目錄結構

| 目錄 | 功能說明 |
| :--- | :--- |
| `sdd/` | [SDD 規範測試](sdd/sdd_file_list.md) - 驗證專案結構與 SSOT 模型同步。 |
| `unit/` | [單元測試](unit/unit_file_list.md) - 驗證獨立組件邏輯。 |
| `system/` | [系統測試](system/system_file_list.md) - 驗證基礎設施與全流程整合。 |
| `fixtures/` | [測試樣本](fixtures/fixtures_file_list.md) - 存放靜態資料與失敗樣本。 |
| `scripts/` | [維護腳本](scripts/scripts_file_list.md) - 資料庫管理與資料檢查工具。 |

## 維護指南

1. **新增檔案**：若在子目錄中新增測試檔案，請同步更新該目錄第一層的 `*_file_list.md` 登記簿。
2. **移除檔案**：若移除檔案，請從對應的登記簿中刪除。
3. **更名檔案**：請同步更新登記簿中的檔名與說明。

---
*詳細檔案清單請參閱各子目錄之 `*_file_list.md`。*
