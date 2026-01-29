# SDD 架構詳解 (System Architecture)

> [!NOTE]
> 本文件深度解析系統內部組件的互動邏輯、資料流動與安全隔離機制。

---

## 1. 核心處理序列 (Core Sequence Diagram)

以下展示 `CrawlService` 處理一個職缺 URL 的完整生命週期：

```mermaid
sequenceDiagram
    participant S as CrawlService
    participant F as BrowserFetcher
    participant E as JsonLdExtractor
    participant A as Adapter
    participant V as SchemaValidator
    participant AI as OllamaClient
    participant STD as StandardCategoryService
    participant DB as Database

    S->>F: 1. Fetch HTML (Retry/Proxy)
    F-->>S: Raw HTML
    S->>E: 2. Extract JSON-LD
    E-->>S: List of Dicts
    S->>A: 3. Map to Pydantic (L1)
    A-->>S: JobPydantic Object
    
    alt L1 Mapping Failed
        S->>AI: 4a. Request AI Healing (L2)
        AI-->>S: Structured Data
        alt AI Success
            S->>A: 4b. Map AI Data
            A-->>S: JobPydantic (L2 Tagged)
        else AI Fail/Timeout
            S->>A: 4c. Minimal Feasible Mapping
            A-->>S: JobPydantic (L1_FAILED_L2 Tagged)
        end
    end

    S->>V: 5. Validate against Schema
    V-->>S: IsValid (True/False)

    alt Validation Pass (L1/L2/L1_FAILED_L2)
        S->>STD: 6. Lookup Standard Category Mappings
        STD-->>S: Std Major/Minor Category
        S->>DB: 7. Save Job & Company (Enriched)
        DB-->>S: Success
    else Validation Fail
        S->>S: Log sdd_validation_failed & Sample HTML
    end
```

---

## 2. 資料流與 SSOT 隔離 (Data Flow)

系統嚴格遵循 **L1 -> L2 -> L3** 的資料增長路徑：

```mermaid
graph TD
    subgraph S1 [外部來源]
        A[平台 104]
        B[平台 1111]
    end

    subgraph S2 [核心處理]
        C[L1: JSON-LD 原生]
        D[L2: AI 語意補完]
    end

    subgraph S3 [資料增強與渲染]
        E[L3: 地理編碼]
        F[L3: 技能提取]
        X[L3: SPA 渲染 BrowserFetcher]
    end

    subgraph S4 [持久化儲存 SSOT]
        G[tb_jobs 主表]
        H[tb_job_locations 座標表]
        I[tb_job_skills 技能表]
        J[tb_category_standardization 映射表]
    end

    A --> C
    B --> C
    C -->|缺失欄位| D
    C --> G
    D --> G
    J -->|映射注入| G
    G --> E
    G --> F
    E --> H
    F --> I
```

---

## 3. AI 隔離保護機制 (AI Sandboxing)

為了防止 Ollama 當機或輸出無意義（幻覺）內容影響系統穩定性，我們實作了**故障隔離器 (Circuit Breaker)**：

| 元件 | 職責 | 觸發條件 |
| :--- | :--- | :--- |
| **相似度檢查** | 防止 AI 產生與頁面無關的標題 | Levenshtein 相似度 < 0.3 |
| **失敗隔離** | 當 AI 連續失敗時暫停調用 | `AI_FAILURE_LIMIT >= 5` |
| **隔離倒數** | 暫停後自動恢復的時間窗口 | 3600 秒 (1 小時) |
| **資源限制** | 確保 AI 不會耗盡主機 CPU | Ollama 運行於獨立 Docker Container |

---

## 4. 部署拓撲 (Deployment Topology)

```mermaid
graph LR
    subgraph Host [主機環境]
        W[Worker: Celery]
        DB[MySQL]
        RE[Redis/Queue]
        OL[Ollama AI]
    end

    subgraph External [外部存取]
        Target[求職網站]
        GeoAPI[OSM Geocoder]
    end

    W --> DB
    W --> RE
    W --> OL
    W --> Target
    W --> GeoAPI
```

---

## 5. 資料一致性與同步 (Linkage Sync)

- **自動關聯**：當職缺資料包含 `company_source_id` 時，系統會自動在存儲時建立與 `tb_companies` 的連結。
- **孤兒職缺**：若職缺無法關聯到已有公司且無法提取公司資訊，則會被記錄至 `tb_data_issues`。
- **更新策略**：主表使用 `ON DUPLICATE KEY UPDATE`，確保座標與技能等增強資訊不會覆蓋 L1/L2 核心資料。

---

## 6. 詳細資料流程 (Detailed Data Flow)

### 6.1 全域處理流程 (Global Flow)

```mermaid
graph TD
    subgraph S1 [Phase 1: Seed Generation]
        FC[fetch_category scripts] -->|API Call| API[Platform Category API]
        API -->|Parse| CDat[Category Data]
        CDat -->|Upsert| DB1[tb_categories]
    end

    subgraph S2 [Phase 2: Discovery & Input]
        DB1 -->|Query Category| DS[DiscoveryService]
        DS -->|Generate URL| SEARCH[Search Page]
        SEARCH -->|Extract & Backup| URLS[Job URLs + Raw JSON]
        URLS -->|Store Metadata| DB3[tb_categories_jobs]
        URLS -->|Queue| MAIN[main.py Coordinator]
    end

    subgraph S4 [Phase 4: SDD Validation & Standardization]
        MAIN -->|Process| VAL{SchemaValidator}
        VAL -->|Fail| SAMP[Change Detection Sample]
        SAMP -->|Isolated AI Heal| AI[Ollama Sandbox]
        AI -->|L2 Success| VAL
        VAL -->|Pass| STD[StandardCategoryService]
        STD -->|Enrich| DB_JOB[tb_jobs]
        AI -->|L2 Fail| FALL[L1_FAILED_L2 Fallback]
        FALL --> DB_JOB
    end
```

### 6.2 資料實體演變 (Data Entity Lifecycle)

- **Category (分類)**：獲取平台內部的分類代碼，作為發現階段的起始種子。
- **Job (職缺)**：由 `JsonLdExtractor`鎖定 `@type: JobPosting` 節點。通過 `_clean_taiwan` 與 `_dedupe_address` 確保符合台灣標準格式。
- **Company (公司)**：從 `JobPosting` 的 `hiringOrganization` 屬性中分離，作為 SSOT。
- **Discovery Link (發現關聯)**：記錄職缺與分類的發現關係，並存儲 `raw_json` 摘要作為追蹤基礎。

### 6.3 關鍵技術實現

- **台灣地址歸一化**：移除贅字（台灣、台灣省）、提取行政區（region/district）、組合去重。
- **Facebook User-Agent**：針對 104 等 SSR 平台，使用 `facebookexternalhit` 取得完整渲染內容，確保 JSON-LD 完整性。
