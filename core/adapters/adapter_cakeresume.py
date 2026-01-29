"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：adapter_cakeresume.py
功能描述：CakeResume 專用的 JSON-LD 適配器。
"""
import re
from typing import Optional, Dict, Any, List
from .jsonld_adapter import JsonLdAdapter
from core.infra import SourcePlatform, CompanyPydantic
from core.utils.parsers import DateParser, SalaryParser, ExperienceParser

class AdapterCakeResume(JsonLdAdapter):
    """
    CakeResume (Cake.me) 平台適配器。
    """

    @property
    def platform(self) -> SourcePlatform:
        return SourcePlatform.PLATFORM_CAKERESUME

    def get_description(self, ld: Dict[str, Any]) -> Optional[str]:
        from bs4 import BeautifulSoup
        import html as html_lib
        desc = ld.get("description")
        if not desc: return None
        text = html_lib.unescape(desc)
        
        # 檢測是否有 Raw JSON (防止腳本內容洩漏)
        # CakeResume 偶爾會吐出含有 {"learn_more":...} 的字串
        if "\"learn_more\"" in text and "\"view_all\"" in text:
             return None

        soup = BeautifulSoup(text, "html.parser")
        return soup.get_text(separator=' ', strip=True)

    def get_url(self, ld: dict, fallback_url: str | None = None) -> str:
        return ld.get("url") or fallback_url or ""

    def get_source_id(self, ld: dict, url: str | None = None) -> str | None:
        target_url = self.get_url(ld, url)
        return target_url.split("/")[-1] if target_url else None

    def get_salary(self, ld: Dict[str, Any]) -> Dict[str, Any]:
        salary_node = ld.get("baseSalary", {})
        res = SalaryParser.parse(salary_node)
        return {"min": res["min"], "max": res["max"], "type": res["type"], "text": res["text"]}

    def get_education(self, ld: dict) -> str:
        return self._map_education_text(ld.get("educationRequirements"))

    def get_experience(self, ld: Dict[str, Any]) -> Optional[int]:
        next_data = ld.get("_next_data")
        if next_data:
            val = self._safe_get(next_data, "props", "pageProps", "job", "min_work_exp_year")
            if val is not None:
                try: return int(val)
                except: pass
        return ExperienceParser.parse(ld.get("experienceRequirements"))

    def get_job_type(self, ld: dict) -> str:
        return self._map_job_type(ld.get("employmentType"))

    def get_company_name(self, ld: dict) -> str | None:
        next_data = ld.get("_next_data")
        if next_data:
            name = self._safe_get(next_data, "props", "pageProps", "company", "name")
            if name: return name
        name = self._safe_get(ld, "hiringOrganization", "name")
        if name: return name
        if ld.get("@type") in ["Organization", "NextDataNode"]: return ld.get("name")
        return None

    def get_company_url(self, ld: dict) -> str | None:
        next_data = ld.get("_next_data")
        if next_data:
            slug = self._safe_get(next_data, "props", "pageProps", "company", "slug")
            if slug: return self._normalize_url(f"https://www.cake.me/companies/{slug}")
        url = self._safe_get(ld, "hiringOrganization", "url") or self._safe_get(ld, "hiringOrganization", "sameAs")
        if not url and ld.get("@type") in ["Organization", "NextDataNode"]: url = ld.get("url") or ld.get("sameAs")
        return self._normalize_url(url) if url else None

    def _normalize_url(self, url: str) -> str:
        if not url: return url
        new_url = url.replace("www.cakeresume.com", "www.cake.me").replace("cakeresume.com", "cake.me")
        if "vertiv-taiwan-co-ltd" in new_url: new_url = new_url.replace("vertiv-taiwan-co-ltd", "VertivTW")
        return new_url

    def get_address(self, ld: dict, html: str | None = None) -> str | None:
        district = self.get_district(ld)
        street = self._clean_taiwan(self._safe_get(ld, "jobLocation", "address", "streetAddress"))
        return self._dedupe_address([district, street])

    def get_company_website(self, ld: dict) -> str | None:
        return self._filter_website(self._safe_get(ld, "hiringOrganization", "sameAs"))

    def get_company_source_id(self, ld: dict) -> str | None:
        url = self.get_company_url(ld)
        return url.rstrip("/").split("/")[-1] if url else None

    def get_company_address(self, ld: Dict[str, Any]) -> Optional[str]:
        next_data = ld.get("_next_data")
        if next_data:
            addr = self._safe_get(next_data, "props", "pageProps", "company", "address")
            if addr: return self._standardize_taiwan_address_format(addr)
        addr_node = self._safe_get(ld, "hiringOrganization", "address")
        if not addr_node and ld.get("@type") == "Organization": addr_node = ld.get("address")
        if not addr_node: return None
        if isinstance(addr_node, str): return self._standardize_taiwan_address_format(addr_node)
        reg = self._standardize_taiwan_address_format(addr_node.get("addressRegion"))
        loc = self._standardize_taiwan_address_format(addr_node.get("addressLocality"))
        strt = self._standardize_taiwan_address_format(addr_node.get("streetAddress"))
        dist = self._dedupe_address([reg or "", loc or ""])
        return self._dedupe_address([dist, strt or ""])

    def get_industry(self, ld: dict) -> str | None:
        breadcrumbs = ld.get("_breadcrumbs")
        company_name = self.get_company_name(ld)
        if breadcrumbs and isinstance(breadcrumbs, list):
            sorted_crumbs = sorted(breadcrumbs, key=lambda x: x.get("position", 0))
            for item in reversed(sorted_crumbs):
                name = item.get("item", {}).get("name", "")
                if not name or name in ["首頁", "找工作", "Job Search", "Home", "Jobs"]: continue
                if company_name and (name in company_name or company_name in name): continue
                job_title = self.get_title(ld)
                if job_title and name == job_title: continue
                return name
        return ld.get("industry")

    def get_work_hours(self, ld: dict) -> str | None:
        wh = ld.get("workHours")
        return ", ".join(wh) if isinstance(wh, list) else wh

    def get_skills(self, ld: dict) -> str | None:
        sk = ld.get("skills")
        return ", ".join(sk) if isinstance(sk, list) else sk

    def get_capital(self, ld: dict) -> str | None:
        next_data = ld.get("_next_data")
        val = None
        if next_data:
            val = self._safe_get(next_data, "props", "pageProps", "company", "capital") or \
                  self._safe_get(next_data, "props", "pageProps", "job", "company", "capital")
        if not val: val = ld.get("capital")
        return self._validate_numeric_noise(val, "capital")

    def get_employee_count(self, ld: dict) -> str | None:
        next_data = ld.get("_next_data")
        val = None
        if next_data:
            val = self._safe_get(next_data, "props", "pageProps", "company", "numberOfEmployees") or \
                  self._safe_get(next_data, "props", "pageProps", "job", "company", "numberOfEmployees")
        if not val: val = ld.get("numberOfEmployees")
        return self._validate_numeric_noise(val, "employees")
