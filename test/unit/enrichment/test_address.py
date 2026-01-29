import re

def _clean_address(address: str) -> str:
    """
    Standardize Taiwan addresses to improve geocoding success rate.
    Borrowed and refined from core/enrichment/geocoder.py
    """
    if not address: return ""
    
    # 0. Convert full-width characters to half-width, including new brackets
    # Added ﹝﹞【】 and others
    trans_map = str.maketrans(
        '１２３４５６７８９０（）［］／、﹝﹞【】', 
        '1234567890()[]/,()[]'
    )
    address = address.translate(trans_map)
    
    # 1. Handle multiple addresses (Choose the first one or the one with '號')
    # Use split by comma or slash
    parts = re.split(r'[/,]', address)
    if len(parts) > 1:
        parts = [p.strip() for p in parts if p.strip()]
        # Requirement: Take the first one if multiple
        # But heuristic says '號' is better for geocoding
        # User said "two or more, always choose the first one" explicitly for Vietnam case
        address = parts[0]

    # 2. Remove Taiwan/ROC prefix
    address = re.sub(r'^(台灣|中華民國|臺灣|Taiwan|R\.O\.C)', '', address).strip()
    
    # 3. Remove content inside brackets/parentheses
    # Expanded regex for bracket types
    address = re.sub(r'[\(\[（［\uFF08\uFF09\uFF3B\uFF3D\u2704\u203B\u3010\u3011\u2705\u274C\u2B55\u274E\u2728\u27A1\ufe0f\ud83d\udccd\ud83d\udea9\ud83d\udcde\ud83d\udce7\ud83d\udcf1\ud83d\udcf2\ud83d\udce6\ud83d\udcb0\ud83d\udcb8\ud83d\udcb3\ud83d\udcb5\ud83d\udcb4\ud83d\udcb9\ud83d\udce1\ud83d\udce2\ud83d\udce3\ud83d\udce4\ud83d\udce5\ud83d\udced\ud83d\udcee\ud83d\udcef\ud83d\udcf0\ud83d\udcf3\ud83d\udcf4\ud83d\udcf5\ud83d\udcf6\ud83d\udcf7\ud83d\udcf8\ud83d\udcf9\ud83d\udcfa\ud83d\udcfb\ud83d\udcfc\ud83d\udcfd\ud83d\udcfe\ud83d\udcff].*?[\)\]）］\uFF08\uFF09\uFF3B\uFF3D\u2704\u203B\u3010\u3011\u2705\u274C\u2B55\u274E\u2728\u27A1\ufe0f\ud83d\udccd\ud83d\udea9\ud83d\udcde\ud83d\udce7\ud83d\udcf1\ud83d\udcf2\ud83d\udce6\ud83d\udcb0\ud83d\udcb8\ud83d\udcb3\ud83d\udcb5\ud83d\udcb4\ud83d\udcb9\ud83d\udce1\ud83d\udce2\ud83d\udce3\ud83d\udce4\ud83d\udce5\ud83d\udced\ud83d\udcee\ud83d\udcef\ud83d\udcf0\ud83d\udcf3\ud83d\udcf4\ud83d\udcf5\ud83d\udcf6\ud83d\udcf7\ud83d\udcf8\ud83d\udcf9\ud83d\udcfa\ud83d\udcfb\ud83d\udcfc\ud83d\udcfd\ud83d\udcfe\ud83d\udcff]', '', address).strip()
    # Simpler: just replace common brackets and then remove everything in () []
    # Re-translating ensures they are consistent
    address = re.sub(r'[\(\[].*?[\)\]]', '', address).strip()

    # 4. Remove floor/room/building info
    patterns = [
        r'\d+[樓Ff].*',
        r'B\d+.*',
        r'地下\d+樓.*',
        r'[第]?[A-Z0-9]+[室室].*',
        r'\d+棟.*',
        r'(?<=號)\s*[A-Z0-9].*' 
    ]
    
    for p in patterns:
        address = re.sub(p, '', address).strip()
        
    # Final cleanup
    address = address.rstrip('- ').strip()
    
    return address

# Test cases
test_cases = [
    ("北市信義區基隆路二段51號7樓之2（距捷運台北101/世貿站490公尺）", "北市信義區基隆路二段51號"),
    ("新北市五股區五工路134號﹝五股工業區﹞", "新北市五股區五工路134號"),
    ("越南南越、印尼中爪哇(視職務需求)", "越南南越"),
    ("台北市大安區信義路四段100號10F", "台北市大安區信義路四段100號"),
]

for inp, expected in test_cases:
    actual = _clean_address(inp)
    print(f"Input: {inp}")
    print(f"Expected: {expected}")
    print(f"Actual:   {actual}")
    print(f"Success:  {actual == expected}")
    print("-" * 20)
