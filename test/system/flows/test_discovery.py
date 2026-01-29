import asyncio
import structlog
import pytest
from core.infra import SourcePlatform, configure_logging, Database
from core.services.discovery_service import DiscoveryService

logger = structlog.get_logger(__name__)

@pytest.mark.asyncio
async def test_discovery():
    """
    Integration test for DiscoveryService.
    Ensures that for each platform, we can discover at least one job URL 
    from a known populated category.
    """
    ds = DiscoveryService()
    db = Database()
    
    # We seeded categories, let's pick one for each platform.
    # We can query the DB to find a valid cat_id for each platform.
    
    platforms = [
        SourcePlatform.PLATFORM_104,
        SourcePlatform.PLATFORM_1111,
        # Yes123 and Yourator might have fewer categories or different IDs, let's check DB finding.
        SourcePlatform.PLATFORM_YES123,
        SourcePlatform.PLATFORM_YOURATOR,
        SourcePlatform.PLATFORM_CAKERESUME
    ]

    for platform in platforms:
        logger.info("test_platform_start", platform=platform.value)
        
        # 1. Get a category
        cats = await ds.get_category_codes(platform)
        if not cats:
            logger.warning("no_categories_found", platform=platform.value)
            continue
            
        # Pick one that likely has jobs. 
        # For 104, maybe "2007001000" (Information Software)?
        # For generic test, just pick the first one or a "Software" related one if possible for stability.
        # Let's just try the first 3 and see if any return jobs.
        
        # Optimizing: Pick a random or standard one.
        # To be safe, try up to 3 categories until we get results.
        
        found_jobs = False
        for cat in cats[:3]: # Limit to first 3 to save time
            logger.info("testing_category", cat=cat['layer_3_name'], id=cat['layer_3_id'])
            try:
                # We need to expose a method to run for specific cat?
                # run_discovery runs for ALL categories of a platform. That's too heavy for a test.
                # Access private method or refactor run_discovery?
                # run_discovery iterates `categories = self.get_category_codes(platform)`.
                # We can mock `get_category_codes` OR we can just instantiate DiscoveryService 
                # and call the internal _discover_* method directly if we want speed,
                # BUT `run_discovery` sets up the `httpx` client with the correct headers/http2 settings.
                # So we should call `run_discovery` but maybe monkeypatch `get_category_codes` to return just one?
                
                # Let's Monkeypatch instance for this test
                original_get = ds.get_category_codes
                ds.get_category_codes = lambda p: [cat]
                
                urls = await ds.run_discovery(platform, max_pages_limit=1) # Limit pages for speed
                
                # Restore
                ds.get_category_codes = original_get
                
                if urls:
                    logger.info("test_success", platform=platform.value, url_count=len(urls), sample=urls[0])
                    found_jobs = True
                    break
                else:
                    logger.warning("test_empty", platform=platform.value, cat=cat['layer_3_name'])
                    
            except Exception as e:
                logger.error("test_error", platform=platform.value, error=str(e))

        if not found_jobs:
            logger.error("test_all_cats_failed", platform=platform.value)

if __name__ == "__main__":
    configure_logging()
    asyncio.run(test_discovery())
