"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：tasks.py
功能描述：Taskiq 非同步任務定義，作為 Celery 之外的高性能任務替代方案。
主要入口：由 Taskiq Worker 啟動。
"""
import asyncio
import httpx
import structlog
from typing import List, Optional, Dict, Any, Set
from taskiq import TaskiqScheduler
from taskiq_redis import RedisAsyncResultBackend, ListQueueBroker
from taskiq.schedule_sources import LabelScheduleSource

from core.infra import Database, SourcePlatform, configure_logging, JobPydantic, CompanyPydantic, JobLocationPydantic
from core.services import CrawlService

# 初始化日誌
configure_logging()
logger = structlog.get_logger(__name__)

# Taskiq 基礎配置
REDIS_URL: str = "redis://localhost:6379"
result_backend = RedisAsyncResultBackend(redis_url=REDIS_URL)
broker: ListQueueBroker = ListQueueBroker(redis_url=REDIS_URL).with_result_backend(result_backend)

# 排程器配置
scheduler: TaskiqScheduler = TaskiqScheduler(
    broker=broker,
    sources=[LabelScheduleSource(broker)],
)

@broker.task
async def process_job_task(url: str, platform_value: str) -> bool:
    """
    單一職缺處理流：抓取 -> 提取 -> 存儲。
    
    Args:
        url (str): 職缺目標連結。
        platform_value (str): 平台枚舉字串。
        
    Returns:
        bool: 處理是否成功。
    """
    platform: SourcePlatform = SourcePlatform(platform_value)
    svc: CrawlService = CrawlService()
    
    logger.info("task_process_start", url=url, platform=platform_value)
    
    async with httpx.AsyncClient(verify=False, timeout=30.0, follow_redirects=True) as client:
        try:
            res: tuple = await svc.process_url(url, platform, client)
            job: Optional[JobPydantic] = res[0]
            comp: Optional[CompanyPydantic] = res[1]
            loc: Optional[JobLocationPydantic] = res[2]
            raw: Optional[str] = res[3]
            
            if not job:
                return False
            
            job.raw_json = raw
            if comp:
                await svc.enrich_company(comp, platform, client)
            
            # 存儲資料
            success: bool = await svc.db.save_full_job_data(job, comp, location=loc)
            return success
        except Exception as e:
            logger.error("task_process_failed", url=url, error=str(e))
            return False
        finally:
            await svc.db.close_pool()

@broker.task
async def discover_category_task(platform_value: str, cat_id: str, limit: int = 50) -> int:
    """
    分類發現任務：搜尋特定分類連結並扇出處理單一職缺任務。
    
    Args:
        platform_value (str): 平台標識。
        cat_id (str): 分類 ID。
        limit (int): 抓取上限。
        
    Returns:
        int: 發現的職缺總數。
    """
    platform: SourcePlatform = SourcePlatform(platform_value)
    svc: CrawlService = CrawlService()
    
    logger.info("task_discovery_start", platform=platform_value, cat=cat_id)
    
    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        try:
            urls: List[str] = await svc.discovery.discover_category(platform, cat_id, client, limit=limit)
            for u in set(urls):
                await process_job_task.kiq(u, platform_value)
            return len(urls)
        except Exception as e:
            logger.error("task_discovery_failed", cat=cat_id, error=str(e))
            return 0
        finally:
            await svc.db.close_pool()

@broker.task(schedule=[{"cron": "0 * * * *"}])
async def trigger_platform_task(platform_value: str) -> int:
    """
    平台排程觸發任務，負責獲取該平台所有類別並排入發現隊列。
    
    Args:
        platform_value (str): 平台標識。
        
    Returns:
        int: 觸發的類別總數。
    """
    svc: CrawlService = CrawlService()
    platform: SourcePlatform = SourcePlatform(platform_value)
    
    try:
        cats: List[Dict[str, Any]] = await svc.discovery.get_category_codes(platform)
        for c in cats:
            await discover_category_task.kiq(platform_value, c["layer_3_id"])
        return len(cats)
    finally:
        await svc.db.close_pool()
