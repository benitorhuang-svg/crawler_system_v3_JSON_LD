# SDD 變更提案模板 (Change Proposal Template)

**提案編號**: `YYYYMMDD-FEATURE-NAME`
**申請日期**: `YYYY-MM-DD`
**目的**: 描述為什麼需要這次變更 (例如：增加新平台、修改薪資枚舉)。

---

## 1. 影響範圍評估 (Impact Analysis)

### ⚠️ Affected Specs (受影響的規格)
- [ ] `core/schemas/job_schema.json`
- [ ] `core/schemas/company_schema.json`
- [ ] 其他: ________________

### 🛠️ Affected Code (受影響的代碼)
- [ ] `core/adapters/` (列出具體 Adapter)
- [ ] `core/infra/database.py` (資料庫層)
- [ ] `core/services/crawl_service.py` (核心流程)

---

## 2. 變更內容描述 (Description of Changes)

### 規格層級 (Spec Level)
- [詳細描述 JSON 結構的異動]

### 實作層級 (Code Level)
- [詳細描述代碼邏輯的調整]

---

## 3. 驗證計畫 (Validation Plan)
- [ ] 已備妥新的測試樣本於 `test/unit/data/`
- [ ] 單元測試通過情況說明
- [ ] 回歸測試範圍 (是否有破壞舊有平台？)
