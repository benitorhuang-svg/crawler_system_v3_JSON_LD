# Crawler System v3: Advanced Distributed Job Intelligence

**Crawler System v3** 是一款高效能、分散式且遵循 **SDD (規格驅動開發)** 的職缺數據採集系統。系統專注於提取 **schema.org/JobPosting** 標準的 **JSON-LD** 結構化數據，並具備強大的數據驗證閘口與自適應抗封鎖能力。

---

## 🌟 核心優勢 (Key Features)

- **規格驅動開發 (SDD)**：以數據規格為中心。所有數據在入庫前必須通過 `SchemaValidator` 的嚴格校驗。
- **結構化提取 (JSON-LD)**：直接解析網頁內的 JSON-LD 標籤，免除 CSS Selector 頻繁失效的困擾。
- **自適應抗封鎖引擎**：動態限流與智慧代理冷卻。
- **數據防污染**：區分原生數據與 AI 備援數據，防範爻覺。
- **高效能非同步任務 (Taskiq)**：比 Celery 更好的 `asyncio` 整合。
- **全方位觀測性**：Prometheus 指標與 FastAPI 健康檢查。
- **地理座標優化**：精準提取 Google Maps 座標並進行 OSM 補全。

---

## 🏛️ 系統架構 (System Architecture)

```
crawler_system_v3_JSON_LD/
├── core/
│   ├── adapters/          # 5大平台適配器 (JSON-LD 提取器)
│   ├── services/          # 爬蟲、出口、健康檢查服務
│   ├── enrichment/        # AI 增強層 (geocoder, skill_extractor)
│   ├── infra/             # 基礎設施 (config, database, metrics)
│   └── schemas/           # SSOT 數據規格
├── test/                  # 單元 & 端到端測試
├── docs/                  # 規格與路線圖
├── scripts/               # 批量腳本與工具
└── docker-compose.yml     # 7 個服務容器編排
```

---

## 🚀 快速上手 (Quick Start)

### 1. 啟動服務

```bash
docker compose up -d --build
```

### 2. 訪問監控

- **phpMyAdmin SQL 管理**: [http://localhost:8080](http://localhost:8080) (root/root)
- **Prometheus 指標**: [http://localhost:8000/metrics](http://localhost:8000/metrics)

### 3. 執行測試

```bash
# 小樣本測試 (每平台 10 筆)
uv run python scripts/sample_test_sql.py
```

---

## 📋 核心命令

| 任務 | 指令 |
|------|------|
| 資料庫初始化 | `PYTHONPATH=. uv run main.py init-db` |
| 執行爬蟲采樣 | `uv run python scripts/sample_test_sql.py` |
| 啟動任務 Worker | `docker compose up worker` |

---

## 📚 文檔導航

- **[SDD_STANDARDS.md](docs/SDD_STANDARDS.md)**: 開發與數據規範
- **[walkthrough_test_plan.md](walkthrough_test_plan.md)**: 端到端測試計畫
- **[ROADMAP.md](docs/ROADMAP.md)**: 功能路線圖

---

## 📄 授權協議

本專案基於 **MIT License** 授權發佈。
