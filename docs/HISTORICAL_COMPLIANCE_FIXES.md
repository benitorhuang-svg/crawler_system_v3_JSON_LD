# SDD 變更提案 (20260126-DATA-COMPLIANCE)

**提案編號**: `20260126-DATA-COMPLIANCE`
**申請日期**: `2026-01-26`
**目的**: 修正 JobPosting 薪資解析失敗、平台名稱不一致以及公司名稱缺失導致的 SDD 驗證錯誤。

---

## 1. 影響範圍評估 (Impact Analysis)

### ⚠️ Affected Specs (受影響的規格)
- [x] `core/schemas/job_schema.json` (邏輯相容性)
- [x] `core/schemas/company_schema.json` (必填欄位檢查)

### 🛠️ Affected Code (受影響的代碼)
- [x] `core/adapters/jsonld_adapter.py` (通用薪資解析)
- [x] `core/adapters/adapter_104.py` (公司名稱提取)
- [x] `core/infra/schemas.py` (Enum 定義)

---

## 2. 變更內容描述 (Description of Changes)

### 規格層級 (Spec Level)
- 保持 `salary_min` / `salary_max` 為 `integer | null`。
- 增加對非標註薪資的容錯處理，確保不因髒數據中斷抓取。

### 實作層級 (Code Level)
- **JsonLdAdapter**: `_parse_common_salary` 增加對非數字字串的過濾，若無數字則回傳 `None` 而非拋出異常或回傳字串。
- **Adapter104**: 優化 `get_company_name` 邏輯，增加從 JSON-LD `hiringOrganization` 或 HTML Title 的萃取可靠度。

---

## 3. 驗證計畫 (Validation Plan)
- [x] 已備妥新的測試樣本於 `test/unit/data/failed_samples`
- [x] 執行 `quality_dashboard.py` 驗證失效樣本數下降
- [x] 單元測試驗證 `SalaryParser` 的極端情況
