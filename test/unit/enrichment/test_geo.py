import re

def _dedupe_address(parts: list[str]) -> str:
    """組合地址並去除重複前綴，使用滑動緩衝檢查重疊部分"""
    if not parts:
        return ""
    
    result = ""
    for part in parts:
        if not part:
            continue
        # Clean part
        part = str(part).strip().replace("\xa0", " ")
        if not result:
            result = part
        else:
            # 1. 檢查是否完整包含
            if part in result: continue
            if result in part:
                result = part
                continue

            # 2. 檢查重疊部分的滑動匹配
            max_overlap = 0
            max_len = min(len(result), len(part))
            for i in range(max_len, 0, -1):
                if result.endswith(part[:i]):
                    max_overlap = i
                    break
            
            if max_overlap > 0:
                result += part[max_overlap:]
            else:
                # 3. 處理一般的連接，補一個空格避免粘連（若非重複）
                # 但對於台灣地址，通常不加空格。這裡保持原樣或加一個細緻判斷
                # 如果兩者都是 CJK，通常不加空格
                is_cjk = re.match(r'[\u4e00-\u9fff]', result[-1:]) and re.match(r'[\u4e00-\u9fff]', part[:1])
                if is_cjk:
                    result += part
                else:
                    result += " " + part
    return result

def get_address_country(ld: dict) -> str | None:
    # Simulating the logic
    country = ld.get("jobLocation", {}).get("address", {}).get("addressCountry")
    
    # Smarter detection
    addr_text = ld.get("jobLocation", {}).get("address", {}).get("streetAddress") or ""
    # Combine with others if available
    region = ld.get("jobLocation", {}).get("address", {}).get("addressRegion") or ""
    locality = ld.get("jobLocation", {}).get("address", {}).get("addressLocality") or ""
    full_search = f"{region}{locality}{addr_text}".upper()
    
    oversea_map = {
        "越南": "VN", "VIETNAM": "VN",
        "印尼": "ID", "INDONESIA": "ID",
        "菲律賓": "PH", "PHILIPPINES": "PH",
        "泰國": "TH", "THAILAND": "TH",
        "馬來西亞": "MY", "MALAYSIA": "MY",
        "新加坡": "SG", "SINGAPORE": "SG",
        "日本": "JP", "JAPAN": "JP",
        "韓國": "KR", "KOREA": "KR",
        "中國": "CN", "CHINA": "CN",
        "美國": "US", "USA": "US",
    }
    
    for kw, code in oversea_map.items():
        if kw in full_search:
            return code

    if not country:
        return "TW"
        
    if isinstance(country, str):
        if country.upper() in ["TW", "TWN", "TAIWAN", "ROC", "台灣", "臺灣"]:
            return "TW"
    return str(country)

# Test Cases
print("Testing Dedupe:")
print(f"Test 1: {(_dedupe_address(['台北市中山區', '台北市']) == '台北市中山區')}")
print(f"Test 2: {(_dedupe_address(['台北市', '台北市中山區']) == '台北市中山區')}")
print(f"Test 3: {(_dedupe_address(['台北市中山區', '中山區瑞光路']) == '台北市中山區瑞光路')}")

print("\nTesting Country:")
mock_ld_vn = {
    "jobLocation": {
        "address": {
            "streetAddress": "越南南越、印尼中爪哇(視職務需求)"
        }
    }
}
print(f"Test VN: {get_address_country(mock_ld_vn)} (Expected: VN)")

mock_ld_tw = {
    "jobLocation": {
        "address": {
            "streetAddress": "台北市中山區"
        }
    }
}
print(f"Test TW: {get_address_country(mock_ld_tw)} (Expected: TW)")
