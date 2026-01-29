"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：adapter_yourator.py
功能描述：Yourator 專用的 JSON-LD 適配器。
主要入口：由 AdapterFactory 實例化使用。
"""
import re
from typing import Optional, Dict, Any, List
from .jsonld_adapter import JsonLdAdapter
from core.infra import SourcePlatform, CompanyPydantic
from core.utils.parsers import DateParser, SalaryParser, ExperienceParser

class AdapterYourator(JsonLdAdapter):
    """
    Yourator 平台適配器。
    針對 Yourator 的 JSON-LD 結構進行映射，並包含針對該平台特殊的職務內容過濾與地點補完邏輯。
    """

    @property
    def platform(self) -> SourcePlatform:
        """Yourator 平台識別。"""
        return SourcePlatform.PLATFORM_YOURATOR


    def get_description(self, ld: Dict[str, Any]) -> Optional[str]:
        """取得職缺描述，並自動保留「工作內容」之後的核心資訊。"""
        from bs4 import BeautifulSoup
        import html as html_lib
        
        desc: Optional[str] = ld.get("description")
        if not desc:
            return None
        
        text: str = html_lib.unescape(desc)
        soup = BeautifulSoup(text, "html.parser")
        clean_text: str = soup.get_text(separator=' ', strip=True)
        
        # 過濾雜訊：保留「工作內容」區塊，移除應徵流程等無關資訊
        if "【工作內容】" in clean_text:
            parts: List[str] = clean_text.split("【工作內容】", 1)
            if len(parts) > 1:
                return "【工作內容】" + parts[1]
                
        return clean_text

    def get_url(self, ld: dict, fallback_url: str | None = None) -> str:
        """取得職缺正確 URL"""
        return ld.get("url") or fallback_url or ""

    def get_source_id(self, ld: dict, url: str | None = None) -> str | None:
        """取得平台原始 ID"""
        target_url = self.get_url(ld, url)
        match = re.search(r"jobs/(\d+)", target_url)
        return match.group(1) if match else None


    def get_salary(self, ld: Dict[str, Any]) -> Dict[str, Any]:
        """解析 Yourator 的薪資結構。"""
        salary_node: Any = ld.get("baseSalary", {})
        res: Dict[str, Any] = SalaryParser.parse(salary_node)
        return {
            "min": res["min"],
            "max": res["max"],
            "type": res["type"],
            "text": res["text"]
        }

    def get_education(self, ld: dict) -> str:
        """取得學歷要求"""
        return self._map_education_text(ld.get("educationRequirements"))

    def get_valid_through(self, ld: Dict[str, Any]) -> Optional[str]:
        """獲取有效截止日期（增加防呆避開 MySQL 限制）。"""
        val = DateParser.parse_iso_date(ld.get("validThrough"))
        if not val: return None
        
        # MySQL DATETIME 範圍至 9999-12-31，過大的年份需修正
        try:
            year = int(val.split("-")[0])
            if year > 9999:
                return f"9999-12-31"
        except (ValueError, IndexError):
            pass
        return val

    def get_experience(self, ld: Dict[str, Any]) -> Optional[int]:
        """提取最低經驗年數需求。"""
        return ExperienceParser.parse(ld.get("experienceRequirements"))

    def get_job_type(self, ld: dict) -> str:
        """取得僱用類型"""
        return self._map_job_type(ld.get("employmentType"))


    def get_company_name(self, ld: dict) -> str | None:
        """取得公司名稱"""
        # 1. 嘗試從 JSON-LD 或注入的名稱欄位取得
        name = self._safe_get(ld, "hiringOrganization", "name")
        if not name:
            name = ld.get("name") # 檢查頂層名稱 (通常是注入的)
        
        if name: return name
        
        # 2. 嘗試從 JSON-LD 的標題後備取得
        title = ld.get("title", "")
        if " | " in title:
             parts = title.split(" | ")
             if len(parts) > 1: return parts[-1].strip()
             
        # 3. 最後手段：從 _injected_html_title 解析
        html_title = ld.get("_injected_html_title", "")
        if html_title:
             # Yourator 標題格式： "VITABOX 維他盒子－最新職缺徵才中｜Yourator..."
             p1 = html_title.split("｜")[0].split("|")[0].strip()
             if "－" in p1:
                  p1 = p1.split("－")[0].strip()
             if "-" in p1: # 同時處理標準連字號
                  p1 = p1.split("-")[0].strip()
                  
             if p1 and "Yourator" not in p1:
                  return p1
        return None

    def get_company_url(self, ld: dict) -> str | None:
        """取得公司在平台的 URL"""
        # 1. 優先從職缺 URL 或來源 URL 提取，因為這對 ID 最可靠
        job_url = ld.get("_url") or ld.get("_source_url")
        if job_url:
             # 處理 yourator.co 與 www.yourator.co
             match = re.search(r"(https?://(?:www\.)?yourator\.co/companies/[^/]+)", job_url)
             if match: return match.group(1)

        # 2. 次之嘗試 JSON-LD
        url = self._safe_get(ld, "hiringOrganization", "url") or self._safe_get(ld, "hiringOrganization", "sameAs")
        if url: return url
        
        if ld.get("@type") == "Organization":
            return ld.get("url") or ld.get("sameAs")
             
        return None





    def _extract_location_badge_city(self, soup: Any) -> Optional[str]:
        """從頁面位置標籤中提取縣市名稱。"""
        badge: Optional[Any] = soup.find(class_="basic-info__icon--location")
        if badge:
            a: Optional[Any] = badge.find("a")
            if a:
                text: str = a.get_text(strip=True).replace("台灣", "").replace("臺灣", "").strip()
                return self._extract_city_from_text(text)
        return None

    def get_address(self, ld: Dict[str, Any], html: Optional[str] = None) -> Optional[str]:
        """
        取得職缺所在地完整地址。
        Yourator JSON-LD 常缺失地址，優先從 HTML 的 Google Maps 連結或資訊標籤中提取。
        """
        if not html:
            return None
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        city_badge: Optional[str] = self._extract_location_badge_city(soup)
        
        addresses: List[str] = []
        # 策略 1: 從 Google Maps 連結文字提取
        map_links: List[Any] = soup.find_all("a", href=re.compile(r"google\.com/maps"))
        for a in map_links:
            text: str = a.get_text(strip=True)
            if not text or len(text) < 5:
                continue
            
            parts: List[str] = re.split(r"[。、,;，；/]", text)
            for p in parts:
                clean_p: str = self._standardize_taiwan_address_format(p) or ""
                if not clean_p:
                    continue
                # 若該片段缺失縣市資訊且有標籤參考，則自動補全
                if city_badge and not any(kw in clean_p for kw in ["市", "縣"]):
                    clean_p = f"{city_badge}{clean_p}"
                addresses.append(clean_p)
            
        # 策略 2: 從特定 CSS Class 提取
        if not addresses:
            for cls in ["basic-info__address", "simple-info__text"]:
                el: Optional[Any] = soup.find(class_=cls)
                if el:
                    text_el: str = el.get_text(strip=True)
                    clean_text: str = self._standardize_taiwan_address_format(text_el) or ""
                    if city_badge and not any(kw in clean_text for kw in ["市", "縣"]):
                        clean_text = f"{city_badge}{clean_text}"
                    addresses.append(clean_text)

        if addresses:
            return " / ".join(dict.fromkeys(addresses))
        return None

    def get_company_website(self, ld: dict) -> str | None:
        """取得公司官方網站"""
        # 在 Yourator 中，sameAs 通常是企業官網
        return self._filter_website(self._safe_get(ld, "hiringOrganization", "sameAs"))

    def get_company_source_id(self, ld: dict) -> str | None:
        """取得平台特定公司 ID"""
        # 使用所有可能的 URL 來源，優先考慮注入的 _url 或 _source_url
        raw_url = ld.get("_source_url") or ld.get("_url") or self.get_company_url(ld) or ld.get("url")
        if not raw_url: return None
        
        url_str = str(raw_url)
        match = re.search(r"companies/([^/?#]+)", url_str)
        if match:
            sid = match.group(1)
            # 避免在 URL 為 /companies/jobs/123 時擷取到 "jobs" 作為 ID
            if sid and sid != "jobs": return sid
             
        return None

    def get_company_address(self, ld: Dict[str, Any]) -> Optional[str]:
        """提取公司地址，支援 JobPosting 與 Organization 結構。"""
        addr_node: Any = self._safe_get(ld, "hiringOrganization", "address") or ld.get("address")
        
        if not addr_node:
            return None
        if isinstance(addr_node, str):
            return self._standardize_taiwan_address_format(addr_node)
            
        region: Optional[str] = self._standardize_taiwan_address_format(addr_node.get("addressRegion"))
        locality: Optional[str] = self._standardize_taiwan_address_format(addr_node.get("addressLocality"))
        street: Optional[str] = self._standardize_taiwan_address_format(addr_node.get("streetAddress"))
        district: str = self._dedupe_address([region or "", locality or ""])
        return self._dedupe_address([district, street or ""])


    def get_work_hours(self, ld: dict) -> str | None:
        """取得工作時間"""
        wh = ld.get("workHours")
        if isinstance(wh, list):
             return ", ".join(wh) if wh else None
        return wh

    def get_skills(self, ld: dict) -> str | None:
        """取得技能要求"""
        sk = ld.get("skills")
        if isinstance(sk, list):
             return ", ".join(sk) if sk else None
        return sk

    def get_latitude(self, ld: Dict[str, Any], html: str | None = None) -> Optional[float]:
        """Yourator 座標常不準，回傳 None 以強制使用地址+OSM 解析。"""
        return None

    def get_longitude(self, ld: Dict[str, Any], html: str | None = None) -> Optional[float]:
        """Yourator 座標常不準，回傳 None 以強制使用地址+OSM 解析。"""
        return None

    def get_capital(self, ld: dict) -> str | None:
        """取得資本額"""
        return self._validate_numeric_noise(ld.get("capital"), "capital")

    def get_employee_count(self, ld: dict) -> str | None:
        """取得員工人數"""
        emp = ld.get("numberOfEmployees")
        val = None
        if isinstance(emp, dict):
            val = f"{emp.get('value')}{emp.get('unitText', '')}"
        else:
            val = str(emp) if emp else None
        return self._validate_numeric_noise(val, "employees")

    def _extract_company_field_from_html(self, html: str, field_type: str) -> str | None:
        """從 HTML 中針對 Yourator 結構提取公司欄位"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        
        if field_type == "capital":
            el = soup.find(class_="basic-info__icon--capital")
            if el: return el.get_text(strip=True)
            
        if field_type == "employees":
            el = soup.find(class_="basic-info__icon--scale")
            if el: return el.get_text(strip=True)
            
        if field_type == "address":
            # 1. 嘗試尋找 Google Maps 連結，通常包含完整地址文字
            map_a = soup.find("a", href=re.compile(r"google\.com/maps"))
            if map_a and map_a.get_text(strip=True):
                return map_a.get_text(strip=True)
                
            # 2. 後備方案使用 basic-info__address
            el = soup.find(class_="basic-info__address")
            if el:
                detail_a = el.find("a")
                if detail_a and detail_a.get_text(strip=True):
                    return detail_a.get_text(strip=True)
                return el.get_text(strip=True)
            
        return super()._extract_company_field_from_html(html, field_type)

