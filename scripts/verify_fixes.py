import asyncio
import httpx
from core.adapters.adapter_yourator import AdapterYourator
from core.adapters.adapter_cakeresume import AdapterCakeResume
from core.services.jsonld_extractor import JsonLdExtractor
from core.infra.schemas import SourcePlatform

async def verify_pinkoi():
    print("\n--- Verifying Pinkoi (Yourator) ---")
    url = "https://www.yourator.co/companies/Pinkoi"
    adapter = AdapterYourator()
    extractor = JsonLdExtractor()
    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
        resp = await client.get(url)
        html = resp.text
        ld_list = extractor.extract(html)
        
        # Use first LD if found, otherwise mock
        ld_to_use = ld_list[0] if ld_list else {"@type": "Organization", "name": "Pinkoi", "url": url}
        company = adapter.map_to_company(ld_to_use, html=html)
        
        print(f"Description: {company.description[:100] if company.description else 'NULL'}...")
        if company.description and "Pinkoi" in company.description:
            print("SUCCESS: Description found.")
        else:
            print("FAILURE: Description still NULL or incorrect.")

async def verify_inline():
    print("\n--- Verifying inline (CakeResume) ---")
    url = "https://www.cake.me/companies/inline"
    adapter = AdapterCakeResume()
    extractor = JsonLdExtractor()
    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
        resp = await client.get(url)
        html = resp.text
        ld_list = extractor.extract(html)
        
        # Use first LD if found (should include _next_data now), otherwise mock
        ld_to_use = ld_list[0] if ld_list else {"@type": "Organization", "name": "inline", "url": url}
        print(f"Using LD type: {ld_to_use.get('@type')}")
        
        company = adapter.map_to_company(ld_to_use, html=html)
        print(f"Name: {company.name}")
        print(f"Address: {company.address}")
        print(f"Capital: {company.capital}")
        print(f"Employees: {company.employee_count}")
        
        if company.address and ("北平東路" in company.address or "中正區" in company.address):
            print("SUCCESS: Address found.")
        else:
            print("FAILURE: Address still NULL or incorrect.")
            
        # Check capital - it might be None if still missing from JSON but we test regex too
        if company.capital and ("1.2" in str(company.capital) or "12000" in str(company.capital) or "億" in str(company.capital)):
            print("SUCCESS: Capital found.")
        else:
            print("FAILURE: Capital still NULL or incorrect.")

if __name__ == "__main__":
    asyncio.run(verify_pinkoi())
    asyncio.run(verify_inline())
