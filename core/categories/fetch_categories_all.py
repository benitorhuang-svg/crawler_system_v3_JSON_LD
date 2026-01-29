"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：fetch_categories_all.py
功能描述：全平台類別同步編排器，負責協調整個系統的職缺類別資料同步任務。
主要入口：由 core.celery_app 或管理腳本 (manage_db.py) 調用。
"""
import asyncio
from typing import List, Tuple, Any, Dict, Callable, Awaitable
import structlog
from core.infra import configure_logging, SourcePlatform
from core.categories import (
    fetch_104_categories,
    fetch_1111_categories,
    fetch_cakeresume_categories,
    fetch_yes123_categories,
    fetch_yourator_categories,
)

logger = structlog.get_logger(__name__)

async def fetch_all_categories() -> None:
    """
    全平台類別同步主程序。
    
    採用並行模式執行各平台的抓取任務，並輸出整合報表。
    """
    logger.info("fetch_categories_all_start")
    
    # 定義平台與對應抓取函數
    tasks: List[Tuple[SourcePlatform, Callable[[], Awaitable[int]]]] = [
        (SourcePlatform.PLATFORM_104, fetch_104_categories),
        (SourcePlatform.PLATFORM_1111, fetch_1111_categories),
        (SourcePlatform.PLATFORM_CAKERESUME, fetch_cakeresume_categories),
        (SourcePlatform.PLATFORM_YES123, fetch_yes123_categories),
        (SourcePlatform.PLATFORM_YOURATOR, fetch_yourator_categories),
    ]
    
    print(f"{'平台':<20} | {'狀態':<10} | {'數量':<10}")
    print("-" * 45)
    
    async def fetch_one(platform: SourcePlatform, func: Callable[[], Awaitable[int]]) -> Tuple[str, str, int]:
        name: str = platform.value
        logger.info("platform_category_fetch_start", platform=name)
        try:
            count: int = await func()
            status: str = "成功" if count > 0 else "空/失敗"
            logger.info("platform_category_fetch_finished", platform=name, count=count)
            return name, status, count
        except Exception as e:
            logger.error("platform_category_fetch_failed", platform=name, error=str(e))
            return name, f"失敗: {str(e)[:20]}", 0

    # 扇出執行
    results: List[Tuple[str, str, int]] = await asyncio.gather(
        *[fetch_one(p, f) for p, f in tasks]
    )
    
    # 輸出報表
    for name, status, count in results:
        print(f"{name:<20} | {status:<10} | {count:<10}")
            
    logger.info("fetch_categories_all_finished", summary=results)

if __name__ == "__main__":
    configure_logging()
    asyncio.run(fetch_all_categories())

