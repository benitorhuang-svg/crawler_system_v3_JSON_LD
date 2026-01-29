"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：jsonld_adapter.py
功能描述：JSON-LD 平台適配器基類，定義欄位映射介面、正則表達式提取邏輯與資料清洗工具。
"""

import json
import re
import html as html_lib
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Union, Type, Set
from datetime import date
from bs4 import BeautifulSoup

from core.infra import (
    CompanyPydantic,
    JobPydantic,
    SalaryType,
    SourcePlatform,
)
from core.utils.parsers import SalaryParser, DateParser, ExperienceParser


class JsonLdAdapter(ABC):
    """
    JSON-LD 平台適配器基類。
    提供從半結構化 JSON-LD 數據提取職缺與公司資訊的標準化方法，並包含強大的正則補償機制。
    """

    # ========== 預編譯正則表達式 ==========
    RE_CAPITAL: List[re.Pattern[str]] = [
        re.compile(r"資本額\s*(?:[:：\s]|<[^>]+>)*\s*([^<|、{}[\"']{2,50})", re.IGNORECASE | re.DOTALL),
        re.compile(r"capital\s*(?:[:：\s]|<[^>]+>)*\s*([^<|、{}[\"']{2,50})", re.IGNORECASE | re.DOTALL),
        re.compile(r"\"capital\"\s*[:：]\s*\"([^\"]+)\"", re.IGNORECASE),
        re.compile(r"basic-info__icon--capital[^>]*>([^<]+)", re.IGNORECASE | re.DOTALL),
        # 通用模式：僅在包含 萬/億 時才視為資本額，避免誤抓薪資或價格 (e.g., 400元)
        re.compile(r"((?:NT\$|TWD|USD|HKD)?\s*[\d\.,]{1,10}\s*[億萬]{1,2}(?:[\d\.,]+\s*[萬元]{1,2})?)(?!\d)", re.IGNORECASE),
    ]
    RE_EMPLOYEES: List[re.Pattern[str]] = [
        re.compile(r"員工人數\s*(?:[:：\s]|<[^>]+>)*\s*([^<|、]{2,50})", re.IGNORECASE | re.DOTALL),
        re.compile(r"員工數\s*(?:[:：\s]|<[^>]+>)*\s*([^<|、]{2,50})", re.IGNORECASE | re.DOTALL),
        re.compile(r"公司規模\s*(?:[:：\s]|<[^|、]{2,50})", re.IGNORECASE | re.DOTALL),
        re.compile(r"\"emp\"\s*[:：]\s*\"([^\"]+)\"", re.IGNORECASE),
        re.compile(r"basic-info__icon--scale[^>]*>([^<]+)", re.IGNORECASE | re.DOTALL),
        # 通用模式移至最後
        re.compile(r"(?<![a-zA-Z\d])(\d{1,7}(?:[~,-、〜]\d{1,7})?\s*人)(?![a-zA-Z\d])", re.IGNORECASE | re.DOTALL),
    ]
    RE_WEB: List[re.Pattern[str]] = [
        re.compile(r"(?:公司網址|官方網站|官網|企業網址|Official Website|Company Website|Website)\s*(?:[:：\s]|<[^>]+>)*\s*<a[^>]+href=[\"'](https?://[^\"']+)[\"']", re.IGNORECASE | re.DOTALL),
        re.compile(r"href\s*=\s*[\"'](https?://(?!www\.104|static\.104|www\.1111|www\.yes123|www\.cake|www\.yourator|facebook|twitter|instagram|linkedin|youtube|line\.me|google|apple|github|onelink|fonts|ajax|cdn|static|assets|nat\.gov|moea\.gov|maps\.google)[^\"']+)[\"']", re.IGNORECASE | re.DOTALL),
    ]
    RE_ADDRESS: List[re.Pattern[str]] = [
        re.compile(r"([\u4e00-\u9fff]{2}[縣市][\u4e00-\u9fff]{1,5}?[區市鎮鄉][^<{}\"']{5,})"),
        re.compile(r"(?:公司地址|公司位置|企業地址|通訊地址|地址|Address)\s*(?:[:：\s]|<[^>]+>)*\s*([^<|{}[\"']{5,})", re.IGNORECASE | re.DOTALL),
        re.compile(r"basic-info__address[^>]*>(?:<[^>]+>)*([^<{}[\"']{5,})", re.IGNORECASE | re.DOTALL),
    ]
    RE_DESCRIPTION: List[re.Pattern[str]] = [
        re.compile(r"(?:公司簡介|公司介紹|企業簡介|經營理念|主要商品|行業說明|福利制度|About Us)\s*(?:[:：\s]|<[^>]+>)*\s*<(?:div|p|section|article)[^>]*>(.*?)</(?:div|p|section|article)>", re.IGNORECASE | re.DOTALL),
        re.compile(r"(?:公司簡介|公司介紹|企業簡介|經營理念|主要商品|行業說明|福利制度|About Us)\s*(?:[:：\s]|<[^>]+>)*\s*([^<]{10,})", re.IGNORECASE | re.DOTALL),
    ]
    RE_NOISE: re.Pattern[str] = re.compile(r'[\s\-\─\=＞\>\<\!\*\#\_\~]+')
    RE_CJK_OR_LETTER: re.Pattern[str] = re.compile(r'[\u4e00-\u9fffA-Za-z0-9]')
    RE_TAIWAN_START: re.Pattern[str] = re.compile(r"^(台灣|臺灣|Taiwan|台灣省|臺灣省|中華民國)[,，\s]*")
    RE_TAIWAN_END: re.Pattern[str] = re.compile(r"[,，\s]*(台灣|臺灣|Taiwan|台灣省|臺灣省)$")
    RE_TAIWAN_ANY: re.Pattern[str] = re.compile(r"(台灣|臺灣|Taiwan|台灣省|臺灣省|中華民國)")
    RE_ADDRESS_FIX: re.Pattern[str] = re.compile(r"(\d+\s*[號樓及Ff])\s+([^\s,;，；]{2,}(?:[路街巷大道段]))")
    RE_ID_NOISE: re.Pattern[str] = re.compile(r'no\s*=\s*["\'][\w\d]+["\']', re.IGNORECASE)
    RE_CITY: re.Pattern[str] = re.compile(r"([^\s,，]{2,3}(?:縣|市))")
    
    # 座標解析 (從 Google Maps URL)
    RE_GEO_URL: List[re.Pattern[str]] = [
        re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)", re.IGNORECASE), # @25.0512786,121.5167936
        re.compile(r"ll=(-?\d+\.\d+),(-?\d+\.\d+)", re.IGNORECASE), # ll=25.033923,121.525422
        re.compile(r"q=(-?\d+\.\d+),\s*(-?\d+\.\d+)", re.IGNORECASE), # q=25.033923,121.525422
        re.compile(r"([-?\d\.]+)\"N\s+([-?\d\.]+)\"E", re.IGNORECASE), # 25°02'02.1"N 121°31'31.5"E (簡化匹配)
    ]
    RE_DISTRICT: re.Pattern[str] = re.compile(r"([\u4e00-\u9fff]{1,5}?[區市鎮鄉])")
    RE_CITY_DISTRICT: re.Pattern[str] = re.compile(r"([\u4e00-\u9fff]{2}[縣市])([\u4e00-\u9fff]{1,5}?[區市鎮鄉])")
    RE_WHITESPACE: re.Pattern[str] = re.compile(r"\s+")
    RE_NUMERIC_ONLY: re.Pattern[str] = re.compile(r'[\d\.]+')
    RE_YI: re.Pattern[str] = re.compile(r'([\d\.]+)(?=億)')
    RE_WAN: re.Pattern[str] = re.compile(r'([\d\.]+)(?=萬)')
    RE_DIGITS_ONLY: re.Pattern[str] = re.compile(r'[^\d]')
    
    # 用於截斷過長匹配的欄目標籤（避免欄位滲透）
    RE_FIELD_LABELS: re.Pattern[str] = re.compile(
        r"(?:行業類別|企業電話|企業地址|相關連結|成立時間|經營項目|資本額|員工人數|公司規模|聯絡人|傳真|公司網址|公司位置|產業類別|產業描述|負責人|統一編號|福利制度|企業職缺|地址|電話|傳真)",
        re.IGNORECASE
    )
    
    # 反幻覺檢測：隱私保護關鍵字
    PRIVACY_PROTECTED_KEYWORDS: Set[str] = {
        "暫不公開", "未公開", "保密", "面議", "暫不提供", "non-disclosure",
        "not-disclosed", "on request", "to be confirmed"
    }
    @abstractmethod
    def platform(self) -> SourcePlatform:
        pass

    # ========== 映射方法 ==========

    def map_to_job(self, ld: Dict[str, Any], url: str, html: Optional[str] = None) -> Optional[JobPydantic]:
        title = ld.get("title") or ld.get("name")
        source_id = self.get_source_id(ld, url)
        if not title or not source_id: return None

        salary = self.get_salary(ld)
        addr = self.get_address(ld, html=html)
        return JobPydantic(
            platform=self.platform,
            url=self.get_url(ld, url),
            source_id=source_id,
            company_source_id=self.get_company_source_id(ld),
            title=title,
            description=self.get_description(ld),
            industry=self.get_industry(ld),
            job_type=self.get_job_type(ld),
            work_hours=self.get_work_hours(ld),
            salary_currency=self.get_salary_currency(ld),
            salary_type=salary.get("type"),
            salary_text=salary.get("text"),
            salary_min=salary.get("min"),
            salary_max=salary.get("max"),
            address_country=self.get_address_country(ld),
            address=addr,
            region=self.get_region(ld, address_hint=addr),
            district=self.get_district(ld, address_hint=addr),
            experience_min_years=self.get_experience(ld),
            education_text=self.get_education(ld),
            skills=self.get_skills(ld),
            posted_at=DateParser.parse(self.get_posted_date(ld)),
            valid_through=DateParser.parse(self.get_valid_through(ld)),
        )

    def map_to_company(self, ld: Dict[str, Any], html: Optional[str] = None) -> Optional[CompanyPydantic]:
        name = self.get_company_name(ld)
        source_id = self.get_company_source_id(ld)
        if not name or not source_id: return None

        url = self.get_company_url(ld)
        web = self.get_company_website(ld)
        addr = self.get_company_address(ld)
        capital = self.get_capital(ld)
        employees = self.get_employee_count(ld)
        desc = ld.get("description") if ld.get("@type") == "Organization" else None

        if html:
            if not web: web = self._extract_company_field_from_html(html, "web")
            new_addr = self._extract_company_field_from_html(html, "address")
            if new_addr:
                 # 針對 HTML 提取結果進行標準化清洗
                 new_addr = self._standardize_taiwan_address_format(new_addr)
            
            if new_addr and (not addr or len(new_addr) > len(addr)): addr = new_addr
                    
            if not capital or self._is_minimalist(capital):
                new_capital = self._extract_company_field_from_html(html, "capital")
                # 針對 HTML 提取結果進行嚴格校驗
                new_capital = self._validate_numeric_noise(new_capital, "capital")
                if new_capital and (not capital or len(new_capital) >= len(str(capital))): capital = new_capital
            
            if not employees or self._is_minimalist(employees):
                new_employees = self._extract_company_field_from_html(html, "employees")
                # 針對 HTML 提取結果進行嚴格校驗
                new_employees = self._validate_numeric_noise(new_employees, "employees")
                if new_employees and (not employees or len(new_employees) >= len(str(employees))): employees = new_employees
                    
            if not desc: 
                candidate = self._extract_company_field_from_html(html, "description")
                if candidate and self._is_meaningful_text(candidate): desc = candidate

        # 全域數據嚴格校驗
        capital = self._validate_numeric_noise(capital, "capital")
        employees = self._validate_numeric_noise(employees, "employees")

        return CompanyPydantic(
            platform=self.platform,
            source_id=source_id,
            name=name,
            company_url=url,
            company_web=self._filter_website(web),
            address=addr,
            capital=self._standardize_numeric(capital),
            employee_count=self._standardize_numeric(employees),
            description=desc,
        )

    # ========== 輔助與清洗工具 ==========

    @staticmethod
    def _is_privacy_protected(val: Any) -> bool:
        """
        檢測字段值是否被隱私保護標記（如「暫不公開」）。
        用於防止HTML爬蟲或JSON-LD幻覺產生的虛假數據。
        
        Args:
            val: 要檢測的字段值（可能是 None, str, dict 等）
            
        Returns:
            True 若值表示隱私保護或不公開，False 否則
        """
        if not val:
            return False
        
        s = str(val).strip().lower()
        return any(kw in s for kw in JsonLdAdapter.PRIVACY_PROTECTED_KEYWORDS)

    @staticmethod
    def _is_minimalist(val: Any) -> bool:
        """判斷原始數據是否過於簡略（需進一步從 HTML 補全）。"""
        if not val: return True
        s = str(val).strip()
        return len(s) < 2 or s.isdigit()

    @staticmethod
    def _standardize_numeric(val: Any) -> Optional[str]:
        """將各種數值描述轉換為純數字或標準範圍 (如 1000000 或 1~5)。"""
        if not val: return None
        s = str(val).strip()
        
        # 0. 基礎清理
        s = s.replace(",", "").replace(" ", "").replace("NT$", "").replace("TWD", "")
        
        # 1. 處理億/萬
        has_yi = "億" in s
        has_wan = "萬" in s
        
        num_part = JsonLdAdapter.RE_NUMERIC_ONLY.search(s)
        if num_part:
            num = float(num_part.group())
            if has_yi: num *= 100000000
            elif has_wan: num *= 10000
            
            # 若是員工人數類型的範圍 (如 1-5人)
            if "人" in s and ("-" in s or "~" in s or "、" in s):
                nums = re.findall(r"\d+", s)
                if nums: return f"{nums[0]}~{nums[-1]}"
                
            return str(int(num))
        
        return s if s else None

    @staticmethod
    def _validate_numeric_noise(val: Any, field_type: str) -> Any:
        """針對數值產出的數值進行嚴格校驗，防範幻覺與漏爬。"""
        if not val:
            return None
        
        # 0. 先檢測隱私保護標記
        if JsonLdAdapter._is_privacy_protected(val):
            return None
        
        # 1. 先行標準化，將 "1萬" 轉為 "10000" 以便數值比對
        std_val = JsonLdAdapter._standardize_numeric(val)
        if not std_val:
            return None # 無法標準化的數值視為無效
            
        s = str(std_val).strip().replace(",", "").replace("元", "").replace("人", "").replace("員", "").replace("名", "")
        
        # 2. 員工人數校驗：過短的純數字通常是雜訊 (如 "2" 或 "5" 頁碼誤爬)
        if field_type == "employees":
             # 員工人數下限：2 (單人公司通常不標註或標註 1，但爬蟲誤抓機率極高)
             # NOTE: 允許 2~9 人的小規模公司，移除長度 < 2 的檢查
             if s.isdigit() and int(s) < 2:
                 return None

        # 3. 資本額校驗
        if field_type == "capital":
            # 排除非數值但包含特殊關鍵字的 (如 "-private-equity")
            if "private-equity" in s.lower() or "funded" in s.lower():
                return None
            
            # 資本額下限：100,000 (10萬)
            # 理由：網站上標註的 40000/50000 等數值極大機率是月薪洩漏
            try:
                if float(s) < 100000:
                    return None
            except ValueError:
                pass
                
            # 若數值過短 (且是純數字)
            if len(s) < 4 and s.replace(".", "").isdigit():
                return None

        # 4. 通用雜訊詞過濾
        noise = [
            "電聯", "先生", "小姐", "人力銀行", 
            "1111", "yes123", "104", "yourator", "cakeresume", "cake.me",
            "locality"
        ]
        if any(k.lower() in s.lower() for k in noise):
            return None
                
        # 5. 針對 104 等平台名誤入的純數字校驗
        if s == "104" or s == "1111":
            return None
                
        # 回傳標準化後的值，避免後續重複處理
        return std_val

    def _is_meaningful_text(self, text: str) -> bool:
        if not text: return False
        clean = self.RE_NOISE.sub('', text)
        if len(text) > 0 and (len(clean) / len(text)) < 0.3: return False
        if len(clean) < 10: return False
        if not self.RE_CJK_OR_LETTER.search(clean): return False
        return True

    def _extract_company_field_from_html(self, html_content: str, field_type: str) -> Optional[str]:
        if not html_content: return None
        soup = BeautifulSoup(html_content, "html.parser")
        for tag in soup(["script", "style"]): tag.decompose()
        clean_html = soup.get_text(separator=" ", strip=True)
        clean_html = html_lib.unescape(clean_html)
        
        patterns_map = {"capital": self.RE_CAPITAL, "employees": self.RE_EMPLOYEES, "web": self.RE_WEB, "address": self.RE_ADDRESS, "description": self.RE_DESCRIPTION}
        for pattern_idx, pattern in enumerate(patterns_map.get(field_type, [])):
            # 優先在大文本中搜尋 (包含標籤，對描述特別有用)
            search_target = html_content if "<" in pattern.pattern and ">" in pattern.pattern else clean_html
            for match in pattern.finditer(search_target):
                try: val = match.group(1).strip()
                except IndexError: val = match.group(0).strip()
                
                # 如果是描述，需要額外清理 HTML 標籤
                if field_type == "description" and "<" in val:
                    val = BeautifulSoup(val, "html.parser").get_text(separator=" ", strip=True)
                
                val = self.RE_WHITESPACE.sub(" ", html_lib.unescape(val.replace("\xa0", " "))).strip()
                if not val: continue
                
                # 1. 跳過「暫不公開」類型的預設值
                # CRITICAL: 僅當「整個值」或「開頭」就是雜訊時，才視為不公開。
                # 避免 bleeding (例如 "1386億 統一編號 暫不公開") 誤殺。
                noise_keywords: List[str] = ["暫不公開", "未公開", "保密", "面議", "暫不提供", "n/a", "null", "none"]
                
                # 特殊處理：如果有 bleeding，截斷它
                for nk in ["統一編號", "員工人數", "員工數", "公司地址", "企業地址"]:
                    if nk in val: val = val.split(nk)[0].strip()
                
                if any(val.lower() == nk or val.lower().startswith(nk) for nk in noise_keywords):
                    if pattern_idx < len(patterns_map.get(field_type, [])) - 1:
                         return None
                    continue
                
                # 截斷：如果匹配內容中包含其他欄目標籤，則從該處截斷（防止欄位滲透）
                label_match = self.RE_FIELD_LABELS.search(val)
                if label_match:
                    val = val[:label_match.start()].strip()

                if not val: continue # 截斷後可能變空

                # 2. 跳過平台名稱洩漏 (例如 1111, yes123)
                platform_noise: List[str] = ["1111", "yes123", "人力銀行"]
                # 若值剛好是平台名稱，或是平台名稱開頭且太短，則跳過
                clean_val = val.replace(" ", "").replace("人", "").replace("元", "")
                if clean_val in platform_noise: continue
                
                if field_type == "address" and any(ns in val.lower() for ns in ["flex", "grid", "rgba"]): continue
                if field_type == "web":
                    val = self._filter_website(val)
                    if not val: continue
                if field_type in ["capital", "employees"]:
                    has_digit = any(char.isdigit() for char in val); has_kw = any(kw in val for kw in ["萬", "億", "人", "員", "名", "位", "~", "-", "〜"])
                    if not (has_digit or has_kw): continue
                    if any(c in val for c in ["{", "}", ":", ";", "=", "@"]): continue
                    if len(val) > 40: continue
                return val
        return None

    def _parse_taiwan_location(self, ld: Dict[str, Any], address_hint: Optional[str] = None) -> Dict[str, Optional[str]]:
        text = address_hint or ""
        if not text:
            node = self._safe_get(ld, "jobLocation", "address")
            if isinstance(node, dict): text = f"{node.get('addressRegion','')}{node.get('addressLocality','')}{node.get('streetAddress','')}"
            elif isinstance(node, str): text = node
        reg = dist = None
        if text:
            text = self._clean_taiwan(text)
            m_cd = self.RE_CITY_DISTRICT.search(text)
            if m_cd:
                reg = m_cd.group(1)
                dist = m_cd.group(1) + m_cd.group(2)
            else:
                m_c = self.RE_CITY.search(text)
                if m_c: reg = m_c.group(1)
                m_d = self.RE_DISTRICT.search(text)
                if m_d: dist = (reg or "") + m_d.group(1)
        return {"region": reg, "district": dist}

    def _clean_taiwan(self, text: Optional[str]) -> str:
        if not text: return ""
        s = str(text)
        s = self.RE_TAIWAN_START.sub("", s)
        s = self.RE_TAIWAN_END.sub("", s)
        return s.strip()

    # ========== Getter 方法 ==========
    def get_salary(self, ld: Dict[str, Any]) -> Dict[str, Any]:
        base = self._safe_get(ld, "baseSalary")
        if not base: return SalaryParser.parse("面議")
        v = base.get("value")
        if isinstance(v, dict):
            min_v = v.get("minValue")
            max_v = v.get("maxValue") or v.get("value")
        else: min_v = max_v = v
        return SalaryParser.parse(f"{min_v or ''}-{max_v or ''}")

    def get_education(self, ld: Dict[str, Any]) -> str:
        edu = ld.get("educationRequirements")
        if isinstance(edu, list) and edu: edu = edu[0]
        if isinstance(edu, dict): edu = edu.get("credentialCategory") or edu.get("name")
        return self._map_education_text(str(edu)) if edu else "不拘"

    def get_experience(self, ld: Dict[str, Any]) -> Optional[int]:
        ext = ld.get("experienceRequirements")
        if isinstance(ext, list) and ext: ext = ext[0]
        if isinstance(ext, dict): ext = ext.get("name") or ext.get("description")
        return ExperienceParser.parse(str(ext)) if ext else None

    def get_job_type(self, ld: Dict[str, Any]) -> str:
        return self._map_job_type(ld.get("employmentType"))

    def get_posted_date(self, ld: Dict[str, Any]) -> Optional[str]:
        return DateParser.parse_iso_date(ld.get("datePosted"))

    def get_valid_through(self, ld: Dict[str, Any]) -> Optional[str]:
        return DateParser.parse_iso_date(ld.get("validThrough"))

    def get_industry(self, ld: Dict[str, Any]) -> Optional[str]:
        return ld.get("industry")

    @abstractmethod
    def get_work_hours(self, ld: Dict[str, Any]) -> Optional[str]: pass
    @abstractmethod
    def get_skills(self, ld: Dict[str, Any]) -> Optional[str]: pass

    def get_description(self, ld: Dict[str, Any]) -> Optional[str]:
        """取得職缺描述，預設從 description 欄位提取並清理 HTML。"""
        from bs4 import BeautifulSoup
        import html as html_lib
        desc = ld.get("description")
        if not desc: return None
        text = html_lib.unescape(str(desc))
        soup = BeautifulSoup(text, "html.parser")
        return soup.get_text(separator=' ', strip=True)

    def get_salary_currency(self, ld: Dict[str, Any]) -> Optional[str]:
        return self._safe_get(ld, "baseSalary", "currency") or "TWD"

    def get_latitude(self, ld: Dict[str, Any], html: Optional[str] = None) -> Optional[float]:
        v = self._safe_get(ld, "jobLocation", "geo", "latitude") or self._safe_get(ld, "jobLocation", 0, "geo", "latitude") or self._safe_get(ld, "geo", "latitude")
        if v:
            try: return float(v)
            except: pass
            
        if html:
            for pattern in self.RE_GEO_URL:
                m = pattern.search(html)
                if m:
                    try: return float(m.group(1))
                    except: continue
        return None

    def get_longitude(self, ld: Dict[str, Any], html: Optional[str] = None) -> Optional[float]:
        v = self._safe_get(ld, "jobLocation", "geo", "longitude") or self._safe_get(ld, "jobLocation", 0, "geo", "longitude") or self._safe_get(ld, "geo", "longitude")
        if v:
            try: return float(v)
            except: pass
            
        if html:
            for pattern in self.RE_GEO_URL:
                m = pattern.search(html)
                if m:
                    try: return float(m.group(2))
                    except: continue
        return None

    def get_district(self, ld: Dict[str, Any], address_hint: Optional[str] = None) -> Optional[str]:
        return self._parse_taiwan_location(ld, address_hint)["district"]

    def get_region(self, ld: Dict[str, Any], address_hint: Optional[str] = None) -> Optional[str]:
        return self._parse_taiwan_location(ld, address_hint)["region"]

    def get_address_country(self, ld: Dict[str, Any]) -> Optional[str]:
        node = self._safe_get(ld, "jobLocation", "address")
        text: str = ""
        if isinstance(node, dict): text = f"{node.get('addressRegion', '')}{node.get('addressLocality', '')}{node.get('streetAddress', '')}"
        elif isinstance(node, str): text = node
        if text:
            m = {"越南": "VN", "印尼": "ID", "菲律賓": "PH", "泰國": "TH", "馬來西亞": "MY", "新加坡": "SG", "日本": "JP", "韓國": "KR", "中國": "CN", "美國": "US"}
            for kw, code in m.items():
                if kw in text: return code
        c = self._safe_get(ld, "jobLocation", "address", "addressCountry")
        if not c: return "TW"
        if isinstance(c, str) and c.upper() in ["TW", "TWN", "TAIWAN", "ROC", "台灣", "臺灣"]: return "TW"
        return str(c)

    @abstractmethod
    def get_source_id(self, ld: Dict[str, Any], url: Optional[str] = None) -> Optional[str]: pass
    @abstractmethod
    def get_url(self, ld: Dict[str, Any], fallback_url: Optional[str] = None) -> str: pass
    @abstractmethod
    def get_address(self, ld: Dict[str, Any], html: Optional[str] = None) -> Optional[str]: pass

    def get_company_name(self, ld: Dict[str, Any]) -> Optional[str]:
        return self._safe_get(ld, "hiringOrganization", "name") or self._safe_get(ld, "author", "name")
    def get_company_url(self, ld: Dict[str, Any]) -> Optional[str]:
        return self._safe_get(ld, "hiringOrganization", "url") or self._safe_get(ld, "hiringOrganization", "sameAs")
    def get_company_website(self, ld: Dict[str, Any]) -> Optional[str]:
        return self._safe_get(ld, "hiringOrganization", "url")
    def get_company_source_id(self, ld: Dict[str, Any]) -> Optional[str]: return None
    def get_company_address(self, ld: Dict[str, Any]) -> Optional[str]:
        addr = self._safe_get(ld, "hiringOrganization", "address")
        if isinstance(addr, dict): return f"{addr.get('addressRegion', '')}{addr.get('addressLocality', '')}{addr.get('streetAddress', '')}"
        return str(addr) if addr else None
    def get_capital(self, ld: Dict[str, Any]) -> Optional[str]: return None
    def get_employee_count(self, ld: Dict[str, Any]) -> Optional[str]: return None

    # ========== 靜態工具 ==========
    @staticmethod
    def _safe_get(data: Optional[Dict[str, Any]], *keys: str, default: Any = None) -> Any:
        if data is None: return default
        curr = data
        for k in keys:
            if isinstance(curr, dict): curr = curr.get(k)
            else: return default
            if curr is None: return default
        return curr

    @staticmethod
    def _map_job_type(et: Optional[str]) -> str:
        if not et: return "全職"
        if isinstance(et, list) and et: et = et[0]
        s = str(et).lower()
        if "full" in s: return "全職"
        if "part" in s: return "兼職"
        if "intern" in s: return "實習"
        if "contract" in s or "temp" in s: return "約聘"
        return str(et)

    @staticmethod
    def _map_education_text(text: Optional[str]) -> str:
        if not text: return "不拘"
        s = text.lower()
        m = {"elementary":"國小", "junior high":"國中", "high school":"高中", "vocational":"高職", "associate":"專科", "junior college":"專科", "bachelor":"大學", "university":"大學", "graduate":"碩士", "master":"碩士", "doctor":"博士", "ph.d":"博士"}
        for k, v in m.items():
            if k in s: return v
        return text

    @staticmethod
    def _standardize_numeric(text: Optional[str]) -> Optional[str]:
        if not text: return None
        s = html_lib.unescape(str(text)).replace(",", "").replace(" ", "").replace("元", "").replace("人", "").replace("員", "").replace("名", "")
        if JsonLdAdapter.RE_NUMERIC_ONLY.fullmatch(s): return s
        total = 0.0; has_u = False
        m_yi = JsonLdAdapter.RE_YI.search(s)
        if m_yi:
            try: total += float(m_yi.group(1)) * 100_000_000; has_u = True; parts = s.split("億", 1); s = parts[1] if len(parts) > 1 else ""
            except: pass
        m_wa = JsonLdAdapter.RE_WAN.search(s)
        if m_wa:
            try: total += float(m_wa.group(1)) * 10_000; has_u = True
            except: pass
        if has_u: return f"{total:f}".split('.')[0]
        # 處理範圍：若包含範圍符號，嘗試提取最大的數字以反映規模
        if any(c in s for c in ["~", "-", "〜", "至"]):
            matches = JsonLdAdapter.RE_NUMERIC_ONLY.findall(s)
            if matches:
                 try: return str(max(int(float(m)) for m in matches))
                 except: pass
        m_dig = JsonLdAdapter.RE_NUMERIC_ONLY.search(s)
        if m_dig: return m_dig.group(0)
        return str(text)

    def _filter_website(self, url: Any) -> Optional[str]:
        if not url: return None
        s = str(url).strip()
        if not s.lower().startswith("http"): return None
        ignore = ["104.com.tw", "1111.com.tw", "yes123.com.tw", "cake.me", "yourator.co", "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "youtube.com", "google.com"]
        if any(d in s.lower() for d in ignore): return None
        return s

    @staticmethod
    def _standardize_taiwan_address_format(text: Optional[str]) -> Optional[str]:
        if not text: return text
        s = str(text)
        if s.strip() in ["台灣", "臺灣", "Taiwan", "TW", "TWN", "中華民國"]: return ""
        
        # 1. 移除開頭國家標籤
        s = JsonLdAdapter.RE_TAIWAN_START.sub("", s)
        s = JsonLdAdapter.RE_TAIWAN_END.sub("", s)
        
        # 2. 移除地址前的雜訊 (找寻第一個縣/市/區)
        # 像是 "D.Lab 台北市..." -> "台北市..."
        match = JsonLdAdapter.RE_CITY_DISTRICT.search(s) or JsonLdAdapter.RE_CITY.search(s)
        if match:
             s = s[match.start():]
             
        # 3. 移除尾部括號備註 (如 "(Pinkoi / ...)")
        s = re.sub(r"\s*\(.*?\)$", "", s)

        # 4. 移除常見尾部雜訊 (按鈕文字、其他欄位標籤)
        trailing_noise = ["追蹤", "關於我們", "職務類別", "儲存", "應徵", "分享", "檢舉", "回報", "查看地圖", "看地圖", "薪資待遇", "上班時段", "休假制度", "工作性質"]
        for noise in trailing_noise:
            if noise in s:
                s = s.split(noise)[0].strip()

        if len(s) > 4: s = JsonLdAdapter.RE_TAIWAN_ANY.sub("", s)
        s = s.replace(",", "").replace("，", "").strip(); s = JsonLdAdapter.RE_ADDRESS_FIX.sub(r"\2\1", s)
        return s

    @staticmethod
    def _dedupe_address(parts: List[str]) -> str:
        if not parts: return ""
        all_tks = []
        for p in parts:
            if p: all_tks.extend(str(p).replace("\xa0", " ").split())
        res_tks = []; seen = set()
        for tk in all_tks:
            tk_c = tk.strip().replace(" ", "")
            if not tk_c or any(tk_c in ex for ex in seen): continue
            new_res = []; repl = False
            for ex_tk in res_tks:
                ex_c = ex_tk.replace(" ", "")
                if ex_c in tk_c:
                    if not repl: new_res.append(tk); repl = True
                    if ex_c in seen: seen.remove(ex_c)
                    seen.add(tk_c)
                else: new_res.append(ex_tk)
            if repl: res_tks = new_res
            else: res_tks.append(tk); seen.add(tk_c)
        res = ""
        for tk in res_tks:
            if not res: res = tk
            else: res += tk if bool(re.match(r'[\u4e00-\u9fff]', res[-1:])) and bool(re.match(r'[\u4e00-\u9fff]', tk[:1])) else f" {tk}"
        return res

    def _clean_id_noise(self, text: Optional[str]) -> Optional[str]:
        if not text: return text
        return self.RE_ID_NOISE.sub("", str(text)).strip()

    def _extract_city_from_text(self, text: str) -> Optional[str]:
        if not text: return None
        match = self.RE_CITY.search(text)
        return match.group(1) if match else None
