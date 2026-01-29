"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：taskiq_app.py
功能描述：純非同步任務排程中心，基於 Taskiq 實現，取代傳統 Celery 以獲得更好的非同步效能。
"""
import asyncio
import random
import structlog
import httpx
from typing import List, Dict, Any, Optional

from taskiq import TaskiqScheduler, Context
from taskiq_redis import RedisAsyncResultBackend, ListQueueBroker
from taskiq.schedule_sources import LabelScheduleSource

from core.infra import configure_logging, Database, SourcePlatform, JobLocationPydantic, JobPydantic, CompanyPydantic
from core.infra.config import settings
from core.services import CrawlService, Throttler

# 全域配置
configure_logging()
logger = structlog.get_logger(__name__)

# 初始化 Broker 與 Backend
# 使用 ListQueueBroker 並配合 Redis
redis_backend = RedisAsyncResultBackend(redis_url=settings.REDIS_URL)
broker = ListQueueBroker(
    url=settings.REDIS_URL,
).with_result_backend(redis_backend)

# 初始化排程器
scheduler = TaskiqScheduler(
    broker=broker,
    sources=[LabelScheduleSource(broker)],
)

# --- 任務定義 ---

@broker.task
async def initialize_system() -> None:
    """初始化系統環境、資料庫表結構與標準分類。"""
    from core.services.standard_category_service import StandardCategoryService
    db: Database = Database()
    await db.ensure_initialized()
    await StandardCategoryService().seed_standard_categories()
    await db.close_pool()

@broker.task(schedule=[{"cron": "0 4 * * *"}])
async def orchestrate_crawl() -> None:
    """核心編排任務：同步類別並觸發各平台探勘。"""
    logger.info("orchestration_start")
    from core.categories import fetch_all_categories
    await fetch_all_categories()
    
    for p in SourcePlatform:
        if p == SourcePlatform.PLATFORM_UNKNOWN:
            continue
        await trigger_discovery.kiq(p.value)

@broker.task
async def trigger_discovery(platform_value: str) -> None:
    """針對單一平台展開類別探勘。"""
    svc: CrawlService = CrawlService()
    platform: SourcePlatform = SourcePlatform(platform_value)
    cats: List[Dict[str, Any]] = await svc.discovery.get_category_codes(platform)
    for c in cats:
        # 使用 Taskiq 的延遲發送
        await discover_category.kiq(
            platform_value, 
            c["layer_3_id"], 
            cat_name=c.get("layer_3_name")
        )
    await svc.db.close_pool()

@broker.task
async def discover_category(platform_value: str, cat_id: str, cat_name: Optional[str] = None) -> int:
    """探索分類下的職缺 URL。"""
    svc: CrawlService = CrawlService()
    platform: SourcePlatform = SourcePlatform(platform_value)
    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        p_id: str = cat_name if platform == SourcePlatform.PLATFORM_YOURATOR and cat_name else cat_id
        urls: List[str] = await svc.discovery.discover_category(platform, p_id, client)
        for u in set(urls):
            await process_job.kiq(u, platform_value, cat_id=cat_id)
        await svc.db.close_pool()
        return len(urls)

@broker.task
async def process_job(url: str, platform_value: str, cat_id: Optional[str] = None) -> bool:
    """單一職缺解析管線。"""
    svc: CrawlService = CrawlService()
    platform: SourcePlatform = SourcePlatform(platform_value)
    
    # 注意：Taskiq 隊列隔離可透過不同的 broker 實例或標籤實現
    # 這裡沿用原本的 Throttler 邏輯
    rate, cap = settings.THROTTLE_CONFIG.get(platform_value, settings.THROTTLE_CONFIG["default"])
    
    if not await Throttler().wait_for_slot(platform, rate=rate, capacity=cap):
        await svc.db.close_pool()
        return False
        
    async with httpx.AsyncClient(verify=False, timeout=20.0, follow_redirects=True) as client:
        try:
            res = await svc.process_url(url, platform, client)
            job, comp, loc, raw = res
            
            if not job:
                return False
            
            job.raw_json = raw
            if comp:
                await svc.enrich_company(comp, platform, client)
            
            success: bool = await svc.db.save_full_job_data(job, comp, cat_id, location=loc)
            if success and random.random() < 0.2:
                await analyze_skills.kiq(job.description, platform_value, job.source_id)
            return success
        except Exception as e:
            logger.error("job_processing_failed", url=url, error=str(e))
            return False
        finally:
            await svc.db.close_pool()

@broker.task
async def analyze_skills(text: str, platform_value: str, job_id: str) -> None:
    """利用 Ollama 進行深度技能識別。"""
    db: Database = Database()
    from core.enrichment.skill_extractor import SkillExtractor
    skills: List[Any] = await SkillExtractor().discover_with_ollama(text, platform_value, job_id)
    if skills:
        await db.save_job_skills(skills)
    await db.close_pool()
