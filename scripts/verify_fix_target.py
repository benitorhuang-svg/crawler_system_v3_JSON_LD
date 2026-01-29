import asyncio
import structlog
from core.services.crawl_service import CrawlService
from core.infra import SourcePlatform, Database
from core.infra.schemas import CompanyPydantic

async def verify_target():
    db = Database()
    svc = CrawlService()
    
    target_url = "https://www.104.com.tw/company/d86epq8"
    print(f"Initializing database and starting targeted enrichment for: {target_url}")
    await db.ensure_initialized()
    
    # 1. Create a minimal company object as if it was found during job crawl
    company = CompanyPydantic(
        platform=SourcePlatform.PLATFORM_104,
        source_id="d86epq8",
        name="創百股份有限公司",
        company_url=target_url,
        data_source_layer="L1"
    )
    
    # 2. Enrich it
    import httpx
    async with httpx.AsyncClient() as client:
        await svc.enrich_company(company, SourcePlatform.PLATFORM_104, client)
    
    print("\n--- Enrichment Result ---")
    print(f"Name: {company.name}")
    print(f"Capital: {company.capital}")
    print(f"Employees: {company.employee_count}")
    print(f"Address: {company.address}")
    print(f"Website: {company.company_web}")
    print(f"Layer: {company.data_source_layer}")
    
    # 3. Save to DB
    success = await db.save_company(company)
    print(f"\nSave to DB success: {success}")
    
    # 4. Close
    await db.close_pool()

if __name__ == "__main__":
    asyncio.run(verify_target())
