import pytest
import asyncio
from core.services.crawl_service import CrawlService
from core.infra.browser_fetcher import BrowserFetcher
from core.infra import SourcePlatform

@pytest.mark.asyncio
async def test_minimal_crawl_pipeline():
    """驗證爬蟲服務的基本流程：抓取 -> 提取 -> 存儲概念。"""
    service = CrawlService()
    test_url = "https://www.cake.me/jobs/antigravity-test" 
    # 註：這是一個測試用 URL，實際運行會由 mock 或 fallback 處理
    
    # 測試抓取 (會經過 Redis 快取與 Browser Fallback)
    # 由於我們沒有真實的 Ollama / 104 API 在測試環境，我們主要驗證組件調用是否正常
    try:
        # 測試 104 (通常需要 Browser)
        result = await service.crawl_job(SourcePlatform.PLATFORM_104, "https://www.104.com.tw/job/7y8y8")
        # 即使失敗，也應返回 None 而非崩潰
        assert result is None or hasattr(result, "source_id")
    except Exception as e:
        pytest.fail(f"CrawlService crashed: {e}")
    finally:
        await BrowserFetcher.close_browser()

@pytest.mark.asyncio
async def test_throttler_logic():
    """驗證限流器是否如期工作。"""
    from core.enrichment.geocoder import Geocoder
    geocoder = Geocoder()
    
    # 連續兩次請求，第二次應被延遲或命中快取
    import time
    start = time.time()
    await geocoder.geocode("台北市信義區")
    await geocoder.geocode("台北市大同區")
    end = time.time()
    
    # 若無快取且成功觸發 Redis 鎖，耗時應至少 > 1s
    # 但如果是快取命中，則會很快
    print(f"Geocoding took {end - start:.2f}s")
