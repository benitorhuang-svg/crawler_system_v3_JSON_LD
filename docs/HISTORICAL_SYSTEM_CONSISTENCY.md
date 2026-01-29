# SDD 變更提案 (20260126-SYSTEM-CONSISTENCY)

**提案編號**: `20260126-SYSTEM-CONSISTENCY`
**申請日期**: `2026-01-26`
**目的**: 完善 `PLATFORM_UNKNOWN` 引入後的系統一致性，並新增資料健康診斷工具。

---

## 1. 影響範圍評估 (Impact Analysis)

### ⚠️ Affected Specs (受影響的規格)
- 無直接 Schema 變更。

### 🛠️ Affected Code (受影響的代碼)
- [x] `core/adapters/adapter_factory.py` (工廠模式調整)
- [x] `test/unit/tools/gen_adversarial_samples.py` (測試指令調整)
- [x] `test/unit/tools/diag_data_health.py` (新增工具)

---

## 2. 變更內容描述 (Description of Changes)

### 實作層級 (Code Level)
- **AdapterFactory**: 明確處理 `PLATFORM_UNKNOWN` 情況。
- **Adversarial Generator**: 更新對抗樣本生成的邏輯，將 `platform_unknown` 移出非法枚舉測試。
- **Diagnostics Tool**: 基於 `Database` 實作資料分析腳本，輸出系統目前的品質指標（如 L1/L2 比例、缺失欄位熱點）。

---

## 3. 驗證計畫 (Validation Plan)
- 執行 `diag_data_health.py` 並檢查輸出。
- 重新生成對抗樣本並驗證驗證器攔截情況。
