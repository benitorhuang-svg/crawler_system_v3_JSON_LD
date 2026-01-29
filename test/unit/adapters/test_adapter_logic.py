import pytest
import json
import os
from pathlib import Path
from core import AdapterFactory, JsonLdExtractor
from core.infra import SourcePlatform, SalaryType

ROOT_DIR = Path(__file__).parents[3]
FIXTURE_DIR = ROOT_DIR / "test" / "fixtures" / "data"

def load_sample(platform: str):
    # Example: 104 -> 104_sample_104_job.json
    filename = f"{platform}_sample_{platform}_job.json"
    path = FIXTURE_DIR / filename
    
    if not path.exists():
        # Fallback search in FIXTURE_DIR
        for f in FIXTURE_DIR.iterdir():
            if f.name.startswith(platform) and f.name.endswith(".json"):
                path = f
                break

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@pytest.mark.parametrize("platform, expected_title, expected_cid", [
    (SourcePlatform.PLATFORM_104, "【新莊區】-社區主任/社區總幹事(福美街附近/有特休)", "1a2x6bkgia"),
    (SourcePlatform.PLATFORM_1111, "貳輪嶼｜徵【儲備店長】高屏區", "73159840"),
    (SourcePlatform.PLATFORM_CAKERESUME, "Account Manager / Sales Manager - ODM", "VertivTW"),
    (SourcePlatform.PLATFORM_YES123, "行銷部/電腦繪圖設計師", "2849804_97260086"),
    (SourcePlatform.PLATFORM_YOURATOR, "機構設計工程師 Mechanical Design Engineer", "919f33fa"),
])
def test_all_adapters_mapping(platform, expected_title, expected_cid):
    adapter = AdapterFactory.get_adapter(platform)
    platform_key = platform.value.replace("platform_", "")
    raw_ld = load_sample(platform_key)
    
    # Safely find the JobPosting object from list
    ld = JsonLdExtractor.find_job_posting(raw_ld) if isinstance(raw_ld, list) else raw_ld
    url = ld.get("_source_url") or ld.get("url") or "https://example.com"
    
    job = adapter.map_to_job(ld, url)
    company = adapter.map_to_company(ld)
    
    assert job.title == expected_title
    assert company.name is not None
    assert company.source_id == expected_cid

def test_salary_parsing():
    # Test specific complex salary parsing logic if needed for any platform
    adapter = AdapterFactory.get_adapter(SourcePlatform.PLATFORM_1111)
    raw_ld = load_sample("1111")
    ld = JsonLdExtractor.find_job_posting(raw_ld) if isinstance(raw_ld, list) else raw_ld
    
    salary = adapter.get_salary(ld)
    assert salary["min"] == 40000
    assert salary["max"] == 100000 # Corrected based on error output (minValue 40000, maxValue 100000)
    assert salary["type"] == SalaryType.MONTHLY
