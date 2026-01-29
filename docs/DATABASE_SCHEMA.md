# 資料庫綱要設計 (V3)

本文件定義了 Crawler System V3 的標準化資料庫架構。本系統採用 **規格即原始碼 (SDD)** 與 **單一真理來源 (SSOT)** 策略：所有的資料表結構皆由 [schemas.py](file:///home/soldier/crawler_system_v3_JSON_LD/core/infra/schemas.py) 中的 Pydantic 模型定義，並透過 `SQLGenerator` 自動同步至 MySQL。

## 核心流程與資料流向 (Data Flow)
1. **種子階段 (Seed)**：獲取平台分類資訊 (`tb_categories`)。
2. **發現階段 (Discovery)**：抓取職缺連結並建立關聯 (`tb_categories_jobs`)。
3. **提取階段 (Extraction - Company)**：提取公司詳情並存入公司表 (`tb_companies`)。
4. **提取階段 (Extraction - Job)**：提取職缺規範化資訊並存入職缺表 (`tb_jobs`)，直接映射平台原始分類系統。
5. **監控階段 (Monitoring)**：記錄爬蟲行為與健康狀況 (`tb_platform_health`)。

## 資料持久化規則 (Persistence Rules)
- **更新追蹤**: 系統在執行 `INSERT ... ON DUPLICATE KEY UPDATE` 時，會強制將 `updated_at` 欄位更新為 `CURRENT_TIMESTAMP`。這確保了 `updated_at` 始終代表該筆資料在資料庫中的**最後同步時間**，而非職缺的發布時間。
- **冪等性**: 所有表皆以 `platform` 與 `source_id` (或其組合) 作為唯一鍵，確保重複爬取時資料能自動覆寫而非產生冗餘紀錄。

---

## 1. 資料表：`tb_categories` (類別定義 - 起點 / SSOT)
存儲各平台定義的職缺類別層級結構。
- **對應模型**: `CategoryPydantic`
- **唯一鍵 (Unique Key)**: `(platform, layer_3_id)`

| 欄位名稱 | 類型 | 描述 |
| :--- | :--- | :--- |
| `idx` | INT (PK) | 系統自增主鍵 |
| `platform` | VARCHAR(50) | 平台來源 (枚舉) |
| `layer_1_id` | VARCHAR(100)| 第一層類別代碼 (例如：IT) |
| `layer_1_name` | VARCHAR(100)| 第一層類別名稱 |
| `layer_2_id` | VARCHAR(100)| 第二層類別代碼 (例如：軟體開發) |
| `layer_2_name` | VARCHAR(100)| 第二層類別名稱 |
| `layer_3_id` | VARCHAR(100)| 第三層類別代碼 (各平台抓取之最小粒度 ID) |
| `layer_3_name` | VARCHAR(100)| 第三層類別名稱 |
| `last_crawled_at` | TIMESTAMP | 上次完成抓取的時間紀錄 |
| `updated_at` | TIMESTAMP | 最後更新時間 |

---

## 2. 資料表：`tb_categories_jobs` (關聯表)
將發現的職缺與類別建立連接。
- **對應模型**: `JobCategoryJunctionPydantic`
- **唯一鍵 (Unique Key)**: `(platform, category_id, job_source_id)`

| 欄位名稱 | 類型 | 描述 |
| :--- | :--- | :--- |
| `idx` | INT (PK) | 系統自增主鍵 |
| `platform` | VARCHAR(50) | 平台來源 |
| `category_id` | VARCHAR(100)| 對應 `tb_categories.layer_3_id` |
| `job_source_id` | VARCHAR(100) | 對應 `tb_jobs.source_id` |
| `job_url` | TEXT | 發現該職缺時使用的 URL |
| `created_at` | TIMESTAMP | 關聯建立時間 |

---

## 3. 資料表：`tb_companies` (公司數據)
- **對應模型**: `CompanyPydantic`
- **唯一鍵 (Unique Key)**: `(platform, source_id)`

| 欄位名稱 | 類型 | 描述 |
| :--- | :--- | :--- |
| `idx` | INT (PK) | 系統自增主鍵 |
| `platform` | VARCHAR(50) | 平台來源 |
| `source_id` | VARCHAR(100) | 平台內部公司唯一 ID |
| `name` | VARCHAR(255) | 公司官方名稱 |
| `company_url` | TEXT | 公司於該平台的介紹頁 URL |
| `company_web` | TEXT | 公司官方網站連結 |
| `address` | TEXT | 公司登記或辦公地址 |
| `capital` | VARCHAR(100) | 實收資本額字串 |
| `employee_count`| VARCHAR(100) | 員工人數規模 |
| `description` | TEXT | 公司簡介與描述 |
| `data_source_layer`| VARCHAR(20) | 數據來源層級 (L1: JSON-LD, L2: Other) |
| `updated_at` | TIMESTAMP | 最後更新時間 |

---

## 4. 資料表：`tb_jobs` (職缺數據)
- **對應模型**: `JobPydantic`
- **唯一鍵 (Unique Key)**: `(platform, source_id)`

| 欄位名稱 | 類型 | 描述 |
| :--- | :--- | :--- |
| `idx` | INT (PK) | 系統自增主鍵 |
| `platform` | VARCHAR(50) | 平台來源 |
| `url` | TEXT | 標準化後的職缺原始 URL |
| `source_id` | VARCHAR(100) | 平台內部職缺唯一 ID |
| `company_source_id`| VARCHAR(100)| 對應 `tb_companies.source_id` |
| `title` | VARCHAR(255) | 職缺職稱 |
| `description` | TEXT | 清洗過後的 HTML/Text 職缺內容 |
| `industry` | VARCHAR(100) | 產業分類 |
| `layer_category_name`| VARCHAR(100)| 系統分類名稱 (層級 3) |
| `job_type` | VARCHAR(50) | 僱用類型 (全職/兼職/實習) |
| `work_hours` | VARCHAR(100) | 上班時段與時數 |
| `salary_currency`| VARCHAR(10) | 薪資貨幣代碼 (預設 TWD) |
| `salary_type` | VARCHAR(20) | 給付週期 (月薪, 年薪...) |
| `salary_text` | VARCHAR(100) | 原始薪資描述文案 |
| `salary_min` | INT | 數值化最低薪資 |
| `salary_max` | INT | 數值化最高薪資 |
| `address_country`| VARCHAR(10) | 工作國家代碼 (預設 TW) |
| `address` | TEXT | 完整工作地址 |
| `region` | VARCHAR(100) | 一級行政區 (縣市) |
| `district` | VARCHAR(100) | 二級行政區 (鄉鎮市區) |
| `experience_min_years`| INT | 最低需求年資 (0 表示不拘) |
| `education_text` | VARCHAR(100)| 教育程度描述 |
| `posted_at` | DATE | 平台發布日期 |
| `valid_through` | DATE | 應徵截止日期 |
| `raw_json` | JSON | 抓取到的原始資料內容 (JSON 字串) |
| `data_source_layer`| VARCHAR(20) | 數據解析來源層級 (L1, L2, L1_FAILED_L2) |
| `updated_at` | TIMESTAMP | 最後更新時間 |

---

## 5. 資料表：`tb_job_locations` (地理座標表)
- **對應模型**: `JobLocationPydantic`
- **唯一鍵 (Unique Key)**: `(platform, job_source_id)`

| 欄位名稱 | 類型 | 描述 |
| :--- | :--- | :--- |
| `platform` | VARCHAR(50) | 平台枚舉值字串 |
| `job_source_id` | VARCHAR(100) | 職缺來源唯一 ID |
| `latitude` | DOUBLE | WGS84 緯度 |
| `longitude` | DOUBLE | WGS84 經度 |
| `formatted_address`| TEXT | 地理編碼標準化後地址 |
| `provider` | VARCHAR(20) | 地理資訊提供者 (NATIVE, OSM, GOOGLE) |
| `updated_at` | TIMESTAMP | 最後更新時間 |

---

## 6. 資料表：`tb_job_skills_extracted` (技能提取表)
- **對應模型**: `JobSkillExtractedPydantic`
- **唯一鍵 (Unique Key)**: `(platform, job_source_id, skill_name)`

| 欄位名稱 | 類型 | 描述 |
| :--- | :--- | :--- |
| `platform` | VARCHAR(50) | 平台枚舉值字串 |
| `job_source_id` | VARCHAR(100) | 職缺來源唯一 ID |
| `skill_name` | VARCHAR(100) | 提取出的技能/關鍵字名稱 |
| `skill_type` | VARCHAR(50) | 技能類型標籤 |
| `confidence_score`| FLOAT | 提取置信度評分 (0.0-1.0) |
| `updated_at` | TIMESTAMP | 最後更新時間 |

---

## 7. 資料表：`tb_platform_health` (監控表)
記錄各平台的 API 調用狀況與解析成功率。
- **對應模型**: `PlatformHealthPydantic`
- **唯一鍵 (Unique Key)**: `(platform)`

| 欄位名稱 | 類型 | 描述 |
| :--- | :--- | :--- |
| `platform` | VARCHAR(50) | (PK) 監控平台對象 |
| `total_requests` | INT | 累計總請求次數 |
| `success_requests` | INT | HTTP 成功次數 |
| `failed_requests` | INT | HTTP 失敗次數 |
| `extraction_success`| INT | 欄位解析成功次數 |
| `extraction_failure`| INT | 欄位解析失敗次數 |
| `avg_latency_ms` | INT | 平均反應延遲 (ms) |
| `last_error` | TEXT | 最後一次遭遇之錯誤摘要 |
| `updated_at` | TIMESTAMP | 紀錄更新時間 |

---

> [!NOTE]
> 座標存儲遵循 **原生優先 (Native-First)** 策略：若平台 JSON-LD 已含座標，則標記為 `NATIVE` 並跳過所有外部請求，極大化數據完整性同時減輕系統負載。
