"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：verify_checkpoint.py
功能描述：斷點續爬 (Checkpoint) 驗證工具，確保系統能正確識別並跳過當日已完成的職缺分類任務。
主要入口：python test/scripts/verify_checkpoint.py
"""
import asyncio
import structlog
from datetime import datetime
from typing import Optional

from core.infra import Database, SourcePlatform, configure_logging
from core.services import CrawlService

# 初始化日誌
configure_logging()
logger = structlog.get_logger(__name__)

async def verify_resume() -> None:
    """
    執行斷點續爬功能的端到端驗證。
    
    流程：
    1. 選定一個測試用分類 (104 平台)。
    2. 手動在 tb_categories 標記該分類今日已爬取。
    3. 啟動 CrawlService 嘗試爬取該分類。
    4. 驗證是否觸發 "category_skipped_checkpoint"。
    """
    db = Database()
    svc = CrawlService()
    
    # 測試組件
    platform: SourcePlatform = SourcePlatform.PLATFORM_104
    cat_id: str = "2003002019"
    
    print(f"\n--- [SDD] 斷點續爬功能驗證啟動 ---")
    print(f"🚀 將 {platform.value}:{cat_id} 標記為今日已完成...")
    
    try:
        # 標記斷點
        await db.mark_category_as_crawled(platform.value, cat_id)
        
        # 執行爬取
        print(f"🚀 啟動爬取測試，預期此分類應被跳過...")
        await svc.run_platform(platform, target_cat_id=cat_id, max_jobs=1)
        
        print("\n✅ 驗證流程執行完畢，請檢查日誌輸出是否包含 'category_skipped_checkpoint'。")
        
    except Exception as e:
        logger.error("verify_resume_failed", error=str(e))
        print(f"❌ 驗證過程發生錯誤：{e}")
    finally:
        # 優雅關閉資源
        await db.close_pool()
        await svc.db.close_pool()

if __name__ == "__main__":
    try:
        asyncio.run(verify_resume())
    except KeyboardInterrupt:
        pass
