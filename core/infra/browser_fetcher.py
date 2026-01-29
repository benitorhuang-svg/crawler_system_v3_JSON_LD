"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：browser_fetcher.py
功能描述：瀏覽器抓取工具，基於 Playwright 實現真實瀏覽器模擬，用於處理動態渲染與反爬蟲。
主要入口：由 core.services.crawl_service 調用。
"""
import asyncio
import random
import structlog
from typing import List, Optional, Dict, Any
from core.infra.config import settings
from playwright.async_api import async_playwright, Browser, Playwright, Error as PlaywrightError

# 設置結構化日誌
logger = structlog.get_logger(__name__)

# 模擬真實瀏覽器的 User-Agent 列表
USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

class BrowserFetcher:
    """
    基於動態瀏覽器的抓取服務。
    當靜態抓取被封鎖或網頁需要渲染 JavaScript 時啟用。
    """
    _playwright: Optional[Playwright] = None
    _browser: Optional[Browser] = None
    _contexts: List[Any] = []
    _max_contexts: int = 5 
    _breaker = None

    @classmethod
    def _init_breaker(cls):
        """初始化熔斷器。"""
        if cls._breaker is None:
            from core.infra.circuit_breaker import CircuitManager
            cls._breaker = CircuitManager.get_breaker("browser_fetcher", failure_threshold=10, recovery_timeout=30)

    @classmethod
    async def get_browser(cls) -> Browser:
        """獲取或初始化 Playwright Chromium 瀏覽器。"""
        cls._init_breaker()
        if cls._browser is None:
            ws_endpoint = settings.BROWSER_WS_ENDPOINT
            cls._playwright = await async_playwright().start()
            
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if ws_endpoint:
                        # 將 ws:// 轉換為 http:// 如果需要，或者直接使用 endpoint
                        cdp_endpoint = ws_endpoint.replace("ws://", "http://").replace("wss://", "https://")
                        logger.info("browser_connecting_remote_cdp", endpoint=cdp_endpoint, attempt=attempt+1)
                        cls._browser = await cls._playwright.chromium.connect_over_cdp(cdp_endpoint, timeout=30000)
                    else:
                        logger.info("browser_launching_local", attempt=attempt+1)
                        cls._browser = await cls._playwright.chromium.launch(
                            headless=settings.BROWSER_HEADLESS,
                            args=["--disable-blink-features=AutomationControlled"]
                        )
                    break 
                except Exception as e:
                    logger.warning("browser_init_failed", error=str(e), attempt=attempt+1)
                    if attempt == max_retries - 1:
                        raise e
                    await asyncio.sleep(2 ** attempt)
        return cls._browser

    @classmethod
    async def close_browser(cls) -> None:
        """關閉所有 Context 並關閉瀏覽器。"""
        for ctx in cls._contexts:
            await ctx.close()
        cls._contexts.clear()
        
        if cls._browser:
            await cls._browser.close()
            cls._browser = None
        if cls._playwright:
            await cls._playwright.stop()
            cls._playwright = None

    async def fetch(self, url: str, proxy: Optional[str] = None, wait_for: Optional[str] = None) -> str:
        """
        使用 Context 池化抓取網頁 HTML。
        """
        async def _do_fetch():
            browser: Browser = await self.get_browser()
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1920, "height": 1080},
                proxy={"server": proxy} if proxy else None
            )
            
            from playwright_stealth import Stealth
            page = await context.new_page()
            stealth = Stealth()
            await stealth.apply_stealth_async(page)
            
            # 重試 page.goto
            for attempt in range(settings.RETRY_COUNT):
                try:
                    logger.info("browser_fetching", url=url, attempt=attempt+1)
                    await page.goto(url, wait_until="domcontentloaded", timeout=settings.BROWSER_TIMEOUT)
                    
                    if wait_for:
                        await page.wait_for_selector(wait_for, timeout=15000)
                    else:
                        await asyncio.sleep(2)
                    
                    content = await page.content()
                    return content
                except Exception as e:
                    logger.warning("browser_page_goto_failed", url=url, attempt=attempt+1, error=str(e))
                    if attempt == settings.RETRY_COUNT - 1:
                        raise e
                    await asyncio.sleep(2 ** attempt)
                finally:
                    # 決定是否關閉頁面：
                    # 1. 成功 (e 不存在) -> 關閉
                    # 2. 最後一次嘗試 -> 關閉
                    # 3. 非 Playwright 錯誤 -> 關閉
                    # 4. Playwright 錯誤且還有重試機會 -> 不關閉 (保持 Session)
                    should_close = True
                    if 'e' in locals():
                        if isinstance(e, PlaywrightError) and attempt < settings.RETRY_COUNT - 1:
                            should_close = False
                    
                    if should_close:
                        try:
                            await page.close()
                            await context.close()
                        except Exception:
                            pass
            return ""

        try:
            BrowserFetcher._init_breaker()
            return await BrowserFetcher._breaker.call(_do_fetch)
        except Exception as e:
            logger.error("browser_fetch_overall_failed", url=url, error=str(e))
            return ""
