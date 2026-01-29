import asyncio
import structlog
from core.infra.browser_fetcher import BrowserFetcher

async def test_fetcher():
    fetcher = BrowserFetcher()
    print("Attempting to fetch...")
    try:
        # Just a dummy fetch to trigger initialization
        await fetcher.fetch("https://example.com")
        print("Fetch call initiated successfully (ignoring result)")
    except Exception as e:
        print(f"Caught error: {e}")

if __name__ == "__main__":
    asyncio.run(test_fetcher())
