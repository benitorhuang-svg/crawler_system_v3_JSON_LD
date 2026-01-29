# 維護腳本目錄進出管理登記簿

本目錄存放用於資料庫管理、資料檢查及快速驗證的工具腳本。

## 檔案清單

| 檔案名稱 | 功能說明 |
| :--- | :--- |
| `manage_db.py` | 資料庫管理與初始化工具。 |
| `inspect_data.py` | 資料品質與欄位缺失率檢查工具。 |
| `regression_all_platforms.py` | 全平台回歸測試自動化腳本。 |
| `benchmark_ollama.py` | Ollama 效能基準測試腳本。 |
| `seed_std_categories.py` | 初始化標準類別資料庫（已更新為單一表結構）。 |
| `verify_yaml_import.py` | 驗證從 YAML 匯入類別映射的功能。 |
| `update_jobs_schema.py` | 升級 `tb_jobs` 表結構以支援標準化分類欄位。 |
| `verify_fixes.py` | 驗證特定 Bug 修復。 |
