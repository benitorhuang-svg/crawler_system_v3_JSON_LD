"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：verify_sample_test.py
功能描述：跨平台樣本測試工具，自動挑選各平台的一個類別執行小規模（5 筆）爬取測試，驗證系統整合狀況。
主要入口：python test/scripts/verify_sample_test.py
"""
import asyncio
import structlog
from typing import List, Dict, Any, Optional

from core.infra import SourcePlatform, configure_logging, Database
from core.services import CrawlService
from core.services.discovery_service import DiscoveryService

# 初始化日誌
configure_logging()
logger = structlog.get_logger(__name__)

async def run_sample_test() -> None:
    """
    執行跨平台樣本爬取測試。
    
    流程：
    1. 遍歷所有支援的平台。
    2. 從資料庫獲取可用分類列表。
    3. 自動挑選一個特定索引的分類。
    4. 啟動 CrawlService 執行限額爬取。
    """
    crawl_service = CrawlService()
    discovery_service = DiscoveryService()
    
    platforms: List[SourcePlatform] = [
        SourcePlatform.PLATFORM_104,
        SourcePlatform.PLATFORM_1111,
        SourcePlatform.PLATFORM_CAKERESUME,
        SourcePlatform.PLATFORM_YES123,
        SourcePlatform.PLATFORM_YOURATOR
    ]

    print("\n--- [SDD] 跨平台樣本測試啟動 ---")

    for platform in platforms:
        logger.info("sample_test_platform_start", platform=platform.value)
        
        # 1. 獲取分類清單
        categories: List[Dict[str, Any]] = await discovery_service.get_category_codes(platform)
        
        if not categories:
            logger.warning("sample_test_no_categories", platform=platform.value)
            continue
            
        logger.debug("sample_test_categories_available", platform=platform.value, count=len(categories))
        
        # 2. 挑選目標分類 (優先選取第 15 個以增加樣本多樣性)
        target_index: int = 14 if len(categories) >= 15 else 0
        target_cat: Dict[str, Any] = categories[target_index]
        cat_id: str = str(target_cat['layer_3_id'])
        cat_name: str = str(target_cat.get('layer_3_name', 'Unknown'))
        
        print(f" [+] 測試平台：{platform.value} | 目標分類：{cat_name} ({cat_id})")
        
        # 3. 執行限額爬取
        try:
            await crawl_service.run_platform(
                platform, 
                max_jobs=5, 
                target_cat_id=cat_id,
                target_cat_name=cat_name
            )
            print(f"     -> {platform.value} 樣本測試完成。")
        except Exception as e:
            logger.error("sample_test_platform_failed", platform=platform.value, error=str(e))
            print(f"     -> {platform.value} 測試失敗：{e}")

    # 4. 清理資料庫連接
    await crawl_service.db.close_pool()
    print("\n--- [SDD] 樣本測試任務結束 ---")

if __name__ == "__main__":
    try:
        asyncio.run(run_sample_test())
    except KeyboardInterrupt:
        pass
