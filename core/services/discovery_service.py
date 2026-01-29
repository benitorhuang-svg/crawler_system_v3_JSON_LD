"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：discovery_service.py
功能描述：職缺探索服務，各平台專屬發現策略。
主要入口：由 core.services.crawl_service 調用。
"""
import re
import httpx
import asyncio
import aiomysql
import structlog
import random
import time
from typing import List, Optional, Dict, Any, Union
from urllib.parse import quote
from bs4 import BeautifulSoup
from abc import ABC, abstractmethod

from core.infra import Database, SourcePlatform
from core.infra.config import settings

# 設置結構化日誌
logger = structlog.get_logger(__name__)

# 使用者代理列表
USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

class BaseDiscoveryStrategy(ABC):
    """職缺探索策略抽象基類。"""
    
    @abstractmethod
    async def discover(self, client: httpx.AsyncClient, cat_id: str, limit: Optional[int] = None) -> List[str]:
        """執行平台特定的職缺發現邏輯。"""
        pass

    def clean_url(self, url: str) -> str:
        """標準化 URL，去除多餘查詢參數。"""
        if not url: return ""
        return url.split("?")[0] if "?" in url else url

    async def _get_with_retry(self, client: httpx.AsyncClient, url: str, headers: Optional[Dict[str, str]] = None, **kwargs) -> Optional[httpx.Response]:
        """封裝重試邏輯。"""
        for attempt in range(settings.RETRY_COUNT):
            try:
                resp = await client.get(url, headers=headers, **kwargs)
                if resp.status_code in (429, 449):
                    logger.debug("rate_limited_discovery", url=url, status=resp.status_code, attempt=attempt+1)
                    await asyncio.sleep(settings.RETRY_BACKOFF_FACTOR ** (attempt + 1))
                    continue
                resp.raise_for_status()
                return resp
            except Exception as e:
                logger.warning("discovery_retry", url=url, attempt=attempt+1, error=str(e))
                if attempt == settings.RETRY_COUNT - 1:
                    raise e
                await asyncio.sleep(settings.RETRY_BACKOFF_FACTOR ** attempt)
        return None

class Discovery104(BaseDiscoveryStrategy):
    """104 人力銀行探索策略。"""
    
    def __init__(self) -> None:
        self.api_url: str = "https://www.104.com.tw/jobs/search/api/jobs"

    async def discover(self, client: httpx.AsyncClient, cat_id: str, limit: Optional[int] = None) -> List[str]:
        urls: List[str] = []
        try:
            headers: Dict[str, str] = {"Referer": "https://www.104.com.tw/", "User-Agent": random.choice(USER_AGENTS)}
            resp = await self._get_with_retry(client, f"{self.api_url}?jobcat={cat_id}&page=1&pagesize=20", headers=headers)
            if not resp: return []
            
            data: Dict[str, Any] = resp.json()
            pagination: Dict[str, Any] = data.get("metadata", {}).get("pagination", {})
            total_pages: int = int(pagination.get("lastPage", 1))

            for item in data.get("data", []):
                link: Optional[str] = item.get("link", {}).get("job")
                if link: urls.append(f"https:{link}" if link.startswith("//") else link)

            if (limit and len(urls) >= limit) or total_pages <= 1: return urls[:limit]

            # 併發處理後續分頁
            sem: asyncio.Semaphore = asyncio.Semaphore(5)
            async def fetch_p(p: int) -> List[str]:
                async with sem:
                    h: Dict[str, str] = {"Referer": "https://www.104.com.tw/", "User-Agent": random.choice(USER_AGENTS)}
                    r = await self._get_with_retry(client, f"{self.api_url}?jobcat={cat_id}&page={p}&pagesize=20", headers=h)
                    if r:
                        d = r.json()
                        return [f"https:{it.get('link', {}).get('job')}" if it.get('link', {}).get('job', '').startswith("//") else it.get('link', {}).get('job') 
                                for it in d.get("data", []) if it.get('link', {}).get('job')]
                    return []

            tasks = [fetch_p(p) for p in range(2, min(total_pages, settings.PAGINATION_LIMIT_MAX) + 1)]
            for step_res in await asyncio.gather(*tasks):
                urls.extend(step_res)
                if limit and len(urls) >= limit: break
        except Exception as e:
            logger.error("discovery_104_error", cat=cat_id, error=str(e))
        return urls[:limit] if limit else urls

class Discovery1111(BaseDiscoveryStrategy):
    """1111 人力銀行探索策略。"""
    
    def __init__(self) -> None:
        self.api_url: str = "https://www.1111.com.tw/api/v1/search/jobs/"

    async def discover(self, client: httpx.AsyncClient, cat_id: str, limit: Optional[int] = None) -> List[str]:
        urls: List[str] = []
        try:
            h: Dict[str, str] = {"User-Agent": random.choice(USER_AGENTS)}
            resp = await self._get_with_retry(client, f"{self.api_url}?jobPositions={cat_id}&page=1", headers=h)
            if not resp: return []
            
            data: Dict[str, Any] = resp.json()
            hits: List[Dict[str, Any]] = data.get("result", {}).get("hits", [])
            urls.extend([f"https://www.1111.com.tw/job/{item['jobId']}" for item in hits if item.get("jobId")])
            
            # 併發翻頁處理
            total_pages: int = int(data.get("result", {}).get("pagination", {}).get("totalPage", 1))
            sem: asyncio.Semaphore = asyncio.Semaphore(5)
            
            async def fetch_p(p: int) -> List[str]:
                async with sem:
                    r = await self._get_with_retry(client, f"{self.api_url}?jobPositions={cat_id}&page={p}", headers=h)
                    if r:
                        h_list = r.json().get("result", {}).get("hits", [])
                        return [f"https://www.1111.com.tw/job/{it['jobId']}" for it in h_list if it.get("jobId")]
                    return []

            tasks = [fetch_p(p) for p in range(2, min(total_pages, 20) + 1)]
            for step_res in await asyncio.gather(*tasks):
                urls.extend(step_res)
                if limit and len(urls) >= limit: break
        except Exception as e:
            logger.error("discovery_1111_error", cat=cat_id, error=str(e))
        return urls[:limit] if limit else urls

class DiscoveryCake(BaseDiscoveryStrategy):
    """Cake (CakeResume) 探索策略。"""
    
    def __init__(self) -> None:
        self.base_url: str = "https://www.cake.me/jobs"

    async def discover(self, client: httpx.AsyncClient, cat_id: str, limit: Optional[int] = None) -> List[str]:
        urls: List[str] = [] # Initialize urls here
        # 降低併發至 2，CakeResume 對頻率非常敏感
        sem: asyncio.Semaphore = asyncio.Semaphore(2)
        
        async def fetch_p(p: int) -> List[str]:
            # 給予隨機延遲，避免瞬間併發過高
            await asyncio.sleep(random.uniform(0.5, 2.0))
            async with sem:
                target_u: str = f"{self.base_url}?refinementList[job_categories][0]={cat_id}&page={p}"
                resp = await self._get_with_retry(client, target_u, headers={"User-Agent": random.choice(USER_AGENTS)})
                if not resp: return []
                
                soup: BeautifulSoup = BeautifulSoup(resp.text, "html.parser")
                p_urls = []
                for a in soup.find_all("a", href=True):
                    href: str = a["href"]
                    if ("/jobs/" in href or "/j/" in href) and "/companies/" in href and not href.startswith("/jobs/for-"):
                        full_u: str = f"https://www.cake.me{href}"
                        if full_u not in p_urls: p_urls.append(full_u)
                return p_urls

        tasks = [fetch_p(p) for p in range(1, 6)] # 降低分頁深度與併發 (Cake 限制多)
        results = await asyncio.gather(*tasks)
        for res in results:
            for u in res:
                if u not in urls: urls.append(u)
            if limit and len(urls) >= limit: break
            
        return urls[:limit] if limit else urls

class DiscoveryYourator(BaseDiscoveryStrategy):
    """Yourator 探索策略。"""
    
    def __init__(self) -> None:
        self.api_url: str = "https://www.yourator.co/api/v4/jobs"

    async def discover(self, client: httpx.AsyncClient, cat_id: str, limit: Optional[int] = None) -> List[str]:
        urls: List[str] = []
        page: int = 1
        while page <= 10:
            try:
                api_u: str = f"{self.api_url}?category_id[]={quote(cat_id)}&page={page}"
                resp = await self._get_with_retry(client, api_u)
                if not resp: break
                
                payload: Dict[str, Any] = resp.json().get("payload", {})
                jobs: List[Dict[str, Any]] = payload.get("jobs", [])
                if not jobs: break
                
                for j in jobs:
                    if j.get("path"): urls.append(f"https://www.yourator.co{j['path']}")
                
                if (limit and len(urls) >= limit) or payload.get("nextPage") is None: break
                page += 1
            except Exception as e:
                logger.error("discovery_yourator_error", cat=cat_id, p=page, error=str(e))
                break
        return urls[:limit] if limit else urls

class DiscoveryYes123(BaseDiscoveryStrategy):
    """Yes123 探索策略。"""
    
    def __init__(self) -> None:
        self.base_url: str = "https://www.yes123.com.tw/wk_index/joblist.asp"

    def clean_url(self, url: str) -> str:
        """Yes123 採用動態參數，不主動清理以防失效。"""
        return url

    async def discover(self, client: httpx.AsyncClient, cat_id: str, limit: Optional[int] = None) -> List[str]:
        urls: List[str] = []
        page: int = 1
        while page <= 10:
            try:
                u: str = f"{self.base_url}?job_check={cat_id}&now_page={page}"
                headers: Dict[str, str] = {"User-Agent": random.choice(USER_AGENTS)}
                resp = await self._get_with_retry(client, u, headers=headers)
                if not resp: break

                matches: List[str] = re.findall(r'job\.asp\?p_id=[^"\'\s>]+', resp.text)
                for m in set(matches):
                    full_u = f"https://www.yes123.com.tw/wk_index/{m}"
                    if full_u not in urls: urls.append(full_u)
                
                if (limit and len(urls) >= limit) or not matches: break
                page += 1
            except Exception as e:
                logger.error("discovery_yes123_error", cat=cat_id, p=page, error=str(e))
                break
        return urls[:limit] if limit else urls

class DiscoveryService:
    """
    職缺發現整合服務器。
    協調多平台探索策略，並與資料庫連動獲取分類種子。
    """
    
    def __init__(self) -> None:
        """初始化探索引擎。"""
        self.db: Database = Database()
        self._strategies: Dict[SourcePlatform, BaseDiscoveryStrategy] = {
            SourcePlatform.PLATFORM_104: Discovery104(),
            SourcePlatform.PLATFORM_1111: Discovery1111(),
            SourcePlatform.PLATFORM_CAKERESUME: DiscoveryCake(),
            SourcePlatform.PLATFORM_YOURATOR: DiscoveryYourator(),
            SourcePlatform.PLATFORM_YES123: DiscoveryYes123()
        }

    def _get_strategy(self, platform: SourcePlatform) -> Optional[BaseDiscoveryStrategy]:
        """按平台取得對應策略。"""
        return self._strategies.get(platform)

    async def get_category_codes(self, platform: SourcePlatform, target_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """獲取該平台所有已註冊的分類代碼。"""
        try:
            async with self.db.safe_cursor(cursor_type=aiomysql.DictCursor) as cursor:
                sql: str = "SELECT layer_3_id, layer_3_name, updated_at FROM tb_categories WHERE platform = %s"
                params = [platform.value]
                if target_id:
                    sql += " AND layer_3_id = %s"
                    params.append(target_id)
                await cursor.execute(sql, tuple(params))
                return await cursor.fetchall() or []
        except Exception as e:
            logger.error("category_fetch_failed", platform=platform.value, error=str(e))
            return []

    async def discover_category(self, platform: SourcePlatform, cat_id: str, client: httpx.AsyncClient, limit: Optional[int] = None) -> List[str]:
        """對單一分類執行探索流水線。"""
        strategy = self._get_strategy(platform)
        if not strategy:
            logger.error("strategy_missing", platform=platform.value)
            return []

        start_t: float = time.perf_counter()
        ok: bool = False
        err: Optional[str] = None
        urls: List[str] = []
        
        try:
            urls = await strategy.discover(client, cat_id, limit)
            ok = True
            return [strategy.clean_url(u) for u in urls]
        except Exception as e:
            err = str(e)
            logger.error("discovery_step_failed", platform=platform.value, cat=cat_id, error=err)
            return []
        finally:
            latency: int = int((time.perf_counter() - start_t) * 1000)
            await self.db.record_platform_health(
                platform.value, ok, 
                extraction_success=(len(urls) > 0 if ok else False),
                latency_ms=latency, error_msg=err
            )

    async def run_discovery(self, platform: SourcePlatform, limit_per_cat: int = 50) -> List[str]:
        """完整自動化探索任務。"""
        logger.info("discovery_process_start", platform=platform.value)
        categories: List[Dict[str, Any]] = await self.get_category_codes(platform)
        if not categories: return []

        all_urls: List[str] = []
        sem: asyncio.Semaphore = asyncio.Semaphore(5)
        
        async def task_wrapper(cat_item: Dict[str, Any], cl: httpx.AsyncClient) -> List[str]:
            async with sem:
                return await self.discover_category(platform, cat_item['layer_3_id'], cl, limit=limit_per_cat)

        async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=30.0) as client:
            tasks = [task_wrapper(c, client) for c in categories]
            results = await asyncio.gather(*tasks)
            for res in results:
                if res: all_urls.extend(res)

        unique_urls: List[str] = list(set(all_urls))
        logger.info("discovery_process_finished", platform=platform.value, total=len(unique_urls))
        return unique_urls
