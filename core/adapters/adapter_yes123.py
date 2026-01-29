"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：adapter_yes123.py
功能描述：yes123 求職網專用的 JSON-LD 適配器。
主要入口：由 AdapterFactory 實例化使用。
"""
import re
from typing import Optional, Dict, Any, List
from .jsonld_adapter import JsonLdAdapter
from core.infra import SourcePlatform, CompanyPydantic
from core.utils.parsers import DateParser, SalaryParser, ExperienceParser

class AdapterYes123(JsonLdAdapter):
    """
    Yes123 求職網適配器。
    針對 Yes123 平台的 JSON-LD 結構進行映射，並包含針對該平台 HTML 結構設計的深度提取邏輯。
    """

    @property
    def platform(self) -> SourcePlatform:
        """Yes123 平台識別。"""
        return SourcePlatform.PLATFORM_YES123

    def map_to_company(self, ld: Dict[str, Any], html: Optional[str] = None) -> Optional[CompanyPydantic]:
        """重寫 map_to_company 以處理 Yes123 特有的 '暫不公開' 或隱藏資訊邏輯。"""
        company = super().map_to_company(ld, html)
        if not company: return None

        if html:
            from bs4 import BeautifulSoup
            
            # 若 HTML 明確標註 "員工人數：暫不公開" 或類似語意，強制清除誤判值
            # Yes123 的標籤通常是 "員工人數：" 然後接 "暫不公開"
            if "員工人數" in html and "暫不公開" in html:
                # 做更嚴謹的檢查
                soup = BeautifulSoup(html, "html.parser")
                text = soup.get_text(separator=" ", strip=True)
                if re.search(r"員工人數[:：\s]*暫不公開", text):
                    company.employee_count = None
            
            if "資本額" in html and "暫不公開" in html:
                 soup = BeautifulSoup(html, "html.parser")
                 text = soup.get_text(separator=" ", strip=True)
                 if re.search(r"資本額[:：\s]*暫不公開", text):
                    company.capital = None

        return company

    def get_title(self, ld: dict) -> str | None:
        """取得職缺標題"""
        return ld.get("name") or ld.get("title")

    def get_description(self, ld: Dict[str, Any]) -> Optional[str]:
        """取得職缺描述並清洗 HTML 標籤。"""
        from bs4 import BeautifulSoup
        import html as html_lib
        
        desc: Optional[str] = ld.get("description")
        if not desc:
            return None
        
        text: str = html_lib.unescape(desc)
        soup = BeautifulSoup(text, "html.parser")
        return soup.get_text(separator=' ', strip=True)

    def get_url(self, ld: dict, fallback_url: str | None = None) -> str:
        """取得職缺正確 URL"""
        url = ld.get("url") or fallback_url or ""
        if url.startswith("/"):
             return f"https://www.yes123.com.tw{url}"
        return url

    def get_source_id(self, ld: dict, url: str | None = None) -> str | None:
        """取得平台原始 ID (結合 p_id 與 job_id)"""
        target_url = self.get_url(ld, url)
        # 處理來自新版 wk_index URL 的 p_id 與 job_id
        p_match = re.search(r"p_id=([^&]+)", target_url)
        j_match = re.search(r"job_id=([^&]+)", target_url)
        
        if p_match and j_match:
             return f"{p_match.group(1)}_{j_match.group(1)}"
        return p_match.group(1) if p_match else None


    def get_salary(self, ld: Dict[str, Any]) -> Dict[str, Any]:
        """解析 Yes123 的薪資結構。"""
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
        edu = ld.get("educationRequirements")
        if isinstance(edu, list) and edu:
            edu = edu[0]
        if isinstance(edu, dict):
            edu = edu.get("credentialCategory") or edu.get("name") or str(edu)
        return self._map_education_text(str(edu) if edu else None)

    def get_experience(self, ld: Dict[str, Any]) -> Optional[int]:
        """提取最低經驗年數。"""
        return ExperienceParser.parse(ld.get("experienceRequirements"))

    def get_job_type(self, ld: dict) -> str:
        """取得僱用類型"""
        return self._map_job_type(ld.get("employmentType"))


    def get_company_name(self, ld: dict) -> str | None:
        """取得公司名稱"""
        name = self._safe_get(ld, "hiringOrganization", "name")
        if name: return name
        if ld.get("@type") == "Organization":
            return ld.get("name")
            
        # 後備方案：從注入的 HTML title 解析
        title = ld.get("_injected_html_title") or ld.get("_injected_title") # 支援多種注入路徑
        if title:
            # 清理： "焱芝手工皂-工作徵才簡介｜yes123" -> "焱芝手工皂"
            # 或者是 "長流機構 | 徵才中..."
            name = title.split("-")[0].split("｜")[0].split("|")[0].strip()
            if "人力銀行" not in name and name:
                return name
        return None

    def get_company_url(self, ld: dict) -> str | None:
        """取得公司在平台的 URL"""
        # 在 Yes123 中，sameAs 通常包含平台簡介連結
        url = self._safe_get(ld, "hiringOrganization", "sameAs") or self._safe_get(ld, "hiringOrganization", "url")
        if url: return url
        if ld.get("@type") == "Organization":
            return ld.get("sameAs") or ld.get("url")
            
        # Fallback: 若無顯式 URL 但有 source_id (p_id)，則主動建構
        sid = self.get_company_source_id(ld)
        if sid:
            return f"https://www.yes123.com.tw/wk_index/comp_info.asp?p_id={sid}"
            
        return None

    def get_salary_currency(self, ld: dict) -> str | None:
        """取得薪資貨幣"""
        return "TWD"

    # ========== 地點相關 ==========
    def get_address_country(self, ld: dict) -> str | None:
        """取得國家代碼 (支援海外判斷)"""
        # 檢查 addressRegion 是否有海外指標
        region = self._safe_get(ld, "jobLocation", "address", "addressRegion")
        locality = self._safe_get(ld, "jobLocation", "address", "addressLocality")
        
        if region:
            # 海外關鍵字
            overseas_regions = ["亞洲", "美洲", "歐洲", "大洋洲", "非洲", "港澳"]
            if any(r in region for r in overseas_regions):
                # 嘗試在 locality 中尋找具體國家 (例如 "東南亞越南" -> "越南")
                if locality:
                     countries = ["越南", "日本", "美國", "中國", "泰國", "菲律賓", "印尼", "馬來西亞", "新加坡", "韓國", "英國", "德國", "法國", "澳洲"]
                     for c in countries:
                         if c in locality:
                             return c
                     
                     return locality.replace("地區", "").replace("東南亞", "").replace("東北亞", "")
                
                return region
        
        return "TW"


    def get_address(self, ld: Dict[str, Any], html: Optional[str] = None) -> Optional[str]:
        """取得職缺所在地之完整地址。"""
        district: Optional[str] = self.get_district(ld)
        street: Optional[str] = self._standardize_taiwan_address_format(
            self._safe_get(ld, "jobLocation", "address", "streetAddress")
        )
        return self._dedupe_address([district or "", street or ""])


    def get_company_website(self, ld: dict) -> str | None:
        """取得公司官方網站"""
        return self._filter_website(ld.get("company_web"))

    def get_company_source_id(self, ld: dict) -> str | None:
        """取得平台特定公司 ID"""
        # 0. 優先從注入的 URL 提取 (針對 corp info 頁面)
        injected_url = ld.get("_url") or ld.get("_source_url")
        if injected_url:
            match = re.search(r"p_id=([^&]+)", str(injected_url))
            if match:
                sid = match.group(1)
                if sid and "yes123" not in sid.lower():
                    return sid

        # 1. 嘗試從 hiringOrganization sameAs 取得
        # NOTE: 此處不調用 get_company_url 以免無限遞迴
        url = self._safe_get(ld, "hiringOrganization", "sameAs") or self._safe_get(ld, "hiringOrganization", "url")
        if url:
            match = re.search(r"p_id=([^&]+)", url)
            if match:
                sid = match.group(1)
                if sid and "yes123" not in sid.lower():
                    return sid

        return None

    def get_company_address(self, ld: Dict[str, Any]) -> Optional[str]:
        """提取公司地址，支援 JobPosting 與 Organization 結構。"""
        addr_node: Any = self._safe_get(ld, "hiringOrganization", "address")
        
        if not addr_node and ld.get("@type") == "Organization":
            addr_node = ld.get("address")
            
        if not addr_node:
            return None
        if isinstance(addr_node, str):
            val = self._standardize_taiwan_address_format(addr_node)
            return val if val else None
            
        region: Optional[str] = self._standardize_taiwan_address_format(addr_node.get("addressRegion"))
        locality: Optional[str] = self._standardize_taiwan_address_format(addr_node.get("addressLocality"))
        street: Optional[str] = self._standardize_taiwan_address_format(addr_node.get("streetAddress"))
        district: str = self._dedupe_address([region or "", locality or ""])
        val = self._dedupe_address([district, street or ""])
        return val if val else None


    def get_work_hours(self, ld: Dict[str, Any]) -> Optional[str]:
        """取得工作時間描述。"""
        wh: Any = ld.get("workHours")
        if isinstance(wh, list):
             return ", ".join(map(str, wh)) if wh else None
        return str(wh) if wh else None

    def get_skills(self, ld: Dict[str, Any]) -> Optional[str]:
        """取得技能要求描述。"""
        sk: Any = ld.get("skills")
        if isinstance(sk, list):
             return ", ".join(map(str, sk)) if sk else None
        return str(sk) if sk else None

    def get_capital(self, ld: Dict[str, Any]) -> Optional[str]:
        """取得資本額資訊。"""
        val = ld.get("capital")
        return self._validate_numeric_noise(val, "capital")

    def get_employee_count(self, ld: Dict[str, Any]) -> Optional[str]:
        """取得員工人數資訊，過濾掉可能是預設值的 '1'。"""
        emp: Any = ld.get("numberOfEmployees")
        result: Optional[str] = None
        if isinstance(emp, dict):
            result = f"{emp.get('value')}{emp.get('unitText', '')}"
        else:
            result = str(emp) if emp else None
            
        return self._validate_numeric_noise(result, "employees")

    def _extract_company_field_from_html(self, html: str, field_type: str) -> Optional[str]:
        """
        針對 Yes123 頁面結構深度提取公司資訊。
        
        Args:
            html (str): 原始網頁 HTML。
            field_type (str): 目標欄位類型 ('capital', 'employees', 'address', 'description')。
            
        Returns:
            Optional[str]: 提取到的內容，查無結果則回傳 None。
        """
        from bs4 import BeautifulSoup, Tag
        soup = BeautifulSoup(html, "html.parser")
        
        # 定義 Yes123 常見標籤關鍵字
        mapping: Dict[str, List[str]] = {
            "capital": ["資本額：", "資本金額：", "本金額：", "資本額", "資本金額", "本金額"],
            "employees": ["員工人數：", "員工數：", "員工人數", "員工數"],
            "address": ["企業地址：", "公 司 地 址：", "公司地址："],
            "description": ["企業簡介", "經營理念", "主要商品", "行業說明", "公司簡介"]
        }
        
        target_labels: Optional[List[str]] = mapping.get(field_type)
        if not target_labels:
             return super()._extract_company_field_from_html(html, field_type)

        if field_type == "description":
            parts: List[str] = []
            for label in target_labels:
                title_node = soup.find(string=lambda s: s and label in s)
                if title_node and title_node.parent:
                    el: Tag = title_node.parent
                    # 向上尋找包含足夠內容的容器
                    if len(el.get_text(strip=True)) < len(label) + 5:
                        parent_el = el.parent
                        if isinstance(parent_el, Tag):
                            el = parent_el
                    
                    full_text: str = el.get_text(separator=" ", strip=True)
                    if label in full_text:
                        val: str = full_text.split(label)[-1].strip().strip("：").strip(":")
                        if len(val) > 10 and not val.startswith("---"):
                             parts.append(f"【{label}】\n{val}")
            
            if parts:
                return "\n\n".join(parts)
            return super()._extract_company_field_from_html(html, field_type)
        else:
            # 處理資本額、員工人數、地址等單一欄位
            for label in target_labels:
                # 搜尋包含關鍵字的文字節點
                nodes: List[Any] = soup.find_all(string=lambda s: s and label in s)
                for node in nodes:
                    if not node.parent:
                        continue
                        
                    parent_text: str = node.parent.get_text(separator=" ", strip=True)
                    # 方式 1: 在同一 DOM 節點中匹配 Label 後方內容
                    match = re.search(f"{re.escape(label)}\\s*(?:[:：\\s]|<[^>]+>)*\\s*([^\\s,，|]{2,})", parent_text)
                    if match:
                        val: str = match.group(1).strip().strip("：").strip(":")
                        val = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9_\-\s.#（）\(\)]", "", val).strip()
                        
                        if field_type == "employees" and val.replace(" ", "") in ["1", "1人", "0", "0人"]:
                            continue
                        if val and len(val) < 100:
                            return val
                    
                    # 方式 2: 尋找相鄰的下一個 HTML 節點 (Sibling)
                    sib = node.parent.find_next_sibling()
                    if isinstance(sib, Tag):
                        val = sib.get_text(strip=True).strip("：").strip(":")
                        val = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9_\-\s.#（）\(\)]", "", val).strip()
                        
                        if field_type == "employees" and val.replace(" ", "") in ["1", "1人", "0", "0人"]:
                            continue
                        if val and len(val) < 100:
                            return val
            
        # 若上方平台專用邏輯未命中，則調用基類通用邏輯
        result: Optional[str] = super()._extract_company_field_from_html(html, field_type)
        if result and field_type == "employees" and result.replace(" ", "") in ["1", "1人", "0", "0人"]:
             return None
        return result

