# 專案演進藍圖 (Project Roadmap)

本文件記錄 `crawler_system_v3_JSON_LD` 專案的發展里程碑、當前技術狀態以及未來的進化方向。

---

## 🚩 已達成里程碑 (Completed Milestones)

### 2026 Q1: 從「選擇器」轉向「規格化」 (Migration to SDD)
- **技術轉型**：廢棄易損毀的 CSS/XPath 選擇器，改為提取 `application/ld+json` 結構化數據。
- **數據契約**：確立了以 JSON Schema 為核心的 `JobPydantic` 與 `CompanyPydantic` 數據實體。
- **驗證閘口**：實作 `SchemaValidator`，確保所有存入資料庫的職缺數據 100% 符合規格。
- **穩定性強化**：實作全域 Redis 限流 (Throttling) 與 429 自動冷卻機制。

---

## 🏗️ 當前技術狀態 (Current Technical State)

### SDD 合規架構
系統目前完全遵循 [SDD 開發規範](SDD_STANDARDS.md)，具備高度的數據純淨度與防護能力。

### AI 隔離沙盒 (Isolation Sandbox)
- **防禦性策略**：針對 Ollama 目前的辨識不穩定性，系統實施了徹底的隔離。AI 自癒功能預設關閉 (`ENABLE_AI_HEAL = False`)。
- **基準測試**：具備自動化量化工具 `benchmark_ollama.py`，作為 AI 是否具備回歸生產隊列資格的唯一考核標準。

---

## 🚀 未來進化方向 (Future Phases)

### Phase 5: 主動學習循環 (Active Learning Loop)
- **動態 Few-shot 注入**：系統將具備自動從「成功 L1 案例」中提取範例並實時更新 Prompt 的能力，讓 AI 隨數據增長而自動「變聰明」。
- **負向反饋修正**：自動收集被驗證閘口攔截的「幻覺樣本」，作為針對性優化的教材。

### Phase 6: 指令微調專屬模型 (Domain-Specific Fine-tuning)
- **目標**：不再依賴通用模型，訓練專屬於「台灣招聘網頁結構」的輕量化 LLM。
- **路徑**：當 L1 高品質數據累積至 > 5,000 筆時，啟動模型微調管線，追求 95% 以上的原生辨識率。

### Phase 7: 自進化規格 (Self-Evolving Schema)
- **技術遠景**：系統能自動偵測市場上出現的新職位類別或技能需求，並主動向開發者提交「規格更新建議書」。

---

## 📈 演進原則 (Evolution Philosophy)
1. **穩定性優先**：任何新功能（特別是 AI）必須在沙盒中通過基準測試，方可併入生產流程。
2. **數據即真理**：L1 (JSON-LD/Adapter) 永遠具備最高優先權。
3. **規格驅動**：所有演進必須先更新 `docs/SDD_STANDARDS.md`。
