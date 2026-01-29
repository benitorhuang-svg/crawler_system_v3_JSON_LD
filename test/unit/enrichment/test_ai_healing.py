import asyncio
import structlog
import pytest
from core.infra import SourcePlatform, configure_logging, Database
from core.services import CrawlService

# Initialize logging
configure_logging()
logger = structlog.get_logger("test_ai_healing")

@pytest.mark.asyncio
async def test_healing():
    crawl_service = CrawlService()
    
    # Mock HTML that looks like a job page but has no JSON-LD
    mock_html = """
    <html>
        <body>
            <h1>Senior Python Engineer</h1>
            <div class="company">Tech Corp</div>
            <div class="description">We are looking for a Python expert to join our team. Salary: 100k - 150k. Address: Taipei 101.</div>
        </body>
    </html>
    """
    
    print("\n--- Starting AI Healing Test ---")
    # Calling heal_with_ai directly
    job, company = await crawl_service.heal_with_ai(
        html=mock_html,
        platform=SourcePlatform.PLATFORM_CAKERESUME,
        original_title="Senior Python Engineer | Tech Corp"
    )
    
    if job:
        print("\nSUCCESS: AI Healing extracted job data:")
        print(f"Title: {job.title}")
        print(f"Description: {job.description[:100]}...")
        print(f"Data Source Layer: {job.data_source_layer}")
    else:
        print("\nFAILURE: AI Healing failed to extract job data.")

    if company:
        print("\nSUCCESS: AI Healing extracted company data:")
        print(f"Name: {company.name}")
        print(f"Data Source Layer: {company.data_source_layer}")

if __name__ == "__main__":
    asyncio.run(test_healing())
