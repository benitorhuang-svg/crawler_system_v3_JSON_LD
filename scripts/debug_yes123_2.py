import asyncio
import re
import html as html_lib
from bs4 import BeautifulSoup
from core.adapters.adapter_yes123 import AdapterYes123

async def debug_yes123():
    with open('/tmp/yes123_debug.html', 'r') as f:
        html = f.read()
    
    adapter = AdapterYes123()
    
    soup = BeautifulSoup(html, "html.parser")
    for script in soup(["script", "style"]): script.decompose()
    clean_html = soup.get_text(separator=" ", strip=True)
    clean_html = html_lib.unescape(clean_html)
    
    print("--- Debugging Employees Patterns ---")
    patterns = adapter.RE_EMPLOYEES
    for idx, pattern in enumerate(patterns):
        print(f"Pattern {idx}: {pattern.pattern}")
        for match in pattern.finditer(clean_html):
            try: val = match.group(1).strip()
            except: val = match.group(0).strip()
            print(f"  Match: '{val}'")
            
    print("\n--- Final Extracted Field ---")
    extracted = adapter._extract_company_field_from_html(html, "employees")
    print(f"Extracted: {extracted}")
    print(f"Standardized: {adapter._standardize_numeric(extracted)}")

if __name__ == "__main__":
    asyncio.run(debug_yes123())
