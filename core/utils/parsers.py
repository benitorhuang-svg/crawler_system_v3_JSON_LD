"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：parsers.py
功能描述：專用解析器工具模組，包含日期、薪資、年資等複雜邏輯的解析工具。
主要入口：由各平台 Adapter 調用。
"""
import re
import enum
from datetime import date, datetime
from typing import Any, Dict, Optional, Union, List
import structlog

logger = structlog.get_logger(__name__)

from core.infra.schemas import SalaryType

class SalaryParser:
    """薪資字串解析器，負責將非結構化的薪資文本轉換為結構化數值範圍。"""
    
    RE_YI = re.compile(r'([\d\.]+)(?=億)')
    RE_WAN = re.compile(r'([\d\.]+)(?=萬)')
    RE_DIGITS = re.compile(r'\d+')
    
    @classmethod
    def parse(cls, base_salary: Any) -> Dict[str, Any]:
        """
        定義通用的薪資解析流程 (SDD Sec 18)。
        
        Args:
            base_salary (Any): JSON-LD 中的 baseSalary 對象或原始文本。
            
        Returns:
            Dict[str, Any]: 包含 min, max, type (SalaryType), text 的結構化資料。
        """
        result: Dict[str, Any] = {"min": None, "max": None, "type": SalaryType.NEGOTIABLE, "text": "面議"}
        if not base_salary:
            return result

        if isinstance(base_salary, list) and base_salary:
            base_salary = base_salary[0]

        min_v: Optional[Union[str, int, float]] = None
        max_v: Optional[Union[str, int, float]] = None
        s_type: SalaryType = SalaryType.MONTHLY
        base_text: Optional[str] = None
        
        # 1. 處理字典格式 (常用於 JSON-LD)
        if isinstance(base_salary, dict):
            value: Dict[str, Any] = base_salary.get("value", {}) if isinstance(base_salary.get("value"), dict) else base_salary
            min_v = value.get("minValue") or value.get("value")
            max_v = value.get("maxValue")
            unit_text = value.get("unitText") or "MONTH"
            s_type = cls._normalize_type(unit_text, str(base_salary))
            base_text = str(min_v) if not base_text and min_v else None

        # 2. 處理字串格式或提取失敗的邏輯
        raw_text: str = str(base_salary) if not isinstance(base_salary, dict) else (base_text or "")
        if (min_v is None or not str(min_v).replace(".", "").isdigit()) and raw_text:
            cleaned: str = raw_text.replace(",", "").replace(" ", "")
            
            # 處理「億/萬」單位
            yi_match = cls.RE_YI.search(cleaned)
            wan_match = cls.RE_WAN.search(cleaned)
            
            if yi_match:
                min_v = int(float(yi_match.group(1)) * 100_000_000)
            elif wan_match:
                min_v = int(float(wan_match.group(1)) * 10_000)
            else:
                digits: List[str] = cls.RE_DIGITS.findall(cleaned)
                if digits:
                    min_v = digits[0]
                    if len(digits) > 1:
                        max_v = digits[1]
            
            if not base_text: base_text = raw_text

        # 3. 數值規範化
        final_min: Optional[int] = cls._to_int(min_v)
        final_max: Optional[int] = cls._to_int(max_v)
        
        result["min"] = final_min
        result["max"] = final_max
        result["type"] = s_type
        result["text"] = cls._format_text(final_min, final_max, base_text)
        
        return result

    @staticmethod
    def _to_int(val: Any) -> Optional[int]:
        """安全數值轉換。"""
        if val is None: return None
        try:
            num = int(float(str(val)))
            return num if num > 0 else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _normalize_type(unit: str, text: str) -> SalaryType:
        """標準化計薪單位至 SalaryType 枚舉。"""
        u = str(unit).upper()
        if "YEAR" in u or "年" in text: return SalaryType.YEARLY
        if "HOUR" in u or "時" in text: return SalaryType.HOURLY
        if "DAY" in u or "日" in text: return SalaryType.DAILY
        if "MONTH" in u or "月" in text: return SalaryType.MONTHLY
        return SalaryType.NEGOTIABLE

    @staticmethod
    def _format_text(min_v: Optional[int], max_v: Optional[int], base_text: Optional[str]) -> str:
        """格式化薪資顯示文本。"""
        if min_v and max_v:
            return f"{min_v}-{max_v}"
        if min_v:
            if base_text and ("以上" in base_text or "起" in base_text):
                return base_text.strip()
            return f"{min_v}元以上"
        return base_text.strip() if base_text else "面議"

class DateParser:
    """日期解析器，負責正規化跨平台的日期字元。"""
    
    @staticmethod
    def parse_iso_date(date_str: Any) -> Optional[str]:
        """解析日期字串並回傳 YYYY-MM-DD 格式。"""
        if not date_str or not isinstance(date_str, str):
            return None
        
        # 處理 T 或空格分隔
        clean_str: str = date_str.split("T")[0].split(" ")[0]
        match = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", clean_str)
        if match:
            y, m, d = match.groups()
            return f"{y}-{int(m):02d}-{int(d):02d}"
            
        return None

    @staticmethod
    def parse(date_raw: Any) -> Optional[date]:
        """轉換為 Python date 物件。"""
        iso_str: Optional[str] = DateParser.parse_iso_date(date_raw)
        if not iso_str: return None
        try:
            return datetime.strptime(iso_str, "%Y-%m-%d").date()
        except Exception:
            return None

class ExperienceParser:
    """工作經驗解析器，處理年資相關文本。"""
    
    @staticmethod
    def parse(exp_val: Any) -> int:
        """
        解析最低年資需求（年）。
        
        Args:
            exp_val (Any): 年資字串。
            
        Returns:
            int: 標準化年資。
        """
        if not exp_val: return 0
        s: str = str(exp_val).lower()
        if "不拘" in s: return 0
        
        match = re.search(r"(\d+)", s)
        if not match: return 0
        
        val: int = int(match.group(1))
        # 處理 12 個月以上轉換為 1 年
        if any(kw in s for kw in ["月", "month", "個月"]) and val >= 12:
            return val // 12
        # 若數字很大且無「年」字眼，視為月份
        if val >= 12 and not any(kw in s for kw in ["年", "year"]):
            return val // 12
        
def parse_salary_text(salary_val: Any) -> Dict[str, Any]:
    """
    薪資解析之簡易包裝函式。
    
    Args:
        salary_val (Any): 原始薪資數據（字典或字串）。
        
    Returns:
        Dict[str, Any]: 結構化薪資對象。
    """
    return SalaryParser.parse(salary_val)
