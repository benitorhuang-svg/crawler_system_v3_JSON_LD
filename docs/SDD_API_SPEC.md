# SDD API 規格與錯誤碼 (API & Error Codes)

> [!NOTE]
> 本文件詳述專案內部的核心介面定義、Service 簽名、以及系統級錯誤碼處理機制。

---

## 1. 核心介面 (Core Interfaces)

### 1.1 `JsonLdAdapter` (抽象基底類別)

位於 `core/adapters/jsonld_adapter.py`。所有平台適配器必須實作以下介面：

| 方法 / 屬性 | 回傳類型 | 說明 |
| :--- | :--- | :--- |
| `platform` | `SourcePlatform` | 平台的 Enum 識別碼 (如 `platform_104`) |
| `get_url(ld, fallback)` | `str` | 從 JSON-LD 提取職缺網址，優先使用 canonical URL |
| `get_source_id(ld, url)` | `str` | 提取平台原始 ID (Unique Key) |
| `get_salary(ld)` | `dict` | 提取薪資資訊，包含 `min`, `max`, `type`, `text` |
| `get_education(ld)` | `str` | 提取學歷要求文字 |
| `get_experience(ld)` | `int` | 提取最小經驗年數要求 |
| `get_job_type(ld)` | `str` | 提取工作類型 (全職、兼職等) |
| `get_company_name(ld)` | `str` | 提取公司名稱 |
| `get_company_source_id(ld)`| `str` | 提取公司在平台的原始 ID |

### 1.2 `CrawlService` (業務邏輯層)

位於 `core/services/crawl_service.py`。負責高層級的流程編排。

| 方法 | 參數 | 職職 |
| :--- | :--- | :--- |
| `run_platform` | `platform, max_jobs, ...` | 執行指定平台的完整爬取流程 (探索 -> 抓取 -> 清洗 -> 存儲) |
| `process_url` | `url, platform, client` | 抓取單一網址，執行 JSON-LD 提取、驗證與自癒 |
| `heal_extraction` | `html, platform, title` | **自癒機制**：當 L1 失敗時，調用 Ollama 進行 L2 語意提取 |
| `enrich_company` | `company, platform, client`| 前往公司主頁抓取資本額、員工人數等詳細資訊 |

---

## 2. 錯誤碼處理機制 (Error Handling)

系統將錯誤分為三類：**網路層 (HTTP)**、**解析層 (Extraction)** 與 **資料層 (Validation)**。

### 2.1 HTTP 狀態碼處理

| 狀態碼 | 內部定義 | 處理策略 |
| :--- | :--- | :--- |
| **403 / 401** | `BLOCK_DETECTED` | 立即切換至 `BrowserFetcher` (Playwright) 繞過 |
| **429** | `RATE_LIMITED` | 觸發 Exponential Backoff (2^n) 延遲重試 |
| **404** | `NOT_FOUND` | 標記為失效職缺，停止後續處理 |
| **5xx** | `SERVER_ERROR` | 重試 3 次後放棄，記錄至 Health Monitor |

### 2.2 系統內部錯誤碼 (Logging Tags)

在 `structlog` 中使用的標準化錯誤識別碼：

| 錯誤標籤 | 描述 | 觸發位置 |
| :--- | :--- | :--- |
| `sdd_validation_failed` | 資料不符合 Schema 契約 (SSOT 失敗) | `SchemaValidator` |
| `ai_hallucination_detected`| AI 提取出的標題與原網頁標題差異過大 | `heal_extraction` |
| `geocoding_failure` | 通過地址無法取得經緯度 | `Geocoder` |
| `structural_change_html` | 偵測到網頁結構變更 (找不到核心節點) | `CrawlService` |
| `ai_threshold_reached` | AI 連續失敗次數過高，進入隔離狀態 | `CrawlService` |

---

## 3. 日誌與監控 (Logging Context)

執行核心任務時，日誌**必須**包含以下 Context 鍵值：

| 鍵名 (Key) | 說明 | 範例 |
| :--- | :--- | :--- |
| `platform` | 來源平台 | `104` |
| `url` | 處理中的網址 | `https://www.104.com.tw/...` |
| `job_id` | 內部或原始 ID | `123456` |
| `latency_ms` | 執行耗時 | `1250` |
| `data_layer` | 資料來源層級 | `L1`, `L2`, `L3`, `L1_FAILED_L2` |

---

## 4. 自癒機制閾值 (Healing Thresholds)

| 參數 | 數值 | 說明 |
| :--- | :--- | :--- |
| `AI_FAILURE_LIMIT` | 5 | 連續提取失敗達此數值，AI 模組進入隔離期 |
| `AI_ISOLATION_WINDOW`| 3600s | AI 隔離持續時間 (1 小時) |
| `SIMILARITY_THRESHOLD`| 0.3 | AI 提取標題與原標題的相似度低於此值則視為幻覺 (L2 失敗) |

---

> [!TIP]
> 當遇到 `sdd_validation_failed` 時，系統會自動在 `test/unit/debug/change_detection/` 儲存 HTML 樣本供開發者手動檢視網頁結構是否變更。
