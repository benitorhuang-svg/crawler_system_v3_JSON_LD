import asyncio
import structlog
import argparse
from typing import List, Optional
from core.infra import SourcePlatform, Database, configure_logging, BrowserFetcher
from core.services import CrawlService, DiscoveryService

configure_logging()
logger = structlog.get_logger(__name__)

async def run_sample_test(limit: int):
    """
    執行小樣測試：每個平台選擇一個職類，蒐集指定數量的資料並存入 SQL。
    """
    db = Database()
    discovery = DiscoveryService()
    svc = CrawlService(db=db, discovery=discovery)
    
    platforms = [
        SourcePlatform.PLATFORM_104,
        SourcePlatform.PLATFORM_1111,
        SourcePlatform.PLATFORM_CAKERESUME,
        SourcePlatform.PLATFORM_YES123,
        SourcePlatform.PLATFORM_YOURATOR
    ]
    
    try:
        # 1. 初始化資料庫
        logger.info("Initializing database...")
        await db.ensure_initialized()
        
        for platform in platforms:
            logger.info(f"Processing platform: {platform.value}")
            
            # 2. 獲取分類
            categories = await discovery.get_category_codes(platform)
            if not categories:
                logger.warning(f"No categories found for {platform.value}, skipping.")
                continue
            
            # 3. 選擇第一個分類 (通常是 IT 或熱門分類)
            target_cat = categories[0]
            cat_id = target_cat["layer_3_id"]
            cat_name = target_cat.get("layer_3_name", "Unknown")
            
            logger.info(f"Selected category: {cat_name} (ID: {cat_id})")
            
            # 4. 執行爬取任務
            await svc.run_platform(platform, max_jobs=limit, target_cat_id=cat_id)
            
            logger.info(f"Finished processing {platform.value}")

        logger.info("Sample test completed successfully.")
        
    except Exception as e:
        logger.error(f"Sample test failed: {str(e)}", exc_info=True)
    finally:
        await db.close_pool()
        await BrowserFetcher.close_browser()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10, help="Max jobs per platform")
    args = parser.parse_args()
    asyncio.run(run_sample_test(args.limit))
