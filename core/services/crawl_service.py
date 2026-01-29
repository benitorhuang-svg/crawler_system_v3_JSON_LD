"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：crawl_service.py
功能描述：核心爬蟲調度服務，負責協調職缺探索、網頁抓取、實體解析、AI 自癒與資料持久化流程。
主要入口：由 core.tasks 或主程序調用。
"""
import asyncio
import httpx
import structlog
import json
import time
import random
import hashlib
from typing import List, Tuple, Any, Optional, Dict, Union, AsyncGenerator
from pathlib import Path
from bs4 import BeautifulSoup
from datetime import datetime

# 核心基礎設施與模型
from core.infra.database import Database
from core.infra.redis_client import RedisClient
from core.infra.schemas import (
    SourcePlatform, JobPydantic, CompanyPydantic, 
    JobLocationPydantic, JobSkillExtractedPydantic, SalaryType
)
from core.infra.browser_fetcher import BrowserFetcher
from core.infra.config import settings
from core.adapters import AdapterFactory
from core.enrichment.geocoder import Geocoder
from core.enrichment.skill_extractor import SkillExtractor
from core.enrichment.ollama_client import OllamaClient
from core.services.discovery_service import DiscoveryService
from core.services.jsonld_extractor import JsonLdExtractor
from core.infra.metrics import (
    CRAWL_REQUEST_TOTAL, EXTRACTION_COUNT_TOTAL, 
    REQUEST_LATENCY_SECONDS, AI_HEAL_REQUESTS_TOTAL
)
from core.schemas.validator import SchemaValidator

# 代理與環境配置
PROXIES: List[Optional[str]] = [None]
USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
]

# 設置結構化日誌
logger = structlog.get_logger(__name__)

class CrawlService:
    """
    職缺抓取生命週期調度器。
    實作探索 (Discovery) -> 抓取 (Fetch) -> 解析 (Parse) -> 增強 (Enrich) -> 存儲 (Persist) 完整管線。
    整合 SDD 自癒機制以應對網頁結構變更。
    """
    
    def __init__(
        self,
        db: Optional[Database] = None,
        discovery: Optional[DiscoveryService] = None,
        extractor: Optional[JsonLdExtractor] = None,
        validator: Optional[SchemaValidator] = None,
        geocoder: Optional[Geocoder] = None,
        skill_extractor: Optional[SkillExtractor] = None
    ) -> None:
        """初始化核心組件，支援依賴注入以符合 SOLID 原則。"""
        self.db = db or Database()
        self.discovery = discovery or DiscoveryService()
        self.extractor = extractor or JsonLdExtractor()
        self.validator = validator or SchemaValidator()
        self.geocoder = geocoder or Geocoder()
        self.skill_extractor = skill_extractor or SkillExtractor()
        self.redis = RedisClient().get_client()
        
        # 內存快取與 AI 調控
        self._company_cache: Dict[str, CompanyPydantic] = {}
        self._max_company_cache: int = 1000
        self._ai_failure_count: int = 0
        self._ai_isolated_until: float = 0.0
        
        # 配置參數 (來自 settings)
        self.AI_FAILURE_THRESHOLD = settings.RETRY_COUNT
        self.ENABLE_AI_HEALING = True
        self.HTML_CACHE_TTL = 3600

    # --- 私有輔助方法 ---

    def _get_headers(self, platform: SourcePlatform) -> Dict[str, str]:
        """產出符合特定平台特徵的 HTTP Headers。"""
        ua: str = random.choice(USER_AGENTS)
        if platform == SourcePlatform.PLATFORM_104:
            ua = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
        headers: Dict[str, str] = {"User-Agent": ua}
        if platform == SourcePlatform.PLATFORM_YES123:
            headers["Referer"] = "https://www.yes123.com.tw/"
        return headers

    def _get_proxy(self) -> Optional[str]:
        """取得隨機代理。"""
        return random.choice(PROXIES) if PROXIES else None


    # --- 核心業務邏輯 ---

    # --- 核心入口 (Core Entry Points) ---

    async def crawl_job(self, platform: SourcePlatform, url: str) -> Optional[JobPydantic]:
        """
        單一職缺抓取入口點（用於手動觸發或系統集成）。
        執行完整的 抓取 -> 解析 -> 增強 -> 持久化 流程。
        """
        logger.info("single_job_crawl_started", platform=platform.value, url=url)
        await self.db.ensure_initialized()
        
        async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=20.0) as client:
            job, comp, loc, raw_json = await self.process_url(url, platform, client)
            if not job:
                logger.warning("single_job_crawl_failed", url=url)
                return None
            
            # 標準補全與持久化
            job.raw_json = raw_json
            if comp: 
                await self.enrich_company(comp, platform, client)
                job.company_source_id = comp.source_id
            
            success = await self.db.save_full_job_data(job, comp, None, location=loc)
            if success:
                # 異步執行選配增強
                skills = self.skill_extractor.extract(job.description or "", platform.value, job.source_id)
                if skills: await self.db.save_job_skills(skills)
                
                if not loc and job.address:
                    # 傳遞縣市與區域資訊以利回退搜尋
                    lat, lon, fmt = await self.geocoder.geocode(job.address, city=job.region, district=job.district)
                    if lat and lon:
                        await self.db.save_job_location(JobLocationPydantic(
                            platform=platform.value, job_source_id=job.source_id,
                            latitude=lat, longitude=lon, formatted_address=fmt or job.address, provider="OSM"
                        ))
                return job
        return None

    # --- 核心業務邏輯：單個職缺處理鏈 ---

    async def _process_url_and_save(
        self, 
        platform: SourcePlatform, 
        url: str, 
        client: httpx.AsyncClient, 
        cat_id: Optional[str] = None, 
        cat_name: Optional[str] = None
    ) -> bool:
        """
        封裝單個職缺的 抓取 -> 解析 -> 增強 -> 持久化 完整管線。
        """
        try:
            job, comp, loc, raw_json = await self.process_url(url, platform, client)
            if not job:
                return False
            
            # 直接使用分類名稱 (層級 3)
            if cat_name:
                job.layer_category_name = cat_name
            
            # 增強與持久化
            job.raw_json = raw_json
            if cat_name: job.industry = cat_name
            if comp: 
                await self.enrich_company(comp, platform, client)
                job.company_source_id = comp.source_id
            
            # 存儲
            success: bool = await self.db.save_full_job_data(job, comp, cat_id, location=loc)
            if success:
                # 異步執行選配增強 (不阻塞主流程)
                asyncio.create_task(self._perform_late_enrichment(job, platform, loc))
                return True
        except Exception as e:
            logger.error("job_pipeline_error", url=url, error=str(e))
        return False

    async def _perform_late_enrichment(self, job: JobPydantic, platform: SourcePlatform, loc: Optional[JobLocationPydantic]) -> None:
        """執行非同步的選配增強任務 (技能提取、地圖座標)。"""
        try:
            # 1. 技能提取
            skills: List[JobSkillExtractedPydantic] = self.skill_extractor.extract(job.description or "", platform.value, job.source_id)
            if skills: await self.db.save_job_skills(skills)
            
            # 2. 地理座標 (僅在原生無座標時採用 OSM 地址轉換)
            if not loc and job.address:
                logger.info("geocoding_fallback_osm", job=job.title, address=job.address)
                lat, lon, fmt = await self.geocoder.geocode(job.address, city=job.region, district=job.district)
                if lat and lon:
                    await self.db.save_job_location(JobLocationPydantic(
                        platform=platform.value, job_source_id=job.source_id,
                        latitude=lat, longitude=lon, formatted_address=fmt or job.address, provider="OSM"
                    ))
            elif loc:
                logger.debug("skipping_osm_geocoding_native_exists", job=job.title)
        except Exception as e:
            logger.error("late_enrichment_failed", job_id=job.source_id, error=str(e))

    # --- 核心業務階段 (Core Business Phases) ---

    async def heal_with_ai(self, html: str, platform: SourcePlatform, original_title: str, url: str) -> Tuple[Optional[JobPydantic], Optional[CompanyPydantic]]:
        """
        利用 AI 進行語義提取補償 (Self-Healing)。
        """
        if not self.ENABLE_AI_HEALING or time.time() < self._ai_isolated_until:
            return None, None

        ollama = OllamaClient()
        try:
            ai_data = await ollama.extract_job_from_html(html)
            if not ai_data or not ai_data.get("title"):
                return None, None

            # 驗證標題相似度
            import Levenshtein
            sim = 1 - (Levenshtein.distance(original_title.lower(), ai_data["title"].lower()) / max(len(original_title), len(ai_data["title"]), 1))
            if sim < 0.4:
                return None, None

            adapter = AdapterFactory.get_adapter(platform)
            mock_ld = self._create_mock_ld(ai_data)
            
            job = adapter.map_to_job(mock_ld, url, html=html)
            company = adapter.map_to_company(mock_ld, html)
            
            if job:
                job.data_source_layer = "L2"
                if company: company.data_source_layer = "L2"
            
            return job, company

        except Exception as e:
            self._handle_ai_failure(e)
            return None, None

    def _create_mock_ld(self, ai_data: Dict[str, Any]) -> Dict[str, Any]:
        """建立構造用的 JSON-LD。"""
        return {
            "@type": "JobPosting",
            "title": ai_data["title"],
            "description": ai_data.get("description"),
            "hiringOrganization": {"name": ai_data.get("company_name")},
            "jobLocation": {"address": {"streetAddress": ai_data.get("address")}},
            "baseSalary": {
                "value": {
                    "minValue": ai_data.get("salary_min"),
                    "maxValue": ai_data.get("salary_max"),
                    "unitText": ai_data.get("salary_type")
                }
            }
        }

    def _handle_ai_failure(self, error: Exception) -> None:
        """處理 AI 提取失敗並記錄隔離狀態。"""
        self._ai_failure_count += 1
        if self._ai_failure_count >= self.AI_FAILURE_THRESHOLD:
            self._ai_isolated_until = time.time() + self.AI_ISOLATION_WINDOW
            logger.error("ai_service_isolated", error=str(error))

    async def process_url(self, url: str, platform: SourcePlatform, client: httpx.AsyncClient) -> Tuple[Optional[JobPydantic], Optional[CompanyPydantic], Optional[JobLocationPydantic], str]:
        """
        處理單一網址：執行抓取、提取、校驗與自癒。
        """
        start_t = time.perf_counter()
        html, http_ok = await self._fetch_html_with_fallback(url, platform, client)
        
        if not html:
            CRAWL_REQUEST_TOTAL.labels(platform=platform.value, status="failed").inc()
            return None, None, None, ""

        CRAWL_REQUEST_TOTAL.labels(platform=platform.value, status="success").inc()
        job, comp, loc, raw_json, extract_ok = await self._extract_entities(url, platform, html)
        
        latency = int((time.perf_counter() - start_t) * 1000)
        await self.db.record_platform_health(platform.value, http_ok, extract_ok, latency, None)
        
        return job, comp, loc, raw_json

    async def _fetch_html_with_fallback(self, url: str, platform: SourcePlatform, client: httpx.AsyncClient) -> Tuple[str, bool]:
        """抓取 HTML，支援 Redis 快取與瀏覽器降級。"""
        cache_key = f"crawl:html:{hashlib.md5(url.encode()).hexdigest()}"
        
        # 0. 快取檢查
        if self.redis:
            cached = self.redis.get(cache_key)
            if cached:
                return cached.decode("utf-8") if isinstance(cached, bytes) else cached, True

        # 1. HTTP 抓取
        html = ""
        try:
            for _ in range(2):
                resp = await client.get(url, headers=self._get_headers(platform), timeout=15.0)
                if resp.status_code in [403, 401]: break
                resp.raise_for_status()
                html = resp.text
                break
        except Exception:
            pass

        # 2. 瀏覽器降級
        if not html:
            fetcher = BrowserFetcher()
            html = await fetcher.fetch(url, proxy=self._get_proxy())

        if html and self.redis:
            self.redis.setex(cache_key, self.HTML_CACHE_TTL, html)
            
        return html, bool(html)

    async def _extract_entities(self, url: str, platform: SourcePlatform, html: str) -> Tuple[Optional[JobPydantic], Optional[CompanyPydantic], Optional[JobLocationPydantic], str, bool]:
        """從 HTML 提取職缺與公司資訊。"""
        soup = BeautifulSoup(html, "html.parser")
        pg_title = soup.title.string.strip() if soup.title else ""
        ld_list = self.extractor.extract(html)
        for ld in ld_list:
            if isinstance(ld, dict):
                ld["_url"] = url
        
        if not ld_list:
            ld_list = [{"@type": "JobPosting", "_url": url, "_injected_title": pg_title}]
        
        job_ld = self.extractor.find_job_posting(ld_list)
        adapter = AdapterFactory.get_adapter(platform)
        
        job = adapter.map_to_job(job_ld, url, html=html) if job_ld else None
        comp = adapter.map_to_company(job_ld or ld_list[0], html) if ld_list else None

        # AI 自癒
        if (not job or not job.title) and self.ENABLE_AI_HEALING:
            job, comp = await self.heal_with_ai(html, platform, pg_title, url)

        if not job:
            return None, None, None, "", False

        # 驗證
        job_data = job.model_dump(mode='json')
        await self.validator.validate_job(job_data)
        
        # 地理資訊
        loc = self._extract_native_location(job, job_ld, adapter, platform, html)
        
        return job, comp, loc, json.dumps(job_ld or {}, ensure_ascii=False), True

    def _extract_native_location(self, job: JobPydantic, ld: Optional[Dict], adapter: Any, platform: SourcePlatform, html: str) -> Optional[JobLocationPydantic]:
        """提取 JSON-LD 中的原生地址資訊。"""
        # 座標處理
        lat = adapter.get_latitude(ld, html=html) if ld else None
        lon = adapter.get_longitude(ld, html=html) if ld else None
        if lat and lon:
            return JobLocationPydantic(
                platform=platform.value,
                job_source_id=job.source_id,
                latitude=lat,
                longitude=lon,
                formatted_address=job.address,
                provider="NATIVE"
            )
        return None

    async def enrich_company(self, company: CompanyPydantic, platform: SourcePlatform, client: httpx.AsyncClient) -> None:
        """從公司首頁補充詳細資訊。"""
        if not company or not company.company_url: return
        
        cache_key: str = f"{platform.value}:{company.source_id}"
        if cache_key in self._company_cache:
            c: CompanyPydantic = self._company_cache[cache_key]
            company.capital = company.capital or c.capital
            company.employee_count = company.employee_count or c.employee_count
            company.description = company.description or c.description
            return

        try:
            html: str = ""
            # 104 是 SPA，必須使用瀏覽器渲染以獲取完整資訊
            if platform in [SourcePlatform.PLATFORM_104, SourcePlatform.PLATFORM_CAKERESUME]:
                logger.info("enrich_company_browser_fallback", platform=platform.value, url=company.company_url)
                fetcher = BrowserFetcher()
                html = await fetcher.fetch(company.company_url, proxy=self._get_proxy())
            else:
                resp: httpx.Response = await client.get(company.company_url, headers=self._get_headers(platform), timeout=10.0)
                if resp.status_code == 200:
                    html = resp.text

            if html:
                adapter = AdapterFactory.get_adapter(platform)
                # 提供基本上下文以通過 Adapter 的必填欄位檢查
                context_ld = {
                    "hiringOrganization": {
                        "name": company.name,
                        "url": company.company_url,
                        "sameAs": company.company_url
                    },
                    "capital": company.capital,
                    "numberOfEmployees": company.employee_count
                }
                enriched: Optional[CompanyPydantic] = adapter.map_to_company(context_ld, html)
                if enriched:
                    # SDD規範：「寧可空白，不可錯誤」
                    # 若 HTML 明確指示欄位應為 NULL（如「暫不公開」），優先採用 NULL
                    company.capital = enriched.capital if enriched.capital is not None else company.capital
                    company.employee_count = enriched.employee_count if enriched.employee_count is not None else company.employee_count
                    company.description = enriched.description or company.description
                    company.address = enriched.address or company.address
                    company.company_web = enriched.company_web or company.company_web
                    company.data_source_layer = "L2"
                    
                    # 簡易 LRU：超限則清空
                    if len(self._company_cache) >= self._max_company_cache:
                        self._company_cache.clear()
                    self._company_cache[cache_key] = company
        except Exception as e:
            logger.warn("enrich_company_failed", url=company.company_url, error=str(e))

    async def run_platform(
        self, 
        platform: SourcePlatform, 
        max_jobs: int = 20, 
        target_cat_id: Optional[str] = None,
        resume: bool = True
    ) -> None:
        """
        執行特定平台的爬取流水線（逐個職業類別順序執行）。
        
        Args:
            platform (SourcePlatform): 目標平台。
            max_jobs (int): 每個分類的職缺上限。
            target_cat_id (Optional[str]): 若指定，只爬取該分類。
            resume (bool): 若 True，跳過已完成的分類；若 False，重新處理全部。
        """
        logger.info("pipeline_started", platform=platform.value, category_mode="sequential", resume=resume, target_cat=target_cat_id)
        
        categories: List[Dict[str, Any]] = await self.discovery.get_category_codes(platform, target_id=target_cat_id)
        if not categories:
            logger.warning("no_categories_found", platform=platform.value)
            return
        
        # ✅ 若 resume=True，過濾掉已完成的分類
        if resume and not target_cat_id:
            crawled_cats = await self.db.get_crawled_categories(platform.value)
            categories = [cat for cat in categories if cat["layer_3_id"] not in crawled_cats]
            logger.info("resume_mode_filtered", platform=platform.value, remaining=len(categories), total_before=len(await self.discovery.get_category_codes(platform, target_id=target_cat_id)))
        
        async with httpx.AsyncClient(
            verify=False, 
            follow_redirects=True, 
            timeout=20.0,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)
        ) as client:
            # 設置併發限制（URL 級別，不是分類級別）
            sem = asyncio.Semaphore(5)
            
            # ✅ 逐個分類執行（而不是並行 gather）
            total_cats = len(categories)
            for cat_idx, cat in enumerate(categories, 1):
                cat_id: str = cat["layer_3_id"]
                cat_name: Optional[str] = cat.get("layer_3_name")
                
                logger.info(
                    "category_processing_start",
                    platform=platform.value,
                    category_index=f"{cat_idx}/{total_cats}",
                    cat_id=cat_id,
                    cat_name=cat_name
                )
                
                try:
                    # 探索 URL 列表
                    urls: List[str] = await self.discovery.discover_category(
                        platform, 
                        cat_id, 
                        client, 
                        limit=max_jobs
                    )
                    
                    if not urls:
                        logger.debug("category_no_urls", platform=platform.value, cat=cat_id)
                        await self.db.mark_category_as_crawled(platform.value, cat_id)
                        continue
                    
                    logger.info(
                        "category_discovery_stats",
                        platform=platform.value,
                        cat=cat_id,
                        count=len(urls)
                    )
                    
                    # 併發處理該類別下的網址（信號量應用於 URL 級別）
                    async def process_with_sem(url: str):
                        async with sem:
                            await self._process_url_and_save(
                                platform, 
                                url, 
                                client, 
                                cat_id, 
                                cat_name
                            )
                    
                    # 建立任務並執行（受信號量限制）
                    job_tasks = [
                        process_with_sem(url) 
                        for url in list(set(urls))[:max_jobs]
                    ]
                    
                    # 執行所有 URL（但受信號量限制，確保併發度控制）
                    await asyncio.gather(*job_tasks, return_exceptions=True)
                    
                    # ✅ 分類處理完成，標記進度
                    await self.db.mark_category_as_crawled(platform.value, cat_id)
                    
                    logger.info(
                        "category_processing_completed",
                        platform=platform.value,
                        cat=cat_id,
                        progress=f"{cat_idx}/{total_cats}"
                    )
                    
                except Exception as e:
                    logger.error(
                        "category_processing_error",
                        platform=platform.value,
                        cat=cat_id,
                        error=str(e),
                        exc_info=True
                    )
                    # ⚠️ 分類失敗時不標記為完成，下次 resume 時會重試
                    continue
            
            logger.info("pipeline_completed", platform=platform.value, total_categories=total_cats)

    async def run_all(
        self, 
        limit_per_platform: int = 10,
        resume: bool = True
    ) -> None:
        """
        啟動所有支援平台的自動抓取（平台並行，分類順序）。
        
        Args:
            limit_per_platform (int): 每個分類的職缺上限。
            resume (bool): 若 True，跳過已完成的分類。
        """
        logger.info("run_all_started", mode="parallel_platforms_sequential_categories", resume=resume)
        
        # ✅ 5 個平台並行執行（各自內部職業類別順序執行）
        tasks = [
            self.run_platform(
                p, 
                max_jobs=limit_per_platform,
                resume=resume
            )
            for p in SourcePlatform
            if p != SourcePlatform.PLATFORM_UNKNOWN
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 統計結果
        failures = sum(1 for r in results if isinstance(r, Exception))
        logger.info(
            "run_all_completed",
            total_platforms=len(results),
            failures=failures,
            mode="parallel_platforms_sequential_categories"
        )
        
        if failures > 0:
            logger.warning("run_all_had_failures", failed_platforms=failures)

