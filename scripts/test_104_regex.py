import re
import html as html_lib
from bs4 import BeautifulSoup

# Mocking the constants from JsonLdAdapter
RE_CAPITAL = [
    re.compile(r"資本額\s*(?:[:：\s]|<[^>]+>)*\s*([^<|]{2,50})", re.IGNORECASE | re.DOTALL),
    re.compile(r"capital\s*(?:[:：\s]|<[^>]+>)*\s*([^<|]{2,50})", re.IGNORECASE | re.DOTALL),
]
RE_EMPLOYEES = [
    re.compile(r"員工人數\s*(?:[:：\s]|<[^>]+>)*\s*([^<|]{2,50})", re.IGNORECASE | re.DOTALL),
    re.compile(r"員工數\s*(?:[:：\s]|<[^>]+>)*\s*([^<|]{2,50})", re.IGNORECASE | re.DOTALL),
]
RE_NUMERIC_ONLY = re.compile(r'[\d\.]+')
RE_YI = re.compile(r'([\d\.]+)(?=億)')
RE_WAN = re.compile(r'([\d\.]+)(?=萬)')
RE_DIGITS_ONLY = re.compile(r'[^\d]')
RE_NOISE = re.compile(r'[\s\-\─\=＞\>\<\!\*\#\_\~]+')
RE_CJK_OR_LETTER = re.compile(r'[\u4e00-\u9fffA-Za-z0-9]')

def standardize_numeric(text):
    if not text:
        return None
    clean_text = html_lib.unescape(str(text))
    lower_raw = clean_text.lower().replace("人力銀行", "")
    
    if any(p in lower_raw for p in ["yes123", "123", "104", "1111", "cakeresume", "yourator"]):
        has_valid_unit = any(u in lower_raw for u in ["萬元", "億", "人數", "~", "-"])
        if not has_valid_unit and not (lower_raw.endswith("人") and not lower_raw.endswith("力人")):
             return None
    
    clean_digits = RE_DIGITS_ONLY.sub("", lower_raw)
    if clean_digits in ["104", "1111", "123"] and len(clean_digits) <= 4:
        return None
    
    clean_text = clean_text.replace(",", "").replace(" ", "")
    clean_text = clean_text.replace("元", "").replace("人", "").replace("員", "").replace("名", "").replace("規模", "")
    
    if RE_NUMERIC_ONLY.fullmatch(clean_text):
        return clean_text
        
    total = 0.0
    has_unit = False
    
    yi_match = RE_YI.search(clean_text)
    if yi_match:
        total += float(yi_match.group(1)) * 100_000_000
        has_unit = True
        
    wan_match = RE_WAN.search(clean_text)
    if wan_match:
        total += float(wan_match.group(1)) * 10_000
        has_unit = True
        
    if has_unit:
        return f"{total:f}".split('.')[0]
        
    digits_match = RE_NUMERIC_ONLY.search(clean_text)
    if digits_match:
        val = digits_match.group(0)
        return val
    return text

def extract_field(html, field_type):
    patterns = RE_CAPITAL if field_type == "capital" else RE_EMPLOYEES
    for pattern in patterns:
        for match in pattern.finditer(html):
            val = match.group(1).strip()
            if "<" in val:
                val = BeautifulSoup(val, "html.parser").get_text(separator=" ", strip=True)
            return val
    return None

test_html = """
<div>職缺內容...</div>
<div>【公司簡介】26 個工作職缺、資本額：4000萬元、員工數：250人。</div>
<h3 data-v-b4e18dff="">資本額</h3></div><div data-v-b4e18dff="" class="col pl-1 p-0 intro-table__data"><p data-v-b4e18dff="" class="...">4000萬元</p>
"""

print("--- Testing Extraction ---")
cap_raw = extract_field(test_html, "capital")
emp_raw = extract_field(test_html, "employees")
print(f"Extracted Capital Raw: '{cap_raw}'")
print(f"Extracted Employees Raw: '{emp_raw}'")

print("\n--- Testing Standardization ---")
print(f"Standardized Capital: {standardize_numeric(cap_raw)}")
print(f"Standardized Employees: {standardize_numeric(emp_raw)}")
