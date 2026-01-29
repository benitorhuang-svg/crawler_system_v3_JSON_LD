"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：jsonld_extractor.py
功能描述：JSON-LD 提取工具，負責從網頁源碼中解析結構化數據。
主要入口：由 core.services.crawl_service 調用。
"""
import json
import re
import structlog
from typing import Any, List, Optional, Dict, Union
from bs4 import BeautifulSoup, Tag

# 設置結構化日誌
logger = structlog.get_logger(__name__)

class JsonLdExtractor:
    """
    JSON-LD 數據提取組件。
    支援從 HTML 腳本標籤中還原結構化物件，並處理 @graph 展平。
    """

    @classmethod
    def extract(cls, html: str) -> List[Dict[str, Any]]:
        """
        從 HTML 中提取所有 application/ld+json 內容。
        """
        if not html: return []

        results: List[Dict[str, Any]] = []
        soup: BeautifulSoup = BeautifulSoup(html, "html.parser")
        
        # 額外提取 __NEXT_DATA__ (針對 Next.js 平台如 CakeResume)
        next_data: Optional[Dict[str, Any]] = None
        next_tag: Optional[Tag] = soup.find("script", id="__NEXT_DATA__")
        if next_tag and next_tag.string:
            try:
                next_data = json.loads(next_tag.string)
            except Exception:
                pass

        tags: List[Tag] = soup.find_all("script", {"type": "application/ld+json"})

        for tag in tags:
            if not tag.string: continue
            try:
                raw: str = tag.string.strip()
                # 移除 CDATA 或多餘註解
                raw = re.sub(r"^\s*<!\[CDATA\[|\]\]>\s*$", "", raw, flags=re.IGNORECASE)
                
                data: Union[Dict[str, Any], List[Any]] = json.loads(raw)
                
                # 自動展開嵌套清單或 @graph
                extracted: List[Dict[str, Any]] = []
                if isinstance(data, list):
                    extracted.extend([it for it in data if isinstance(it, dict)])
                elif isinstance(data, dict):
                    if "@graph" in data and isinstance(data["@graph"], list):
                        extracted.extend([it for it in data["@graph"] if isinstance(it, dict)])
                    else:
                        extracted.append(data)
                
                # 注入 next_data 到所有物件
                if next_data:
                    for obj in extracted:
                        obj["_next_data"] = next_data
                
                results.extend(extracted)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning("jsonld_extraction_skipped", error=str(e))
                continue

        # 若無 LD 但有 next_data，回傳一個帶有 next_data 的虛擬物件
        if not results and next_data:
            results.append({"@type": "NextDataNode", "_next_data": next_data})

        return results

    @classmethod
    def _walk_objects(cls, data: Any) -> List[Dict[str, Any]]:
        """內部方法：遍歷所有層級的字典物件。"""
        found: List[Dict[str, Any]] = []
        if isinstance(data, dict):
            found.append(data)
            for v in data.values():
                found.extend(cls._walk_objects(v))
        elif isinstance(data, list):
            for i in data:
                found.extend(cls._walk_objects(i))
        return found

    @classmethod
    def find_by_type(cls, ld_list: List[Dict[str, Any]], target: str) -> Optional[Dict[str, Any]]:
        """在提取出的生活中搜尋特定標識 (@type) 的物件。"""
        all_objs = cls._walk_objects(ld_list)
        for obj in all_objs:
            t = obj.get("@type")
            if (isinstance(t, str) and t == target) or (isinstance(t, list) and target in t):
                return obj
        return None

    @classmethod
    def find_job_posting(cls, ld_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """快速定位 JobPosting 物件。"""
        return cls.find_by_type(ld_list, "JobPosting")

    @classmethod
    def find_organization(cls, ld_list: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """快速定位 Organization 物件。"""
        return cls.find_by_type(ld_list, "Organization")

    @staticmethod
    def safe_get(data: Optional[Dict[str, Any]], *keys: str, default: Any = None) -> Any:
        """深度安全取得字典鍵值。"""
        if not data: return default
        curr: Any = data
        for k in keys:
            if isinstance(curr, dict):
                curr = curr.get(k)
                if curr is None: return default
            else:
                return default
        return curr
