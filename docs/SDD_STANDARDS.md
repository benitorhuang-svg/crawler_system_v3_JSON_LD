# SDD 開發規範 (Specification-Driven Development Standards)

本文件定義了 `crawler_system_v3_JSON_LD` 專案中，「規格先行」與「規格即源碼 (Spec-as-source)」的深度開發規範。

---

## 壹、大綱 (Principles & Philosophy)

### 1. 核心哲學：規格即源碼 (Spec-as-source)
- **單一真理來源 (SSOT)**：規格不再是靜態的說明書，而是系統邏輯的**啟動源**。
- **架構驅動**：代碼應從規格中推導，例如資料庫 Schema、驗證邏輯、DTO (Data Transfer Object) 應與 Pydantic Model 保持 1:1 的強類型同步。
- **設計保證 (By-Design)**：所有錯誤處理與自癒邏輯必須有對應的規格描述，禁止在代碼中存在「隱含」的數據假設。

### 2. 開發哲學：防禦性工程
- **零假設 (Zero Assumption)**：對外部數據平台（104, 1111 等）抱持不信任態度，所有數據必須通過規格過濾器。
- **失敗可感知**：任何偏離規格的行為必須被捕獲、數據化並轉錄為 `sdd_data_issue` 日誌。

### 3. 工作日誌與 Issue 規範 (Issue Logging Spec)
- **非同步修復**：當發生「代碼失效」（如解析器無法提取、Geocoding 失敗）時，系統不應終止，而是拋出帶有 `sdd_data_issue` 標籤的日誌。
- **日誌格式**：必須包含 `type`, `job_id`, `original_data` 以及 `note`。
- **處理流**：日誌日後由開發者或規格自動化工具提取，作為更新 Adapter 或更新詞庫的依據。

---

## 貳、架構 (System Architecture & Data Flow)

### 1. 規格即源碼流向 (Spec-as-source Data Flow)
- **規格注入**：系統啟動時，`core/schemas/` 定義的 Pydantic Model 自動作為系統行為的真理來源。
- **提取 -> 驗證 -> 存儲**：數據流入必須通過 Validator 的規格牆。
- **鏈路規約**：`JSON-LD Sample` -> `Adapter` -> `JobPydantic` -> `SQL Tables`。

### 2. 數據獲取階層 (Data Extraction Hierarchy)
系統遵循分層提取規格，確保效率與質量的平衡：
- **L1 - 原生結構化 (JSON-LD)**：第一優先級。直接映射至 Schema.org 規格。
- **L2 - AI 語意補完 (Ollama)**：當 L1 缺失核心數據（如薪資區間）時，驅動 AI 進行非結構化文本轉規格化輸出。
- **L3 - 外部富化/渲染 (Services)**：整合 BrowserFetcher (SPA 渲染), Geocoding, NLP 標籤，對規格定義的擴展地圖進行填充。

### 3. 資料持久化與一致性
- **冪等性保障**：系統執行 `ON DUPLICATE KEY UPDATE` 時，必須強制刷新 `updated_at` 欄位為目前時間。
- **唯一鍵映射**：優先使用平台 `source_id` 作為唯一索引，確保跨平台職缺不重複。

---

## 參、細枝 (Technical Implementation Rules)

### 1. 命名規範與資料型別 (Naming & Types)
- **格式規範**：統一採用 `snake_case` (欄位) 與 `PascalCase` (類類/模型)。
- **精確型別**：
    - 座標：`float` (6 位小數)。
    - 金額：`int` (不允許 float 以避免精度丟失)。
    - 平台宣告：`SourcePlatform` 枚舉。

### 2. 數據提取與轉型標準 (Extraction Standards)
- **國家代碼**：所有台灣地區職缺，`addressCountry` 必須統一轉換為 `"TW"`。
- **日期格式**：所有日期欄位必須通過 `DateParser.parse_iso_date` 轉換為 `YYYY-MM-DD` 格式。
- **薪資解析**：必須使用 `SalaryParser` 處理各種非標數字（如「萬」、「億」、「面議」）。
- **公司資訊強化**：若 JSON-LD 缺乏公司細節（資本額、員工人數），各平台 Adapter 必須實作 L1.5 的 `BeautifulSoup` 補丁邏輯。
- **反幻覺原則 (Anti-Hallucination)**：
    - **顯式空值**：遇見「暫不公開」等明確回避字眼，必須強制映射為 `NULL`，禁止對其文本進行模糊解析。
    - **標籤優先**：優先匹配平台標記的結構化欄位，嚴禁使用全文正則搜索回退 (Fallback) 導致資料污染。
- **地址清洗標準**：
    - **編碼移除**：必須執行 `_clean_id_noise` 以移除平台內部類別編碼 (如 `no=...`)。
    - **雜訊截斷**：設定 Stop Words 以截斷地址後的 UI 雜訊（如「薪資內容」、「上班時段」）。
    - **地址標準格式化**：透過 `_standardize_taiwan_address_format` 正向清理。

### 3. 註釋與文件規範 (Documentation & Comments)
- **檔案標頭**：每個檔案開頭必須以 docstring (`""" ... """`) 描述其功能、模組位置與主要入口。
- **繁體中文註釋**：所有代碼註釋、docstring 與日誌訊息必須使用 **繁體中文**。
- **一致性**：確保所有包結構中具備 `__init__.py` 且包含導出說明。


### 4. 檔案組織與工作區潔癖 (File Organization & Workspace Hygiene)
- **根目錄整潔**：根目錄僅允許保留入口文件 (`main.py`)、配置 (`Makefile`, `Dockerfile`, `*.toml`, `.env*`) 與文檔。
- **測試歸位**：
    - `test/sdd/`：規格驗證層 (Schema 檢查、命名規範)。
    - `test/unit/`：單元功能層 (Adapters, Parsers, Enrichers)。
    - `test/system/`：系統整合層 (Flows, Infra, BrowserFetcher)。
- **腳本歸位**：所有一次性、維運或偵錯腳本必須移至 `test/scripts/`，禁止散落在專案根目錄。
- **資料歸位**：測試樣本必須存放在 `test/fixtures/data/`。
- **無垃圾檔案**：嚴禁提交 `*.identifier` 或 IDE 生成的臨時檔案。

### 5. 套件管理 (Package Management)
- **唯一工具**：強制使用 `uv` 作為專案套件管理器。
- **依賴鎖定**：必須提交 `uv.lock` 以確保環境一致性。
- **執行指令**：所有 Python 指令請透過 `uv run` 執行 (例如 `uv run main.py`)，禁止直接呼叫 `python` 或 `pip`。

---

## 肆、流程樣板 (Workflow Templates)

### 1. 代碼修正流程 (Code Rectification Workflow)
當功能有變動時，開發者必須遵循以下順序：
1. **更新規格**：首先修改 `.rule/SDD_SDLC_SPEC.md`（高層級流程）或相關專題文件。
2. **更新架構文檔**：修改本文件 (或 `docs/DATABASE_SCHEMA.md`) 以反映變更。
3. **實現代碼修正**：進行實際的代碼修改。
4. **驗證與存檔**：執行 `test/` 目錄下的驗證腳本，並更新 `walkthrough.md`。

---

## 伍、分項 (Functional Module Specifications)

### 1. 座標優先級 (Geocoding Priority)
- **Tier 1 (原生)**：優先獲取 `jobLocation.geo`。
- **Tier 2 (清洗)**：移除不友好的地址後綴（如 3F-1, A室）。
- **Tier 3 (後備)**：呼叫快取化的 OSM/Nominatim 服務。

### 2. 限流隔離 (Throttling Isolation)
- 單一平台的 429/403 應只導致該平台進入 `Cooling` 狀態，不應連累其他平台。
- 隔離參數應持久化於 Redis 鍵值對中。

---

> _"In Spec We Trust, code follows as truth."_

---

## 六、專案結構與組件 (Structure & Components)

### 1. 目錄結構公約

```
├── core/                   # 核心邏輯層
│   ├── adapters/           # 平台適配器 (Mapping)
│   ├── services/           # 業務服務 (Crawl, Throttler)
│   ├── schemas/            # 數據契約 (Validator)
│   ├── infra/              # 基礎設施 (DB, SSOT Models)
│   ├── enrichment/         # 數據增強 (Ollama, Geocoder)
│   ├── utils/              # 公用工具 (Parsers, Logger)
│   ├── celery_app.py       # Celery 進入點
│   ├── taskiq_app.py       # Taskiq 進入點
│   └── tasks.py            # 任務定義
├── test/                   # 維運與驗收
│   ├── sdd/                # 規格驗證
│   ├── unit/               # 單元功能
│   ├── system/             # 系統整合
│   ├── scripts/            # 維運指令 (DB Init, Regression)
│   └── fixtures/data/      # 真理來源 (Ground Truth)
├── docs/                   # 專案文檔 (README.md Index)
├── scripts/                # 開發與驗證腳本 (E2E Tests)
└── main.py                 # 程式進入點
```

### 2. 核心組件說明

| 組件 | 關鍵檔案 | 功能說明 |
| :--- | :--- | :--- |
| **基礎設施** | `database.py`, `schemas.py` | 管理連線池與 Pydantic SSOT 模型。 |
| **服務層** | `crawl_service.py` | 協調爬取、提取與持久化流程。 |
| **適配器** | `jsonld_adapter.py` | 定義 JSON-LD 抽象映射標準。 |
| **數據增強** | `ollama_client.py` | 負責 L2 語意提取與自癒。 |
| **類別標準化**| `standard_category_service.py` | 管理平台類別與系統標準類別之映射（含 YAML 匯入）。 |

### 3. 依賴管理 (uv sync)

在 Dockerfile 中使用 `uv sync --frozen --no-install-project --no-dev`：
- **--frozen**: 強制鎖定版本，確保生產與開發環境 100% 一致。
- **--no-install-project**: 避免將爬蟲程式封裝成系統套件，減少建置開銷。
- **--no-dev**: 排除測試工具，縮小映像檔體積並提高安全性。

