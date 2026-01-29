import asyncio
from playwright.async_api import async_playwright
import re
import html as html_lib
from bs4 import BeautifulSoup

# Minimal extraction logic from JsonLdAdapter
RE_CAPITAL = [
    re.compile(r"資本額\s*(?:[:：\s]|<[^>]+>)*\s*([^<|、]{2,50})", re.IGNORECASE | re.DOTALL),
    re.compile(r"\"capital\"\s*[:：]\s*\"([^\"]+)\"", re.IGNORECASE),
]
RE_EMPLOYEES = [
    re.compile(r"員工人數\s*(?:[:：\s]|<[^>]+>)*\s*([^<|、]{2,50})", re.IGNORECASE | re.DOTALL),
    re.compile(r"\"emp\"\s*[:：]\s*\"([^\"]+)\"", re.IGNORECASE),
]
RE_ADDRESS = [
    re.compile(r"(?:公司地址|公司位置|企業地址|通訊地址|Address)\s*(?:[:：\s]|<[^>]+>)*\s*([^\s<|]{3,})", re.IGNORECASE | re.DOTALL),
]

async def extract_one(url):
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:3000")
        page = await browser.new_page()
        print(f"Fetching {url}...")
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(2)
        content = await page.content()
        content_clean = html_lib.unescape(content)

        results = {}
        for field, patterns in [("capital", RE_CAPITAL), ("employees", RE_EMPLOYEES), ("address", RE_ADDRESS)]:
            for p in patterns:
                m = p.search(content_clean)
                if m:
                    results[field] = m.group(1).strip()
                    if "<" in results[field]:
                        results[field] = BeautifulSoup(results[field], "html.parser").get_text(separator=" ", strip=True)
                    break
        
        print(f"Results for {url}:")
        print(results)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(extract_one("https://www.104.com.tw/company/d86epq8"))
