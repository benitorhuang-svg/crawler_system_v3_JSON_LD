import asyncio
from playwright.async_api import async_playwright
import re

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:3000")
        page = await browser.new_page()
        
        url = "https://www.104.com.tw/company/1a2x6bkgia"
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(2)
        
        content = await page.content()
        
        # Search for keywords
        for kw in ["資本額", "員工人數", "員工數", "公司規模", "dataLayer"]:
            matches = list(re.finditer(kw, content))
            print(f"Keyword '{kw}' found {len(matches)} times.")
            for m in matches:
                # Print context around match
                start = max(0, m.start() - 100)
                end = min(len(content), m.end() + 100)
                print(f"Context: ...{content[start:end]}...")
                print("-" * 20)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
