# 職業類別順序執行 - 快速參考

> **最常用的 5 個命令**

---

## 1️⃣ 首次爬取（標準模式）

```python
# 所有平台並行，內部分類順序執行
await crawl_service.run_all(limit_per_platform=20, resume=True)
```

**效果：**
- 5 個平台 **同時執行**
- 各平台內分類 **逐個執行**
- 已完成分類自動跳過（多次執行時）
- ✅ 預期耗時：~12 分鐘

---

## 2️⃣ 故障恢復（自動繼續）

```python
# 容器崩潰後直接重啟，系統自動接續
await crawl_service.run_all(limit_per_platform=20, resume=True)
```

**效果：**
- 自動偵測已爬取分類
- 跳過完成的分類 A-C
- 接續未完成分類 D
- 無需手動修改數據庫
- ✅ 節省 ~5 分鐘

---

## 3️⃣ 強制重爬（清除進度）

```python
# 重新爬取全部分類，忽略之前的進度
await crawl_service.run_all(limit_per_platform=20, resume=False)
```

**效果：**
- 重新爬取 **所有分類**
- 忽略 `tb_categories.updated_at` 記錄
- 用於測試或資料驗證
- ⚠️ 耗時：全部 12 分鐘

---

## 4️⃣ 單個平台重爬（部分重做）

```python
# 只重爬平台 104，其他平台不變
await crawl_service.run_platform(
    SourcePlatform.PLATFORM_104,
    max_jobs=20,
    resume=False
)
```

**效果：**
- 只重爬 **平台 104**
- 其他平台繼續執行
- 用於平台級故障修復

---

## 5️⃣ 特定分類測試（Debug）

```python
# 只爬取某個特定分類（用於測試或修復）
await crawl_service.run_platform(
    SourcePlatform.PLATFORM_104,
    target_cat_id="cat_software_engineering",
    max_jobs=50,
    resume=True  # 注：target_cat_id 時 resume 無效
)
```

**效果：**
- 只處理 **1 個分類**
- 最大 50 個職缺
- 用於分類級故障修復
- ✅ 耗時：~2 分鐘

---

## 📊 日誌監控

### 查看進度

```bash
# 實時查看爬蟲進度
docker logs crawler_system -f | grep "category_processing"
```

**典型輸出：**
```
2026-01-29T10:00:10Z category_processing_start platform=platform_104 category_index=1/8 cat_id=cat_001
2026-01-29T10:15:30Z category_processing_completed platform=platform_104 cat=cat_001 progress=1/8
2026-01-29T10:15:35Z category_processing_start platform=platform_104 category_index=2/8 cat_id=cat_002
```

### 檢查已爬取分類

```python
# 查詢已爬取分類
db = Database()
crawled = await db.get_crawled_categories("platform_104", days=30)
print(f"已爬取: {len(crawled)} 個分類")
print(f"分類列表: {crawled}")
```

---

## 🎯 常見場景對應表

| 場景 | 命令 | 耗時 | 備註 |
|------|------|------|------|
| 第一次爬取 | `run_all(resume=True)` | 12 min | 標準流程 |
| 容器重啟 | `run_all(resume=True)` | ~5 min | 跳過已完成 |
| 升級新規則 | `run_all(resume=False)` | 12 min | 全部重做 |
| 修復平台 104 | `run_platform(104, resume=False)` | 12 min | 只改一個平台 |
| 測試分類 | `run_platform(104, target_cat_id=...)` | 2 min | Debug 用 |

---

## ⚠️ 常見問題

### Q: 為什麼分類執行順序而不是並行？
**A:** 為了實現「接續上次的分類」功能。並行執行時無法精確定位哪個分類失敗。現在的設計：
- ✅ 支持故障恢復
- ✅ 進度可追蹤
- ✅ 吞吐量無損（平台層仍並行）

### Q: 為什麼平台改為並行？
**A:** 大幅削減總耗時：
```
舊: 平台 104 (12 min) → 1111 (12 min) → ... = 60 min
新: 平台並行 max(12, 12, ...) = 12 min  ← 5 倍加速！
```

### Q: 如何強制重爬某個分類？
**A:** 使用 `target_cat_id` 參數（自動忽略 resume 邏輯）：
```python
await crawl_service.run_platform(
    SourcePlatform.PLATFORM_104,
    target_cat_id="cat_001",  # 只爬這個
    resume=True
)
```

### Q: 如何查看還有多少分類未爬取？
**A:** 
```sql
-- 方式 1: 查詢 30 天內已更新的分類
SELECT DISTINCT layer_3_id 
FROM tb_categories 
WHERE platform = 'platform_104'
  AND updated_at >= DATE_SUB(NOW(), INTERVAL 30 DAY);

-- 方式 2: 查詢 30 天內未更新的分類
SELECT DISTINCT layer_3_id 
FROM tb_categories 
WHERE platform = 'platform_104'
  AND updated_at < DATE_SUB(NOW(), INTERVAL 30 DAY);
```

### Q: Resume 的時間範圍可以改嗎？
**A:** 可以，修改 `get_crawled_categories()` 的 `days` 參數：
```python
# 只考慮 7 天內的記錄
crawled = await db.get_crawled_categories("platform_104", days=7)

# 或者考慮所有記錄
crawled = await db.get_crawled_categories("platform_104", days=999)
```

---

## 🔍 驗證修改是否生效

### 1. 檢查日誌格式

```bash
# 執行爬蟲並監控
docker logs crawler_system -f 2>&1 | head -100
```

**應該看到：**
- ✅ `category_mode="sequential"` 
- ✅ `category_index="N/M"` 
- ✅ 逐個分類的 `category_processing_*` 事件

### 2. 驗證 Resume 邏輯

```python
# 測試腳本
python scripts/test_sequential_execution.py
```

**應該返回：**
```
✅ PASS: TEST 1: get_crawled_categories()
✅ PASS: TEST 2: 分類跳過邏輯
✅ PASS: TEST 3: Resume 過濾邏輯
✅ PASS: TEST 4: 順序執行結構
總計: 4/4 測試通過
```

### 3. 檢查數據庫更新

```sql
-- 查詢分類表的 updated_at 時間戳
SELECT layer_3_id, updated_at 
FROM tb_categories 
WHERE platform = 'platform_104'
ORDER BY updated_at DESC LIMIT 10;

-- 應該看到最近更新的分類
```

---

## 📈 性能指標

### 預期改進

| 指標 | 舊系統 | 新系統 | 改進 |
|------|--------|--------|------|
| **首次爬取耗時** | 60 min | 12 min | **5 倍快速** ⚡ |
| **容器重啟恢復** | 60 min | 5 min | **92% 加速** ⚡ |
| **進度可視性** | ❌ 差 | ✅ 優 | **顯著提升** 📊 |
| **故障恢復成本** | 高 | 低 | **58% 節省** 💰 |

### 吞吐量

```
URL 並發數: 5 (不變，控制在 URL 層)
平台並行數: 1 → 5 (新增)
分類執行模式: 並行 → 順序 (改進可追蹤性)

結果: 總耗時 12 min (5 倍改進)
```

---

## 🚀 最佳實踐

### ✅ 推薦做法

1. **定期執行** `run_all(resume=True)`
   ```python
   # 每日 10:00 執行一次
   await crawl_service.run_all(limit_per_platform=20, resume=True)
   ```

2. **監控日誌中的進度**
   ```bash
   # 設置告警：若某分類卡在同一地點超過 1 小時
   docker logs crawler_system -f | grep -E "category_index|error"
   ```

3. **每週進行驗證爬取**
   ```python
   # 每週日進行 resume=False 驗證
   if datetime.now().weekday() == 6:  # Sunday
       await crawl_service.run_all(limit_per_platform=20, resume=False)
   ```

### ❌ 避免做法

1. ❌ **手動修改 `updated_at` 欄位**（應使用 `resume=False`）
2. ❌ **同時啟動多個 `run_all()` 實例**（避免資料競合）
3. ❌ **過於頻繁的 `resume=False` 爬取**（浪費資源）

---

## 📞 支持與調試

### 若遇到問題

1. **分類未跳過 (Resume 失效)**
   ```sql
   -- 檢查 tb_categories 是否有相應分類
   SELECT * FROM tb_categories 
   WHERE platform='platform_104' AND layer_3_id='cat_001';
   ```

2. **進度日誌消失**
   ```bash
   # 檢查日誌級別設定
   grep -r "LOG_LEVEL" core/infra/logging_config.py
   ```

3. **爬蟲無法接續**
   ```python
   # 強制刷新進度（危險操作）
   await db.mark_category_as_crawled('platform_104', 'cat_001')
   ```

---

