import asyncio
import structlog
from typing import List, Optional
from core.infra import SourcePlatform, Database, configure_logging, BrowserFetcher
from core.services import CrawlService, DiscoveryService

configure_logging()
logger = structlog.get_logger(__name__)

async def run_104_test():
    """
    執行 104 平台測試，驗證修復後的瀏覽器功能。
    """
    db = Database()
    # Skip full ensure_initialized to avoid heavy seeding if possible, 
    # but we need tables. _ensure_db_exists is called by _get_pool.
    # We call ensure_initialized once.
    # await db.ensure_initialized() 
    # 只確保表格存在
    await db.create_tables()
    
    discovery = DiscoveryService()
    svc = CrawlService(db=db, discovery=discovery)
    
    platform = SourcePlatform.PLATFORM_104
    
    try:
        logger.info(f"Processing platform: {platform.value}")
        
        # 2. 獲取分類
        categories = await discovery.get_category_codes(platform)
        if not categories:
            logger.warning(f"No categories found for {platform.value}, skipping.")
            return
        
        # 3. 選擇一個分類
        target_cat = categories[0]
        cat_id = target_cat["layer_3_id"]
        cat_name = target_cat.get("layer_3_name", "Unknown")
        
        logger.info(f"Selected category: {cat_name} (ID: {cat_id})")
        
        # 4. 執行爬取任務
        await svc.run_platform(platform, max_jobs=5, target_cat_id=cat_id)
        
        # 等待背景增強任務完成 (因 CrawlService 使用非同步 create_task)
        await asyncio.sleep(15)
        
    except Exception as e:
        logger.error(f"Sample test failed: {str(e)}", exc_info=True)
    finally:
        await db.close_pool()
        await BrowserFetcher.close_browser()

if __name__ == "__main__":
    asyncio.run(run_104_test())
