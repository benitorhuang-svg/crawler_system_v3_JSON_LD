# 優化實作補丁 - Phase 1

## 文件 1: crawl_service.py

### 修改 #1: 增加自適應並發度計算方法

在 `CrawlService` 類別中添加：

```python
def _get_concurrency_for_platform(self, platform: SourcePlatform) -> int:
    """
    根據平台特性計算最佳並發度。
    
    SDD 規範: 根據平台速率與容錯能力動態調整，確保在避免封鎖的前提下最大化吞吐。
    
    Args:
        platform (SourcePlatform): 目標平台。
    
    Returns:
        int: 推薦的並發度（信號量上限）。
    """
    # 映射表：基於實測與平台特性
    concurrency_map: Dict[SourcePlatform, int] = {
        SourcePlatform.PLATFORM_104: 10,        # API 穩定，容忍度高
        SourcePlatform.PLATFORM_1111: 10,       # JSON API，速率友善
        SourcePlatform.PLATFORM_YES123: 6,      # ⚠️ 易觸發 429，保守策略
        SourcePlatform.PLATFORM_CAKERESUME: 8,  # 中等規模，容易
        SourcePlatform.PLATFORM_YOURATOR: 8,    # 開放友善
    }
    return concurrency_map.get(platform, 5)

def _get_throttle_params(self, platform: SourcePlatform) -> Tuple[float, float]:
    """
    從全域配置取得平台特定的限流參數。
    
    Returns:
        Tuple[float, float]: (rate, capacity) 即 (每秒令牌率, 最大容量)
    """
    default_rate: Tuple[float, float] = (2.0, 10.0)
    return settings.THROTTLE_CONFIG.get(platform.value, default_rate)
```

### 修改 #2: 集成 Throttler 到初始化

在 `CrawlService.__init__()` 中添加：

```python
def __init__(
    self,
    db: Optional[Database] = None,
    discovery: Optional[DiscoveryService] = None,
    extractor: Optional[JsonLdExtractor] = None,
    validator: Optional[SchemaValidator] = None,
    geocoder: Optional[Geocoder] = None,
    skill_extractor: Optional[SkillExtractor] = None
) -> None:
    """初始化核心組件，支援依賴注入以符合 SOLID 原則。"""
    self.db = db or Database()
    self.discovery = discovery or DiscoveryService()
    self.extractor = extractor or JsonLdExtractor()
    self.validator = validator or SchemaValidator()
    self.geocoder = geocoder or Geocoder()
    self.skill_extractor = skill_extractor or SkillExtractor()
    self.redis = RedisClient().get_client()
    
    # ✅ 新增：Throttler 實例
    self.throttler = Throttler()
    
    # 內存快取與 AI 調控
    self._company_cache: Dict[str, CompanyPydantic] = {}
    self._max_company_cache: int = 1000
    self._ai_failure_count: int = 0
    self._ai_isolated_until: float = 0.0
    
    # 配置參數
    self.AI_FAILURE_THRESHOLD = settings.RETRY_COUNT
    self.ENABLE_AI_HEALING = True
    self.HTML_CACHE_TTL = 3600
    self.AI_ISOLATION_WINDOW = 600  # 10 分鐘
```

### 修改 #3: 優化 run_platform() 應用自適應並發度

```python
async def run_platform(self, platform: SourcePlatform, max_jobs: int = 20, target_cat_id: Optional[str] = None) -> None:
    """執行特定平台的爬取流水線。"""
    logger.info("pipeline_started", platform=platform.value, cat_limit=target_cat_id)
    
    categories: List[Dict[str, Any]] = await self.discovery.get_category_codes(platform, target_id=target_cat_id)
    
    async with httpx.AsyncClient(
        verify=False, 
        follow_redirects=True, 
        timeout=20.0,
        # ✅ 連線池配置（Phase 2 優化）
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)
    ) as client:
        # ✅ 自適應並發度：根據平台特性動態調整
        concurrency = self._get_concurrency_for_platform(platform)
        sem = asyncio.Semaphore(concurrency)
        logger.info("platform_concurrency_set", platform=platform.value, concurrency=concurrency)
        
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
            await asyncio.gather(*job_tasks, return_exceptions=True)
            await self.db.mark_category_as_crawled(platform.value, cat_id)

        # 執行所有類別的處理
        cat_tasks = [process_category(cat) for cat in categories]
        await asyncio.gather(*cat_tasks, return_exceptions=True)
```

### 修改 #4: 更新 _process_url_and_save() 集成 Throttler

找到 `_process_url_and_save()` 方法，將其修改為：

```python
async def _process_url_and_save(
    self, 
    platform: SourcePlatform, 
    url: str, 
    client: httpx.AsyncClient, 
    cat_id: Optional[str] = None,
    cat_name: Optional[str] = None
) -> None:
    """処理單個 URL 的完整流程（含 Throttler 限流）。"""
    
    # ✅ 新增：從配置取得限流參數
    rate, capacity = self._get_throttle_params(platform)
    
    # ✅ 新增：等待限流令牌
    allowed = await self.throttler.wait_for_slot(
        platform=platform,
        rate=rate,
        capacity=capacity,
        timeout=30.0
    )
    
    if not allowed:
        logger.warning("throttle_exhausted_skip_url", platform=platform.value, url=url)
        return
    
    start_ts = time.time()
    logger.debug("url_processing_start", platform=platform.value, url=url[:50])
    
    try:
        job, comp, loc, raw_json = await self.process_url(url, platform, client)
        
        if not job:
            logger.debug("url_processing_no_job", url=url[:50])
            # ✅ 報告失敗，觸發自適應降速
            await self.throttler.report_429(platform, rate, duration=300)
            return
        
        # ✅ 報告成功，觸發自適應提速
        await self.throttler.report_success(platform, rate)
        
        # 補全數據
        job.raw_json = raw_json
        if comp:
            await self.enrich_company(comp, platform, client)
            job.company_source_id = comp.source_id
        
        if cat_id:
            job.platform_category_id = cat_id
        if cat_name:
            job.platform_category_name = cat_name
        
        success = await self.db.save_full_job_data(job, comp, None, location=loc)
        
        if success:
            logger.info("url_processing_success", platform=platform.value, source_id=job.source_id)
            
            # 異步執行選配增強
            skills = self.skill_extractor.extract(job.description or "", platform.value, job.source_id)
            if skills:
                await self.db.save_job_skills(skills)
            
            if not loc and job.address:
                lat, lon, fmt = await self.geocoder.geocode(job.address, city=job.region, district=job.district)
                if lat and lon:
                    await self.db.save_job_location(JobLocationPydantic(
                        platform=platform.value, 
                        job_source_id=job.source_id,
                        latitude=lat, 
                        longitude=lon, 
                        formatted_address=fmt or job.address, 
                        provider="OSM"
                    ))
        else:
            logger.warning("url_processing_db_save_failed", url=url[:50])
            
    except httpx.HTTPStatusError as e:
        # ✅ 檢測 429 並報告給 Throttler
        if e.response.status_code == 429:
            logger.warning("rate_limited_429", platform=platform.value, url=url[:50])
            await self.throttler.report_429(platform, rate, duration=600)
        else:
            logger.warning("url_processing_http_error", status=e.response.status_code, url=url[:50])
    except asyncio.TimeoutError:
        logger.warning("url_processing_timeout", url=url[:50])
    except Exception as e:
        logger.error("url_processing_error", url=url[:50], error=str(e), exc_info=True)
    finally:
        elapsed = time.time() - start_ts
        logger.debug("url_processing_complete", url=url[:50], elapsed_ms=int(elapsed * 1000))
```

### 修改 #5: 全局 Fan-out - run_all() 改用並行

```python
async def run_all(self, limit_per_platform: int = 10) -> None:
    """✅ 啟動所有支援平台的自動抓取（並行執行）。"""
    logger.info("run_all_started", platforms_count=len(list(SourcePlatform)))
    
    # 構建所有平台的任務
    tasks = [
        self.run_platform(p, max_jobs=limit_per_platform)
        for p in SourcePlatform
        if p != SourcePlatform.PLATFORM_UNKNOWN
    ]
    
    # ✅ 改為並行執行，使用 gather 代替逐個 for 迴圈
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 統計結果
    failures = sum(1 for r in results if isinstance(r, Exception))
    logger.info("run_all_completed", total=len(results), failures=failures)
    
    if failures > 0:
        logger.warning("run_all_had_failures", failed_platforms=failures)
```

---

## 文件 2: core/infra/config.py

### 修改：增強 THROTTLE_CONFIG

在 `Settings` 類別中更新限流配置：

```python
# 平台限流配置：(每秒速率, 突發容量)
# 基於實測與安全邊界調整
THROTTLE_CONFIG: Dict[str, tuple[float, float]] = {
    "platform_104": (5.0, 25.0),         # API 穩定，可調高
    "platform_1111": (5.0, 25.0),        # JSON API 穩定
    "platform_yes123": (3.0, 18.0),      # ⚠️ 保守：低速率，小突發
    "platform_cakeresume": (5.0, 20.0),  # 中等規模
    "platform_yourator": (5.0, 20.0),    # 開放友善
    "default": (2.0, 10.0)               # 未知平台預設
}

# 新增：平台特定延遲
PLATFORM_DELAYS: Dict[str, float] = {
    "platform_yes123": 0.5,    # Yes123 加入額外延遲
    "default": 0.0             # 其他平台無額外延遲
}
```

---

## 文件 3: core/services/throttler.py

### 補丁：改進 wait_for_slot() 支援自定義超時

當前實現已很完整，但可補充以下日誌增強：

```python
async def wait_for_slot(self, platform: SourcePlatform, rate: float = 1.0, 
                        capacity: float = 10.0, timeout: float = 60.0, 
                        proxy_url: Optional[str] = None) -> bool:
    """
    ✅ 改進的分佈式令牌獲取函數（具備詳細日誌）。
    """
    if not self.redis or not self.lua_script: 
        return True

    name: str = platform.value
    token_key: str = f"throttle:{name}"
    start_ts: float = time.time()
    wait_count: int = 0

    while True:
        # 1. 檢查逾時
        if time.time() - start_ts > timeout:
            logger.warning("throttle_wait_timeout", 
                         platform=name, 
                         timeout=timeout, 
                         wait_cycles=wait_count)
            return False

        # 2. 檢查冷卻
        if await self.is_cooling(platform, proxy_url):
            await asyncio.sleep(2.0)
            wait_count += 1
            continue

        # 3. 執行 Lua 獲取令牌
        try:
            curr_rate: float = await self.get_adaptive_rate(platform, rate)
            now: float = time.time()
            result: Union[int, float] = self.lua_script(
                keys=[token_key], 
                args=[curr_rate, capacity, now]
            )
            
            if result == 1:
                elapsed = time.time() - start_ts
                if elapsed > 0.1:
                    logger.debug("throttle_slot_obtained", 
                               platform=name, 
                               wait_ms=int(elapsed * 1000))
                return True
            
            # 需等待，result 為負值預期等待秒數
            wait_val: float = abs(float(result))
            # 增加 Jitter 抖動，避免雷群效應
            wait_val = min(wait_val + random.uniform(0.01, 0.1), 5.0)
            await asyncio.sleep(wait_val)
            wait_count += 1
            
        except Exception as e:
            logger.error("throttle_lua_exec_failed", 
                       platform=name, 
                       error=str(e))
            return True  # 發生錯誤時傾向放行
```

---

## 測試驗證腳本

建立 `test/sdd/test_optimization.py`：

```python
"""
優化驗證測試：確保 Phase 1 優化達成預期目標。
"""
import asyncio
import pytest
import time
from unittest.mock import AsyncMock, patch, MagicMock
from core.services.crawl_service import CrawlService
from core.infra import SourcePlatform
from core.services.throttler import Throttler

class TestPhase1Optimization:
    """Phase 1 優化驗證測試套件。"""
    
    async def test_fan_out_concurrency(self):
        """驗證：5 平台並行執行，耗時 ≈ 最慢平台耗時。"""
        svc = CrawlService()
        
        # Mock run_platform 以不同速度完成
        async def mock_run(platform, max_jobs=10, target_cat_id=None):
            delays = {
                SourcePlatform.PLATFORM_104: 0.1,
                SourcePlatform.PLATFORM_1111: 0.15,
                SourcePlatform.PLATFORM_YES123: 0.2,
                SourcePlatform.PLATFORM_CAKERESUME: 0.12,
                SourcePlatform.PLATFORM_YOURATOR: 0.11,
            }
            await asyncio.sleep(delays.get(platform, 0.1))
        
        with patch.object(svc, 'run_platform', side_effect=mock_run):
            start = time.time()
            await svc.run_all(limit_per_platform=10)
            elapsed = time.time() - start
        
        # 預期耗時 ≈ max(delays) ≈ 0.2s，而非 sum ≈ 0.68s（串行）
        assert elapsed < 0.3, f"並行耗時過長: {elapsed}"
        print(f"✅ Fan-out 並行驗證通過: {elapsed:.2f}s")
    
    def test_adaptive_concurrency(self):
        """驗證：不同平台應應用不同並發度。"""
        svc = CrawlService()
        
        concurrency_map = {
            SourcePlatform.PLATFORM_104: 10,
            SourcePlatform.PLATFORM_1111: 10,
            SourcePlatform.PLATFORM_YES123: 6,  # 保守
            SourcePlatform.PLATFORM_CAKERESUME: 8,
            SourcePlatform.PLATFORM_YOURATOR: 8,
        }
        
        for platform, expected in concurrency_map.items():
            actual = svc._get_concurrency_for_platform(platform)
            assert actual == expected, f"{platform.value}: 期望 {expected}，實際 {actual}"
        
        print("✅ 自適應並發度驗證通過")
    
    async def test_throttler_integration(self):
        """驗證：Throttler 能正確限流。"""
        svc = CrawlService()
        throttler = svc.throttler
        
        platform = SourcePlatform.PLATFORM_104
        rate, capacity = svc._get_throttle_params(platform)
        
        # 連續獲取令牌，應逐漸受限
        results = []
        for i in range(15):
            start = time.time()
            success = await throttler.wait_for_slot(platform, rate, capacity, timeout=5.0)
            elapsed = time.time() - start
            results.append((success, elapsed))
        
        # 前幾個應立即成功，後面應經歷等待
        assert results[0][1] < 0.1, "首個令牌應立即獲取"
        assert results[-1][1] > 0.1, "突發後應進入等待"
        print(f"✅ Throttler 限流驗證通過: {len(results)} 個請求處理完畢")
    
    def test_throttle_params(self):
        """驗證：限流參數配置正確。"""
        svc = CrawlService()
        
        params = {
            SourcePlatform.PLATFORM_104: (5.0, 25.0),
            SourcePlatform.PLATFORM_1111: (5.0, 25.0),
            SourcePlatform.PLATFORM_YES123: (3.0, 18.0),  # 保守
        }
        
        for platform, (exp_rate, exp_cap) in params.items():
            rate, capacity = svc._get_throttle_params(platform)
            assert rate == exp_rate, f"{platform.value} rate 不符"
            assert capacity == exp_cap, f"{platform.value} capacity 不符"
        
        print("✅ 限流參數驗證通過")

# 執行測試
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

---

## 部署檢查清單

應用這些補丁前，請確認：

- [ ] 已備份原始 `crawl_service.py`
- [ ] 已在 `config.py` 更新 `THROTTLE_CONFIG`
- [ ] `Throttler` 已在中依賴環境中可用
- [ ] Redis 連線正常（用於令牌桶狀態存儲）
- [ ] 執行測試: `pytest test/sdd/test_optimization.py -v`
- [ ] 驗證日誌輸出無異常
- [ ] 在小規模環境試運行 24 小時

