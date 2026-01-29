import structlog
import pytest
from core.infra.browser_fetcher import BrowserFetcher

# Setup logging to see what's happening
structlog.configure()

@pytest.mark.asyncio
async def test_fetcher():
    print("Testing BrowserFetcher...")
    try:
        fetcher = BrowserFetcher()
        content = await fetcher.fetch("https://www.google.com")
        if content:
            print(f"Success! Content length: {len(content)}")
        else:
            print("Fetcher returned empty content.")
    except Exception as e:
        print(f"BrowserFetcher failed: {e}")
    finally:
        await BrowserFetcher.close_browser()

if __name__ == "__main__":
    asyncio.run(test_fetcher())
