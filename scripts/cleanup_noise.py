import asyncio
import structlog
from core.services.crawl_service import CrawlService
from core.infra import SourcePlatform, Database, configure_logging

configure_logging()
logger = structlog.get_logger(__name__)

async def cleanup():
    cs = CrawlService()
    await cs.db.ensure_initialized()
    
    # Target URLs
    targets = [
        (SourcePlatform.PLATFORM_YES123, "4670482_16708353", "https://www.yes123.com.tw/wk_index/comp_info.asp?p_id=4670482_16708353"),
        (SourcePlatform.PLATFORM_1111, "55134176", "https://www.1111.com.tw/corp/55134176/"),
        (SourcePlatform.PLATFORM_104, "ocu6ueo", "https://www.104.com.tw/company/ocu6ueo")
    ]
    
    from core.infra.browser_fetcher import BrowserFetcher
    fetcher = BrowserFetcher()
    
    for platform, source_id, url in targets:
        logger.info(f"Cleaning up {platform.value}: {url}")
        html = await fetcher.fetch(url)
        if not html:
            logger.error(f"Failed to fetch {url}")
            continue
            
        from core.services.jsonld_extractor import JsonLdExtractor
        from core.adapters import AdapterFactory
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html, "html.parser")
        page_title = soup.title.string if soup.title else ""
        
        extractor = JsonLdExtractor()
        ld_list = extractor.extract(html)
        ld = ld_list[0] if ld_list else {}
        
        # Inject context for adapters to find company name/id on corp pages
        ld["_injected_html_title"] = page_title
        ld["_url"] = url
        
        adapter = AdapterFactory.get_adapter(platform)
        comp = adapter.map_to_company(ld, html)
        
        if comp:
            logger.info(f"Extracted Company for {url}: capital={comp.capital}, employees={comp.employee_count}")
            success = await cs.db.save_company(comp)
            logger.info(f"Save status: {success}")
        else:
            logger.warning(f"Failed to extract company for {url}")

    # Final Check
    db = Database()
    async with db.safe_cursor() as cursor:
        await cursor.execute("SELECT platform, source_id, capital, employee_count, updated_at FROM tb_companies WHERE source_id IN ('4670482_16708353', '55134176', 'ocu6ueo')")
        rows = await cursor.fetchall()
        print('\n--- Final DB State ---')
        for row in rows:
            print(row)

    await BrowserFetcher.close_browser()
    await db.close_pool()

if __name__ == "__main__":
    asyncio.run(cleanup())
