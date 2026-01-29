import asyncio
import pytest
from playwright.async_api import async_playwright

@pytest.mark.asyncio
async def test_playwright():
    print("Testing Playwright Chromium Launch...")
    try:
        async with async_playwright() as p:
            # Check if it attempts to connect to 9222 by default
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto("https://www.google.com")
            title = await page.title()
            print(f"Success! Title: {title}")
            await browser.close()
    except Exception as e:
        print(f"Playwright Launch Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_playwright())
