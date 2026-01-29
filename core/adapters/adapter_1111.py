"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：adapter_1111.py
功能描述：1111 人力銀行專用的 JSON-LD 適配器。
主要入口：由 AdapterFactory 實例化使用。
"""
import re
import structlog
from typing import Optional, Dict, Any, List
from .jsonld_adapter import JsonLdAdapter
from core.infra import SourcePlatform, CompanyPydantic
from core.utils.parsers import DateParser, SalaryParser, ExperienceParser

logger = structlog.get_logger(__name__)

class Adapter1111(JsonLdAdapter):
    """
    1111 人力銀行適配器。
    針對 1111 平台的 JSON-LD 特殊標籤與巢狀地理資訊進行映射。
    """

    def map_to_company(self, ld: Dict[str, Any], html: Optional[str] = None) -> Optional[CompanyPydantic]:
        """重寫 map_to_company 以處理 1111 特有的 '暫不公開' 邏輯。"""
        company = super().map_to_company(ld, html)
        if not company: return None
        
        # ============ 反幻覺：基於 HTML 內容進行嚴格檢測 ============
        if html:
            from bs4 import BeautifulSoup
            # 輕量級清理 HTML 用於關鍵字檢索
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style"]): tag.decompose()
            text = soup.get_text(separator=" ", strip=True)
            
            # SDD 規範 2.3.1：寧可空白，不可錯誤
            # 若 HTML 明確標註 "員工人數 暫不公開"，則強制設為 NULL
            # 匹配模式: "員工人數" + 分隔符 (冒號、空格) + "暫不公開"
            if re.search(r"員工人數\s*[:：]\s*暫不公開", text) or re.search(r"員工人數.*?暫不公開", text):
                company.employee_count = None
                logger.info("anti_hallucination_employee_count", action="set_null_due_to_tzygk")
            
            # 若 HTML 明確標註 "資本額 暫不公開"，強制設為 NULL
            if re.search(r"資本額\s*[:：]\s*暫不公開", text) or re.search(r"資本額.*?暫不公開", text):
                company.capital = None
                logger.info("anti_hallucination_capital", action="set_null_due_to_tzygk")

        return company

    @property
    def platform(self) -> SourcePlatform:
        """1111 平台識別。"""
        return SourcePlatform.PLATFORM_1111

    def get_description(self, ld: Dict[str, Any]) -> Optional[str]:
        """從 JSON-LD 提取並清洗職缺描述。"""
        from bs4 import BeautifulSoup
        import html as html_lib
        
        desc: Optional[str] = ld.get("description")
        if not desc:
            return None
        
        # 1. 解碼 HTML 實體並清理
        text: str = html_lib.unescape(desc)
        soup = BeautifulSoup(text, "html.parser")
        return soup.get_text(separator=' ', strip=True)


    def get_url(self, ld: dict, fallback_url: str | None = None) -> str:
        """取得職缺正確 URL"""
        return ld.get("url") or fallback_url or ""

    def get_source_id(self, ld: dict, url: str | None = None) -> str | None:
        """取得平台原始 ID"""
        target_url = self.get_url(ld, url)
        match = re.search(r"job/(\d+)", target_url)
        return match.group(1) if match else None

    def get_salary(self, ld: Dict[str, Any]) -> Dict[str, Any]:
        """解析 1111 的薪資結構。"""
        salary_node: Any = ld.get("baseSalary", {}) # Renamed base_salary to salary_node
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

    def get_experience(self, ld: Dict[str, Any]) -> Optional[int]:
        """提取最低經驗年數需求。"""
        return ExperienceParser.parse(ld.get("experienceRequirements"))

    def get_job_type(self, ld: dict) -> str:
        """取得僱用類型"""
        return self._map_job_type(ld.get("employmentType"))


    def get_work_hours(self, ld: dict) -> str | None:
        """取得工作時間"""
        return ld.get("workHours")

    def get_skills(self, ld: dict) -> str | None:
        """取得技能要求"""
        val = ld.get("skills")
        if isinstance(val, list):
            return ",".join([str(v) for v in val])
        return str(val) if val else None



    def get_address(self, ld: Dict[str, Any], html: Optional[str] = None) -> Optional[str]:
        """取得職缺所在地之完整地址。"""
        district: Optional[str] = self.get_district(ld)
        street: Optional[str] = self._standardize_taiwan_address_format(
            self._safe_get(ld, "jobLocation", "address", "streetAddress")
        )
        return self._dedupe_address([district or "", street or ""])
    
    def get_company_name(self, ld: dict) -> str | None:
        """取得公司名稱"""
        # 優先檢查 hiringOrganization (針對 JobPosting 結構)
        name = self._safe_get(ld, "hiringOrganization", "name")
        if name: return name
        # 若 ld 直接是 Organization 類型
        if ld.get("@type") == "Organization":
            return ld.get("name")
        
        # 後備：從 injected title 提取
        title = ld.get("_injected_title") or ld.get("_injected_html_title")
        if title:
             # 1111 標題格式通常是 "公司名稱 | 徵才中 - 1111人力銀行"
             return title.split("|")[0].strip()
        return None

    def get_company_url(self, ld: dict) -> str | None:
        """取得公司在平台的 URL"""
        # 1. 直接從注入的 URL 提取 (針對 corp info 頁面)
        injected_url = ld.get("_url") or ld.get("_source_url")
        if injected_url and "corp/" in str(injected_url):
            return str(injected_url)

        # 2. 在 1111 中，公司詳情通常在 sameAs 或 url 欄位
        if ld.get("@type") == "Organization":
            u = ld.get("url")
            if u and "1111.com.tw" in str(u):
                return u
            # 後備方案：如果 sameAs 看起來像 1111 連結則採納
            same_as = ld.get("sameAs")
            if isinstance(same_as, list):
                for s in same_as:
                    if "1111.com.tw" in str(s):
                        return s
            elif same_as and "1111.com.tw" in str(same_as):
                return same_as
                
        # 針對 JobPosting 結構的後備方案
        url = self._safe_get(ld, "hiringOrganization", "sameAs") or self._safe_get(ld, "hiringOrganization", "url")
        if url: return url
        
        return None

    def get_company_website(self, ld: dict) -> str | None:
        """取得公司官方網站"""
        if ld.get("@type") == "Organization":
            same_as = ld.get("sameAs")
            if isinstance(same_as, list):
                for s in same_as:
                    filtered = self._filter_website(s)
                    if filtered: return filtered
            else:
                return self._filter_website(same_as)
        return None

    def get_company_source_id(self, ld: dict) -> str | None:
        """取得平台特定公司 ID"""
        url = self.get_company_url(ld)
        if url:
             match = re.search(r"corp/(\d+)", url)
             return match.group(1) if match else url.rstrip("/").split("/")[-1]
        return None

    def get_capital(self, ld: dict) -> str | None:
        """
        取得資本額。
        自動過濾隱私保護標記（如「暫不公開」）。
        """
        val = ld.get("capital")
        
        # 使用基類的隱私保護檢測
        if self._is_privacy_protected(val):
            return None
        
        return self._validate_numeric_noise(val, "capital")

    def get_employee_count(self, ld: dict) -> str | None:
        """
        取得員工人數。
        自動過濾隱私保護標記（如「暫不公開」）。
        """
        val = ld.get("numberOfEmployees")
        
        # 使用基類的隱私保護檢測
        if self._is_privacy_protected(val):
            return None
        
        return self._validate_numeric_noise(val, "employees")

    def get_company_address(self, ld: Dict[str, Any]) -> Optional[str]:
        """解析公司詳細地址並處理 1111 特有的逗號分隔格式。"""
        addr_node: Any = None
        if ld.get("@type") == "JobPosting":
             addr_node = self._safe_get(ld, "hiringOrganization", "address")
        else:
             addr_node = ld.get("address") or self._safe_get(ld, "jobLocation", "address")
        
        if not addr_node:
            return None
        
        if isinstance(addr_node, str):
            return self._standardize_taiwan_address_format(addr_node)
        
        # 結構化地址解析
        region: Optional[str] = self._standardize_taiwan_address_format(addr_node.get("addressRegion"))
        locality: Optional[str] = self._standardize_taiwan_address_format(addr_node.get("addressLocality"))
        street: Optional[str] = self._standardize_taiwan_address_format(addr_node.get("streetAddress"))
        
        # 1111 特殊處理：addressLocality 可能包含 "台灣,台中市,北屯區"
        if locality and "," in locality:
            parts: List[str] = [self._standardize_taiwan_address_format(p.strip()) or "" for p in locality.split(",")]
            locality = "".join([p for p in parts if p])

        district: str = self._dedupe_address([region or "", locality or ""])
        return self._dedupe_address([district, street or ""])

