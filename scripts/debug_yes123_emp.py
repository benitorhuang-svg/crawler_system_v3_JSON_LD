import asyncio
from core.services.crawl_service import CrawlService
from core.infra.database import Database

async def reproduce_e2e():
    # Target the company with the reported '4' hallucination
    url = "https://www.yes123.com.tw/wk_index/comp_info.asp?p_id=20151030095054_20000099"
    print(f"Starting E2E Crawl for {url}...")
    
    # Initialize DB (pooling)
    db = Database()
    
    # Initialize Service
    service = CrawlService()
    
    # Crawl
    import aiohttp
    from core.adapters.adapter_yes123 import AdapterYes123
    
    print("Fetching HTML...")
    async with aiohttp.ClientSession() as session:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        async with session.get(url, headers=headers) as resp:
            try:
                html = await resp.text()
            except:
                html = await resp.text(encoding='utf-8', errors='ignore')

    adapter = AdapterYes123()
    # Mock LD needs _url
    ld = {"@type": "Organization", "url": url, "_url": url, "name": "Test Company"}
    
    # Init soup for debugging later
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    
    print("Mapping to Company...")
    company = adapter.map_to_company(ld, html=html)
    
    if company:
        print(f"Mapped Company: {company.name}")
        print(f"Address: '{company.address}'")
        
        # Check if address contains "薪資待遇"
        if "薪資待遇" in str(company.address):
             print("FAIL: Address still contains '薪資待遇'")
        else:
             print("PASS: Address cleaned.")
             
        # Save to DB to update the record and clear the error for verify_data.py
        await db.save_company(company)
        print("Saved to DB.")
    else:
        print("Failed to map company.")
        
    await db.close_pool()

    # Debug Base Class Extraction for "4"
    print("\n--- Debugging Base Class Extraction for '4' ---")
    clean_html = soup.get_text(separator=" ", strip=True) 
    from core.adapters.jsonld_adapter import JsonLdAdapter
    for i, pattern in enumerate(JsonLdAdapter.RE_EMPLOYEES):
        matches = list(pattern.finditer(clean_html))
        for m in matches:
            val = m.group(1) if m.groups() else m.group(0)
            if "4" in val:
                 print(f"MATCH FOUND containing '4': Pattern {i} ({pattern.pattern[:20]}...)")
                 print(f"  Match: '{m.group(0)}'")
                 print(f"  Extracted Value: '{val}'")
                 
    # Simulation: What does the adapter actually return if we force it?
    res = adapter._extract_company_field_from_html(html, "employees")
    print(f"Direct _extract_company_field_from_html result: '{res}'")
    
    # Check if labels exist
    labels = ["員工人數", "員工數"]
    present = [l for l in labels if l in clean_html]
    print(f"Labels present in HTML: {present}")

if __name__ == "__main__":
    asyncio.run(reproduce_e2e())
