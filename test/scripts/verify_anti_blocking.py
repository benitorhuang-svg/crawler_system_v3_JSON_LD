"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：verify_anti_blocking.py
功能描述：反爬蟲機制驗證工具，測試智能路由與爬取服務是否能成功繞過封鎖並正確提取資料。
主要入口：python test/scripts/verify_anti_blocking.py
"""
import asyncio
import httpx
import structlog
from typing import Optional, Tuple

from core.infra import SourcePlatform, configure_logging, BrowserFetcher, JobPydantic, CompanyPydantic, LocationPydantic
from core.services import CrawlService

# 初始化日誌
configure_logging()
logger = structlog.get_logger(__name__)

async def test_anti_blocking() -> None:
    """
    執行反爬蟲機制測試。
    
    流程：
    1. 初始化 CrawlService。
    2. 選定一個具備挑戰性的職缺 URL。
    3. 透過 CrawlService 執行完整處理流（含 BrowserFetcher 輔助）。
    4. 驗證提取結果。
    """
    service = CrawlService()
    platform: SourcePlatform = SourcePlatform.PLATFORM_104
    
    # 測試 URL
    test_url: str = "https://www.104.com.tw/job/8uq5m"
    
    print(f"\n🚀 啟動智能繞過封鎖測試：{test_url}")
    
    async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=30.0) as client:
        try:
            # 執行 URL 處理
            result: Tuple[Optional[JobPydantic], Optional[CompanyPydantic], Optional[LocationPydantic], str] = \
                await service.process_url(test_url, platform, client)
            
            job, company, loc, _ = result
            
            if job:
                print(f"✅ 提取成功！")
                print(f"   - 職稱：{job.title}")
                print(f"   - 公司：{company.name if company else '未公開'}")
                print(f"   - 地區：{loc.district if loc else '未知'}")
            else:
                print("❌ 提取失敗：未能解析出職缺資料。")
                
        except Exception as e:
            logger.error("anti_blocking_test_failed", error=str(e))
            print(f"❌ 測試過程發生異常：{e}")
        finally:
            # 確保瀏覽器資源被釋放
            await BrowserFetcher.close_browser()
            # 關閉資料庫連接
            await service.db.close_pool()

if __name__ == "__main__":
    try:
        asyncio.run(test_anti_blocking())
    except KeyboardInterrupt:
        pass
