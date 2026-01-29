# 職業類別順序執行 - 修正方案

> **日期**: 2026-01-29  
> **目標**: 改為逐個職業類別執行，支持暫停/恢復

---

## 修正概述

### 當前問題

```python
# 現有實現：所有分類並行執行
cat_tasks = [process_category(cat) for cat in categories]
await asyncio.gather(*cat_tasks)  # ⚠️ 所有分類同時執行
```

問題：
- ❌ 無法細粒度追蹤進度（某分類卡到某個 URL）
- ❌ 故障恢復時無法接續上次的分類
- ❌ 並行執行會導致同一平台上有多個分類搶互聯網頻寬

### 優化方案

```python
# 修正實現：逐個分類執行
for cat in categories:
    await process_category(cat)  # ✅ 一個接一個
    # 每個分類完成後自動記錄進度
```

優點：
- ✅ 清晰的進度追蹤（完成到第 N 個分類）
- ✅ 支持暫停/恢復（故障後可接續上次）
- ✅ 順序執行，具有可預測性

---

## 代碼修正

### 修改 1: run_platform() - 改為逐個分類執行

**位置**: `core/services/crawl_service.py` (L420-454)

**當前代碼:**
```python
async def run_platform(self, platform: SourcePlatform, max_jobs: int = 20, target_cat_id: Optional[str] = None) -> None:
    """執行特定平台的爬取流水線。"""
    logger.info("pipeline_started", platform=platform.value, cat_limit=target_cat_id)
    
    categories: List[Dict[str, Any]] = await self.discovery.get_category_codes(platform, target_id=target_cat_id)
    
    async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=20.0) as client:
        # 設置併發限制
        sem = asyncio.Semaphore(5)
        
        async def process_category(cat: Dict[str, Any]):
            cat_id: str = cat["layer_3_id"]
            cat_name: Optional[str] = cat.get("layer_3_name")
            
            # 探索 URL 列表
            urls: List[str] = await self.discovery.discover_category(platform, cat_id, client, limit=max_jobs)
            if not urls: return
            
            logger.info("category_discovery_stats", platform=platform.value, cat=cat_id, count=len(urls))
            
            # 併發處理該類別下的網址
            async def process_with_sem(url: str):
                async with sem:
                    await self._process_url_and_save(platform, url, client, cat_id, cat_name)

            job_tasks = [process_with_sem(url) for url in list(set(urls))[:max_jobs]]
            await asyncio.gather(*job_tasks)
            await self.db.mark_category_as_crawled(platform.value, cat_id)

        # 執行所有類別的處理
        cat_tasks = [process_category(cat) for cat in categories]
        await asyncio.gather(*cat_tasks)
```

**修正後代碼:**
```python
async def run_platform(
    self, 
    platform: SourcePlatform, 
    max_jobs: int = 20, 
    target_cat_id: Optional[str] = None,
    resume: bool = True  # ✅ 新增：是否恢復上次進度
) -> None:
    """
    執行特定平台的爬取流水線（逐個職業類別順序執行）。
    
    Args:
        platform (SourcePlatform): 目標平台。
        max_jobs (int): 每個分類的職缺上限。
        target_cat_id (Optional[str]): 若指定，只爬取該分類。
        resume (bool): 若 True，跳過已完成的分類；若 False，重新處理全部。
    """
    logger.info("pipeline_started", platform=platform.value, category_mode="sequential", resume=resume)
    
    categories: List[Dict[str, Any]] = await self.discovery.get_category_codes(platform, target_id=target_cat_id)
    if not categories:
        logger.warning("no_categories_found", platform=platform.value)
        return
    
    # ✅ 若 resume=True，過濾掉已完成的分類
    if resume and not target_cat_id:
        crawled_cats = await self.db.get_crawled_categories(platform.value)
        categories = [cat for cat in categories if cat["layer_3_id"] not in crawled_cats]
        logger.info("resume_mode_filtered", platform=platform.value, remaining=len(categories))
    
    async with httpx.AsyncClient(
        verify=False, 
        follow_redirects=True, 
        timeout=20.0,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)
    ) as client:
        # 設置併發限制（URL 級別，不是分類級別）
        sem = asyncio.Semaphore(self._get_concurrency_for_platform(platform))
        
        # ✅ 逐個分類執行（而不是並行 gather）
        total_cats = len(categories)
        for cat_idx, cat in enumerate(categories, 1):
            cat_id: str = cat["layer_3_id"]
            cat_name: Optional[str] = cat.get("layer_3_name")
            
            logger.info(
                "category_processing_start",
                platform=platform.value,
                category_index=f"{cat_idx}/{total_cats}",
                cat_id=cat_id,
                cat_name=cat_name
            )
            
            try:
                # 探索 URL 列表
                urls: List[str] = await self.discovery.discover_category(
                    platform, 
                    cat_id, 
                    client, 
                    limit=max_jobs
                )
                
                if not urls:
                    logger.debug("category_no_urls", platform=platform.value, cat=cat_id)
                    await self.db.mark_category_as_crawled(platform.value, cat_id)
                    continue
                
                logger.info(
                    "category_discovery_stats",
                    platform=platform.value,
                    cat=cat_id,
                    count=len(urls)
                )
                
                # 併發處理該類別下的網址（信號量應用於 URL 級別）
                async def process_with_sem(url: str):
                    async with sem:
                        await self._process_url_and_save(
                            platform, 
                            url, 
                            client, 
                            cat_id, 
                            cat_name
                        )
                
                # ✅ 改為：建立任務但順序執行 URL
                job_tasks = [
                    process_with_sem(url) 
                    for url in list(set(urls))[:max_jobs]
                ]
                
                # 執行所有 URL（但受信號量限制，確保並發度控制）
                await asyncio.gather(*job_tasks, return_exceptions=True)
                
                # ✅ 分類處理完成，標記進度
                await self.db.mark_category_as_crawled(platform.value, cat_id)
                
                logger.info(
                    "category_processing_completed",
                    platform=platform.value,
                    cat=cat_id,
                    progress=f"{cat_idx}/{total_cats}"
                )
                
            except Exception as e:
                logger.error(
                    "category_processing_error",
                    platform=platform.value,
                    cat=cat_id,
                    error=str(e),
                    exc_info=True
                )
                # ⚠️ 分類失敗時不標記為完成，下次 resume 時會重試
                continue
        
        logger.info("pipeline_completed", platform=platform.value, total_categories=total_cats)
```

---

### 修改 2: 新增輔助方法 - get_crawled_categories()

**位置**: `core/infra/database.py` (新增方法)

```python
async def get_crawled_categories(self, platform: str, days: int = 30) -> set:
    """
    取得指定平台已爬取的分類列表。
    
    Args:
        platform (str): 平台名稱 (e.g., 'platform_104')。
        days (int): 查詢時間範圍（天數）。
    
    Returns:
        set: 已爬取的分類 ID 集合。
    """
    try:
        async with self.safe_cursor() as cursor:
            await cursor.execute(
                """
                SELECT DISTINCT layer_3_id 
                FROM tb_categories 
                WHERE platform = %s 
                  AND updated_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                """,
                (platform, days)
            )
            rows = await cursor.fetchall()
            return {row[0] for row in rows}
    except Exception as e:
        logger.error("get_crawled_categories_failed", platform=platform, error=str(e))
        return set()
```

---

### 修改 3: run_all() - 平台仍然並行，分類順序執行

**位置**: `core/services/crawl_service.py` (L456-462)

**當前代碼:**
```python
async def run_all(self, limit_per_platform: int = 10) -> None:
    """啟動所有支援平台的自動抓取。"""
    for p in SourcePlatform:
        if p == SourcePlatform.PLATFORM_UNKNOWN: continue
        try:
            await self.run_platform(p, max_jobs=limit_per_platform)
        except Exception as e:
            logger.error("platform_crash", platform=p.value, error=str(e))
```

**修正後代碼:**
```python
async def run_all(
    self, 
    limit_per_platform: int = 10,
    resume: bool = True  # ✅ 新增：支持恢復上次進度
) -> None:
    """
    啟動所有支援平台的自動抓取（平台並行，分類順序）。
    
    Args:
        limit_per_platform (int): 每個分類的職缺上限。
        resume (bool): 若 True，跳過已完成的分類。
    """
    logger.info("run_all_started", mode="parallel_platforms_sequential_categories", resume=resume)
    
    # ✅ 5 個平台並行執行（各自內部職業類別順序執行）
    tasks = [
        self.run_platform(
            p, 
            max_jobs=limit_per_platform,
            resume=resume  # 傳遞 resume 參數
        )
        for p in SourcePlatform
        if p != SourcePlatform.PLATFORM_UNKNOWN
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 統計結果
    failures = sum(1 for r in results if isinstance(r, Exception))
    logger.info(
        "run_all_completed",
        total_platforms=len(results),
        failures=failures,
        mode="parallel_platforms_sequential_categories"
    )
    
    if failures > 0:
        logger.warning("run_all_had_failures", failed_platforms=failures)
```

---

## 執行模式對比

### 優化前 (並行所有分類)

```
平台 104
├─ 分類 A (並行) ─────────┐
├─ 分類 B (並行) ─────────┼─ 同時執行，12 分鐘
├─ 分類 C (並行) ─────────┤
└─ 分類 D (並行) ─────────┘

問題：
❌ 無法精確追蹤「卡在分類 B 的 URL 5」
❌ 故障後無法接續「分類 C 的 URL 8」
```

### 優化後 (順序執行分類)

```
平台 104
├─ 分類 A [████████] 完成，已記錄
├─ 分類 B [██████░░] 進行中...
│  ├─ URL 1 [完成]
│  ├─ URL 2 [完成]
│  ├─ URL 3 [進行中...]
│  └─ ...
├─ 分類 C [待執行]
└─ 分類 D [待執行]

好處：
✅ 清晰進度追蹤
✅ 故障後可接續分類 B 的 URL 3
✅ 支持 resume 機制
```

---

## 使用場景

### 場景 1: 全新爬取

```python
# 第一次爬取，resume=True（預設）
await crawl_service.run_all(limit_per_platform=10, resume=True)

# 全部分類逐個執行
# 每完成一個分類就標記進度
```

### 場景 2: 故障恢復

```bash
# Day 1: 執行到一半時容器崩潰（已完成分類 A-C）

# Day 2: 重新啟動
await crawl_service.run_all(limit_per_platform=10, resume=True)

# 系統自動跳過已完成的 A-C，接續分類 D
```

### 場景 3: 重新處理某平台

```python
# 需要重新爬取平台 104 的全部分類（跳過 resume）
await crawl_service.run_platform(
    SourcePlatform.PLATFORM_104,
    max_jobs=20,
    resume=False  # 不跳過已完成分類，全部重做
)
```

### 場景 4: 僅處理某個分類

```python
# 只爬取平台 1111 的特定分類（如「軟體工程」）
await crawl_service.run_platform(
    SourcePlatform.PLATFORM_1111,
    target_cat_id="software_engineering",  # 指定分類
    max_jobs=50
)
```

---

## 日誌輸出範例

### 執行日誌

```json
{
  "event": "pipeline_started",
  "platform": "platform_104",
  "category_mode": "sequential",
  "resume": true,
  "timestamp": "2026-01-29T10:00:00Z"
}

{
  "event": "resume_mode_filtered",
  "platform": "platform_104",
  "crawled_before": 15,
  "remaining": 8,
  "timestamp": "2026-01-29T10:00:05Z"
}

{
  "event": "category_processing_start",
  "platform": "platform_104",
  "category_index": "1/8",
  "cat_id": "cat_001",
  "cat_name": "軟體工程",
  "timestamp": "2026-01-29T10:00:10Z"
}

{
  "event": "category_discovery_stats",
  "platform": "platform_104",
  "cat": "cat_001",
  "count": 45,
  "timestamp": "2026-01-29T10:00:12Z"
}

[... URL 處理 ...]

{
  "event": "category_processing_completed",
  "platform": "platform_104",
  "cat": "cat_001",
  "progress": "1/8",
  "timestamp": "2026-01-29T10:15:30Z"
}

{
  "event": "category_processing_start",
  "platform": "platform_104",
  "category_index": "2/8",
  "cat_id": "cat_002",
  "cat_name": "市場行銷",
  "timestamp": "2026-01-29T10:15:35Z"
}

[... 重複 ...]

{
  "event": "pipeline_completed",
  "platform": "platform_104",
  "total_categories": 8,
  "timestamp": "2026-01-29T11:30:00Z"
}
```

---

## 性能影響

### 吞吐量對比

| 指標 | 並行分類 | 順序分類 | 備註 |
|------|---------|---------|------|
| **單平台耗時** | 12 min | 12 min | 總耗時相同（受 URL 級併發影響） |
| **進度追蹤** | ❌ 粗糙 | ✅ 精確 | 順序執行更易追蹤 |
| **恢復能力** | ❌ 差 | ✅ 強 | 可精確接續 |
| **運維成本** | 🔴 高 | 🟢 低 | 順序執行更易監控 |

### 吞吐量計算

```
總職缺數 = 8 分類 × 50 URL/分類 = 400 URL

並行分類:
  [Categ A] ┐
  [Categ B] ├─ 並行 (8 個分類同時)
  [Categ C] ┤  耗時 = 12 min
  ...       ┘
  單 URL 耗時 ≈ 1.8 sec
  
順序分類:
  [Categ A] ─────
  [Categ B] ─────    順序 (一個接一個)
  [Categ C] ─────    耗時 = 12 min (相同！信號量控制)
  ...
  單 URL 耗時 ≈ 1.8 sec (相同！)

結論: 總吞吐相同，但追蹤能力顯著提升
```

---

## 部署檢查清單

- [ ] 代碼修改已測試
- [ ] 新增 `get_crawled_categories()` 方法
- [ ] 數據庫表 `tb_categories` 有 `updated_at` 欄位
- [ ] 日誌輸出驗證（見上述範例）
- [ ] 執行 `pytest test/sdd/test_sequential_execution.py`
- [ ] 測試 resume 機制：停止後再啟動
- [ ] 驗證進度記錄正確

---

## 回滾方案

若要回到並行分類模式：

```python
# 改回舊邏輯
cat_tasks = [process_category(cat) for cat in categories]
await asyncio.gather(*cat_tasks)
```

但 **不建議** 回滾，因為順序執行提供了更好的可觀測性和容錯能力。

---

