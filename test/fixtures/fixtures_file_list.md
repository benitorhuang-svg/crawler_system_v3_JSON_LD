# 測試固定裝置 (Fixtures) 目錄進出管理登記簿

本目錄存放用於測試的靜態資料樣本。

## 檔案與子目錄清單

### 1. Data (核心樣本資料)
| 檔案名稱 | 功能說明 |
| :--- | :--- |
| `data/104_sample_104_job.json` | 104 職缺 JSON-LD 樣本。 |
| `data/1111_sample_1111_job.json` | 1111 職缺 JSON-LD 樣本。 |
| `data/native_geo_sample.json` | 包含原生經緯度的 JSON-LD 樣本。 |

### 2. Adversarial (對抗性樣本)
| 檔案名稱 | 功能說明 |
| :--- | :--- |
| `data/adversarial/stress_sample.json` | 包含極端字元、無效編碼或注入威脅的壓力測試樣本。 |

### 3. Failed Samples (失敗樣本存檔)
位於 `data/failed_samples/`，自動收集系統運行中無法解析或驗證失敗的數據。
(檔案格式：`fail_[type]_[platform]_[id]_[timestamp].json`)
