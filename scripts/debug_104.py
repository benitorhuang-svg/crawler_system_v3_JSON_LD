import asyncio
import httpx
import json
import sys
from bs4 import BeautifulSoup
from core.infra import SourcePlatform
from core.adapters import AdapterFactory
from core.services import JsonLdExtractor

async def debug_104():
    url = "https://www.104.com.tw/job/6szw1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    }
    
    print(f"Fetching {url}...")
    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.get(url, headers=headers)
        html = resp.text
        
    ld_list = JsonLdExtractor.extract(html)
    job_ld = JsonLdExtractor.find_job_posting(ld_list)
    
    print("\n--- JSON-LD Found ---")
    if job_ld:
        # Print keys and interesting nested fields
        print(f"LD keys: {list(job_ld.keys())}")
        print(f"Location: {json.dumps(job_ld.get('jobLocation'), indent=2, ensure_ascii=False)}")
        print(f"Org: {json.dumps(job_ld.get('hiringOrganization'), indent=2, ensure_ascii=False)}")
    else:
        print("No JobPosting LD found")

    # Inspect HTML for regex matching
    print("\n--- HTML Inspection (Snippet) ---")
    if "公司地址" in html:
        idx = html.find("公司地址")
        print(f"Snippet near '公司地址': {html[idx:idx+200]}")
    
    if "資本額" in html:
        idx = html.find("資本額")
        print(f"Snippet near '資本額': {html[idx:idx+100]}")

if __name__ == "__main__":
    asyncio.run(debug_104())
