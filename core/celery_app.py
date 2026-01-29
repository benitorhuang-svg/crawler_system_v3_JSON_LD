"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：celery_app.py
功能描述：非同步任務排程中心，負責分散式爬蟲的生命週期調度與頻率控管。
主要入口：由 Celery Worker 啟動。
"""
import asyncio
import os
import random
import structlog
import httpx
from typing import Optional, Any, List, Dict, Tuple, Union
from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_ready
from celery.app.task import Task

from core.infra.config import settings
from core.infra import configure_logging, Database, SourcePlatform, JobLocationPydantic, JobPydantic, CompanyPydantic
from core.services import CrawlService, Throttler

# 全域配置
configure_logging()
logger: structlog.BoundLogger = structlog.get_logger(__name__)

# 各平台速率限額從 settings 獲取
THROTTLE_CONFIG = settings.THROTTLE_CONFIG

# Celery 應用初始化
app: Celery = Celery("crawler_v3", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

def route_task(name: str, *args: Any, **kwargs: Any) -> Optional[Dict[str, str]]:
    """
    根據任務性質動態路由至專屬隊列，實現資源隔離。
    相容 Celery 5.x 路由簽章：(name, args, kwargs, options, task=None)
    """
    if name.startswith("core.tasks."):
        # 提取 task_kwargs (args 是 (task_args, task_kwargs, options))
        task_kwargs: Dict[str, Any] = args[1] if len(args) > 1 else {}
        task_args: Tuple = args[0] if len(args) > 0 else ()
        
        platform: Optional[str] = None
        if "platform_value" in task_kwargs:
            platform = task_kwargs["platform_value"]
        elif task_args:
            # 假設第一個參數為 URL 或平台字串的情況
            if isinstance(task_args[0], str) and task_args[0].startswith("platform_"):
                platform = task_args[0]
            elif len(task_args) > 1 and isinstance(task_args[1], str) and task_args[1].startswith("platform_"):
                platform = task_args[1]
        
        if platform:
            name_clean: str = platform.replace("platform_", "")
            return {"queue": f"q_{name_clean}"}
            
    return {"queue": "q_default"}

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Taipei",
    enable_utc=True,
    task_default_queue="q_default",
    task_routes=("core.celery_app.route_task",),
    beat_schedule={
        "daily-crawl-orchestration": {
            "task": "core.tasks.orchestrate_crawl",
            "schedule": crontab(minute=0, hour=4),
        },
    },
)

def run_async(coro: Any) -> Any:
    """協程運行輔助工具。"""
    try:
        loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

# --- 任務定義 ---

@app.task(name="core.tasks.initialize_system")
def initialize_system() -> None:
    """初始化系統環境、資料庫表結構與標準分類。"""
    async def _do() -> None:
        db: Database = Database()
        await db.ensure_initialized()
        await db.close_pool()
    run_async(_do())

@app.task(name="core.tasks.orchestrate_crawl")
def orchestrate_crawl() -> None:
    """核心編排任務：同步類別並觸發各平台探勘。"""
    logger.info("orchestration_start")
    from core.categories import fetch_all_categories
    run_async(fetch_all_categories())
    
    for p in SourcePlatform:
        if p == SourcePlatform.PLATFORM_UNKNOWN:
            continue
        app.send_task("core.tasks.trigger_discovery", args=[p.value])

@app.task(name="core.tasks.trigger_discovery")
def trigger_discovery(platform_value: str) -> None:
    """針對單一平台展開類別探勘。"""
    async def _do() -> None:
        svc: CrawlService = CrawlService()
        platform: SourcePlatform = SourcePlatform(platform_value)
        cats: List[Dict[str, Any]] = await svc.discovery.get_category_codes(platform)
        for c in cats:
            app.send_task("core.tasks.discover_category", 
                          args=[platform_value, c["layer_3_id"]],
                          kwargs={"cat_name": c.get("layer_3_name")},
                          countdown=random.randint(0, 300))
        await svc.db.close_pool()
    run_async(_do())

@app.task(name="core.tasks.discover_category", autoretry_for=(Exception,), max_retries=3)
def discover_category(platform_value: str, cat_id: str, cat_name: Optional[str] = None) -> int:
    """探索分類下的職缺 URL。"""
    async def _do() -> int:
        svc: CrawlService = CrawlService()
        platform: SourcePlatform = SourcePlatform(platform_value)
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            # Yourator 支援名稱搜索
            p_id: str = cat_name if platform == SourcePlatform.PLATFORM_YOURATOR and cat_name else cat_id
            urls: List[str] = await svc.discovery.discover_category(platform, p_id, client)
            for u in set(urls):
                app.send_task("core.tasks.process_job", 
                              args=[u, platform_value], 
                              kwargs={"cat_id": cat_id},
                              countdown=random.randint(0, 60))
            await svc.db.close_pool()
            return len(urls)
    return run_async(_do())

@app.task(name="core.tasks.process_job", bind=True, max_retries=5)
def process_job(self: Task, url: str, platform_value: str, cat_id: Optional[str] = None) -> bool:
    """單一職缺解析管線。"""
    async def _do() -> bool:
        svc: CrawlService = CrawlService()
        platform: SourcePlatform = SourcePlatform(platform_value)
        rate, cap = THROTTLE_CONFIG.get(platform_value, THROTTLE_CONFIG["default"])
        
        # 限流檢查
        if not await Throttler().wait_for_slot(platform, rate=rate, capacity=cap):
            await svc.db.close_pool()
            return False
            
        async with httpx.AsyncClient(verify=False, timeout=20.0, follow_redirects=True) as client:
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
                
                # 持久化
                success: bool = await svc.db.save_full_job_data(job, comp, cat_id, location=loc)
                if success:
                    # 技能提取 (AI 異步分析)
                    if random.random() < 0.2:
                        app.send_task("core.tasks.analyze_skills", args=[job.description, platform_value, job.source_id])
                return success
            except Exception as e:
                logger.error("job_processing_failed", url=url, error=str(e))
                raise self.retry(exc=e, countdown=60)
            finally:
                await svc.db.close_pool()
    return run_async(_do())

@app.task(name="core.tasks.analyze_skills", queue="q_ollama")
def analyze_skills(text: str, platform_value: str, job_id: str) -> None:
    """利用 Ollama 進行深度技能識別。"""
    async def _do() -> None:
        db: Database = Database()
        from core.enrichment.skill_extractor import SkillExtractor
        skills: List[Any] = await SkillExtractor().discover_with_ollama(text, platform_value, job_id)
        if skills:
            await db.save_job_skills(skills)
        await db.close_pool()
    run_async(_do())

@worker_ready.connect
def on_start(sender: Any, **kwargs: Any) -> None:
    """啟動時自動初始化。"""
    logger.info("worker_ready_hook")
    initialize_system.delay()

