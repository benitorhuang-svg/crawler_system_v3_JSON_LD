"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：adapter_104.py
功能描述：104 人力銀行專用的 JSON-LD 適配器，處理該平台的標籤差異與資料清洗。
主要入口：由 AdapterFactory 實例化使用。
"""
import re
from typing import Optional, Dict, Any, List
from .jsonld_adapter import JsonLdAdapter
from core.infra import SourcePlatform, CompanyPydantic
from core.utils.parsers import SalaryParser, ExperienceParser

class Adapter104(JsonLdAdapter):
    """
    104 人力銀行適配器。
    針對 104 平台的 JSON-LD 結構進行特殊欄位映射與資料清洗。
    """

    @property
    def platform(self) -> SourcePlatform:
        """104 平台識別。"""
        return SourcePlatform.PLATFORM_104

    def get_description(self, ld: Dict[str, Any]) -> Optional[str]:
        """
        從 JSON-LD 提取並清洗職缺描述。
        移除 HTML 標籤並還原實體字元。
        """
        from bs4 import BeautifulSoup
        import html as html_lib
        
        desc: Optional[str] = ld.get("description")
        if not desc:
            return None
        
        # 1. 解碼 HTML 實體並清理
        text: str = html_lib.unescape(desc)
        
        # 2. 險查是否為 Raw JSON (防止腳本內容洩漏)
        if "{" in text and "}" in text and ":" in text and "\"" in text:
             return None

        soup = BeautifulSoup(text, "html.parser")
        return soup.get_text(separator=' ', strip=True)

    def get_url(self, ld: Dict[str, Any], fallback_url: Optional[str] = None) -> str:
        """
        取得規範化的職缺 URL，移除查詢參數（Query Parameters）。
        """
        url = ld.get("url") or fallback_url or ""
        # 移除 URL 中的查詢參數 (SDD Sec 18)
        if "?" in url:
            return url.split("?")[0]
        return url

    def get_source_id(self, ld: Dict[str, Any], url: Optional[str] = None) -> Optional[str]:
        """
        從 URL 中提取 104 的職缺原始 ID (job id)。
        """
        target_url = self.get_url(ld, url)
        match = re.search(r"job/([^/?#]+)", target_url)
        return match.group(1) if match else None

    def get_salary(self, ld: Dict[str, Any]) -> Dict[str, Any]:
        """解析 104 的薪資結構。"""
        base_salary: Any = ld.get("baseSalary", {})
        res: Dict[str, Any] = SalaryParser.parse(base_salary)
        return {
            "min": res["min"],
            "max": res["max"],
            "type": res["type"],
            "text": res["text"]
        }

    def get_education(self, ld: Dict[str, Any]) -> str:
        """提取學歷要求並映射至標準中文標籤。"""
        edu = ld.get("educationRequirements")
        if not edu: return "不拘"
        
        text = ""
        if isinstance(edu, list):
            items = []
            for item in edu:
                val = item.get("credentialCategory") or item.get("name") or str(item)
                items.append(val)
            text = "/".join(items)
        elif isinstance(edu, dict):
            text = edu.get("credentialCategory") or edu.get("name") or str(edu)
        else:
            text = str(edu)
            
        return self._map_education_text(text)

    def get_experience(self, ld: Dict[str, Any]) -> Optional[int]:
        """提取最低經驗年數需求。"""
        return ExperienceParser.parse(ld.get("experienceRequirements"))

    def get_job_type(self, ld: Dict[str, Any]) -> str:
        """提取僱用類型（全職/兼職等）。"""
        return self._map_job_type(ld.get("employmentType"))

    def get_posted_date(self, ld: Dict[str, Any]) -> Optional[str]:
        """提取刊登日期（YYYY-MM-DD）。"""
        date_str = ld.get("datePosted")
        return date_str.split("T")[0] if date_str else None

    # ========== 地點處理 ==========


    def get_address(self, ld: Dict[str, Any], html: Optional[str] = None) -> Optional[str]:
        """取得職務所在地之完整地址。"""
        district = self.get_district(ld)
        street = self._clean_taiwan(self._safe_get(ld, "jobLocation", "address", "streetAddress"))
        return self._clean_id_noise(self._dedupe_address([district, street]))


    def get_company_name(self, ld: Dict[str, Any]) -> Optional[str]:
        """
        多層次提取公司名稱。
        包含：JSON-LD hiringOrganization、頁面標題解析 (Title Parsing)。
        """
        # 1. 標準 JSON-LD 欄位
        name = self._safe_get(ld, "hiringOrganization", "name") or self._safe_get(ld, "hiringOrganization", "legalName")
        
        # 2. 若 ld 直接是 Organization 類型
        if not name and ld.get("@type") == "Organization":
            name = ld.get("name") or ld.get("legalName")
        
        # 3. 從職缺標題解析 (104 常見格式： "職缺名稱｜公司名稱")
        if not name:
            title = ld.get("title", "")
            if "｜" in title:
                 parts = title.split("｜")
                 if len(parts) > 1:
                    name = parts[1].strip()
                 
        # 4. 從 HTML Title 標籤解析 (後備方案)
        if not name:
            html_title = ld.get("_injected_html_title", "")
            if html_title:
                clean_title = html_title.replace("｜", " - ").replace("|", " - ").replace("－", " - ")
                parts = [p.strip() for p in clean_title.split(" - ") if p.strip()]
                if len(parts) >= 2:
                    name = parts[1]
                    # 若 parts[1] 是平台名稱，則嘗試 parts[0]
                    if "104" in name and len(parts) >= 3:
                        name = parts[1] # 重新評估
                    if "104" in name or name in ["徵才中", "徵人中", "工作", "職缺", "Company"]:
                        # 尋找第一個不包含 "104" 或狀態詞的部分
                        for p in parts:
                            if "104" not in p and p not in ["徵才中", "徵人中", "工作", "職缺", "Company"]:
                                name = p
                                break

        # 移除平台關鍵字雜訊
        if name:
            name = name.replace("104人力銀行", "").replace("104", "").strip(" -|－｜")
            # 若清洗後為空則回傳 None
            if not name: return None
            
        return name

    def map_to_company(self, ld: Dict[str, Any], html: Optional[str] = None) -> Optional[CompanyPydantic]:
        """覆寫以支援 data_source_layer 傳遞。"""
        comp = super().map_to_company(ld, html)
        if comp and "data_source_layer" in ld:
            comp.data_source_layer = ld["data_source_layer"]
        return comp

    def get_company_url(self, ld: Dict[str, Any]) -> Optional[str]:
        """取得公司於 104 平台的介紹頁面 URL。"""
        # 0. 直接從注入的 URL 提取 (針對 corp 頁面)
        injected_url = ld.get("_url") or ld.get("url")
        if injected_url and "company/" in injected_url:
            return injected_url

        # 1. Try hiringOrganization.sameAs or .url
        url = self._safe_get(ld, "hiringOrganization", "sameAs") or self._safe_get(ld, "hiringOrganization", "url")
        if url: return url
        
        # 2. If ld is Organization directly
        if ld.get("@type") == "Organization":
            return ld.get("sameAs") or ld.get("url")
            
        return None

    def get_company_website(self, ld: Dict[str, Any]) -> Optional[str]:
        """取得公司官方網站。"""
        # 104 often puts social links in sameAs
        url = ld.get("sameAs")
        if not url and ld.get("@type") == "Organization":
            url = ld.get("url")
            
        if isinstance(url, list):
            for u in url:
                filtered = self._filter_website(u)
                if filtered: return filtered
        else:
            return self._filter_website(url)
        return None

    def get_company_source_id(self, ld: Dict[str, Any]) -> Optional[str]:
        """提取公司在 104 平台的原始 ID。"""
        url = self.get_company_url(ld)
        if url:
             match = re.search(r"company/([^/?#]+)", url)
             return match.group(1) if match else url.rstrip("/").split("/")[-1]
        return None

    def get_company_address(self, ld: Dict[str, Any]) -> Optional[str]:
        """提取公司總部地址。"""
        addr_node: Any = self._safe_get(ld, "hiringOrganization", "address")
        
        if not addr_node and ld.get("@type") == "Organization":
            addr_node = ld.get("address")
            
        if not addr_node:
            return None
        if isinstance(addr_node, list) and addr_node:
            addr_node = addr_node[0]

        if isinstance(addr_node, str):
            return self._clean_id_noise(self._standardize_taiwan_address_format(addr_node))
            
        if isinstance(addr_node, dict):
            region = self._clean_id_noise(self._standardize_taiwan_address_format(addr_node.get("addressRegion")))
            locality = self._clean_id_noise(self._standardize_taiwan_address_format(addr_node.get("addressLocality")))
            
            # 過濾 Locality 佔位符
            if locality and "Locality" in locality:
                locality = ""

            street = self._clean_id_noise(self._standardize_taiwan_address_format(addr_node.get("streetAddress")))
            
            district = self._dedupe_address([region or "", locality or ""])
            final = self._dedupe_address([district, street or ""])
            return final
        return self._clean_id_noise(str(addr_node))

    def get_industry(self, ld: Dict[str, Any]) -> Optional[str]:
        """從 JSON-LD 或描述內容中提取產業類別。"""
        ind = ld.get("industry")
        if ind: return ind
        
        # 後備方案：從描述中提取
        # 模式： "經營理念 ： 1. [產業] -" 或類似格式
        desc = self.get_description(ld)
        if desc:
            # 尋找 104 常見模式
            match = re.search(r"經營理念\s*[:：].*?(\d+\.\s*)?([^\s\-]+)\s*[\-－]", desc)
            if match:
                return match.group(2)
            
        return None

    def get_work_hours(self, ld: Dict[str, Any]) -> Optional[str]:
        """取得工作時間描述（104 預設為空，由描述中提取或 API 補完）。"""
        wh = ld.get("workHours")
        if isinstance(wh, list):
             return ", ".join(wh) if wh else None
        return wh

    def get_skills(self, ld: Dict[str, Any]) -> Optional[str]:
        """取得技能要求描述（104 預設為空）。"""
        sk = ld.get("skills")
        if isinstance(sk, list):
             return ", ".join(sk) if sk else None
        return sk

    def get_capital(self, ld: Dict[str, Any]) -> Optional[str]:
        """取得資本額資訊。"""
        val = ld.get("capital")
        return self._validate_numeric_noise(val, "capital")

    def get_employee_count(self, ld: Dict[str, Any]) -> Optional[str]:
        """取得員工人數資訊。"""
        val = ld.get("numberOfEmployees")
        return self._validate_numeric_noise(val, "employees")
