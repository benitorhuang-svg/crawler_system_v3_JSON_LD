import asyncio
import aiohttp
from core.adapters.adapter_1111 import Adapter1111
from bs4 import BeautifulSoup

async def reproduce():
    urls = [
        "https://www.1111.com.tw/corp/50566778", # reported issue "5"
        "https://www.1111.com.tw/corp/290855"    # reported issue "10"
    ]
    
    for url in urls:
        print(f"\n========================================\nTesting {url}...")
        
        async with aiohttp.ClientSession() as session:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            # Disable SSL verification for debugging
            async with session.get(url, headers=headers, ssl=False) as resp:
                html = await resp.text()
        
        print(f"HTML len: {len(html)}")
        
        adapter = Adapter1111()
        print("\n--- Testing Extraction (map_to_company) ---")
        # Construct a dummy LD to pass to map_to_company
        ld = {"@type": "Organization", "url": url, "name": "Test Company"}
        company = adapter.map_to_company(ld, html=html)
        
        employees = company.employee_count if company else "None (No company mapped)"
        print(f"Final Result (Employee Count): '{employees}'")
        capital = company.capital if company else "None"
        print(f"Final Result (Capital): '{capital}'")
        
        print("\n--- Regex Debug ---")
        soup = BeautifulSoup(html, "html.parser")
        # clean like the adapter does
        for tag in soup(["script", "style"]): tag.decompose()
        clean_html = soup.get_text(separator=" ", strip=True) 
        
        from core.adapters.jsonld_adapter import JsonLdAdapter
        for i, pattern in enumerate(JsonLdAdapter.RE_EMPLOYEES):
            matches = list(pattern.finditer(clean_html))
            if matches:
                print(f"Pattern {i}: {pattern.pattern}")
                for m in matches:
                    print(f"  Match: '{m.group(0)}' -> Group 1: '{m.group(1) if m.groups() else 'N/A'}'")

if __name__ == "__main__":
    asyncio.run(reproduce())
