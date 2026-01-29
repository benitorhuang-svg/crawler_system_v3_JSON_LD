"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：fetch_categories_yes123.py
功能描述：Yes123 職缺類別抓取器，自官方 JSON 接口提取類別數據並同步至資料庫。
主要入口：由 core.categories.fetch_all_categories 或非同步任務調用。
"""
import asyncio
import json
import httpx
import structlog
from typing import List, Dict, Any, Optional

from core.infra import Database, SourcePlatform

# 初始化日誌
logger = structlog.get_logger(__name__)

async def fetch_yes123_categories() -> int:
    """
    抓取 Yes123 求職網之職缺分類。
    
    流程：
    1. 請求核心分類 JSON。
    2. 解析 listObj 結構並提取 L1 與 L2 (作為層級 3) 數據。
    3. 扁平化數據並執行資料庫 Upsert。
    
    Returns:
        int: 成功處理的類別總筆數。
    """
    logger.info("fetch_yes123_cat_start")
    url: str = "https://www.yes123.com.tw/json_file/work_mode.json"
    
    headers: Dict[str, str] = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.yes123.com.tw/"
    }

    raw_data: Optional[Dict[str, Any]] = None
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp: httpx.Response = await client.get(url, headers=headers)
            resp.raise_for_status()
            # 處理潛在的 UTF-8 BOM 並解碼
            content: str = resp.content.decode('utf-8-sig')
            raw_data = json.loads(content)
        except Exception as e:
            logger.error("fetch_yes123_cat_error", error=str(e))
            return 0

    if not isinstance(raw_data, dict) or "listObj" not in raw_data:
        logger.error("fetch_yes123_cat_invalid_format")
        return 0

    # 解析結構
    root_list: List[Dict[str, Any]] = raw_data.get("listObj", [])
    flattened: List[Dict[str, Any]] = []

    for item in root_list:
        l1_id: str = str(item.get("code", "")).lstrip("_")
        l1_name: str = str(item.get("level_1_name", ""))
        
        subs: List[Dict[str, Any]] = item.get("list_2", [])
        
        if not subs:
            # 第一層無子項目時，將自身映射至 L3
            flattened.append({
                "platform": SourcePlatform.PLATFORM_YES123.value,
                "layer_1_id": l1_id,
                "layer_1_name": l1_name,
                "layer_3_id": l1_id,
                "layer_3_name": l1_name
            })
        else:
            for s in subs:
                l3_id: str = str(s.get("code", "")).lstrip("_")
                l3_name: str = str(s.get("level_2_name", ""))
                
                flattened.append({
                    "platform": SourcePlatform.PLATFORM_YES123.value,
                    "layer_1_id": l1_id,
                    "layer_1_name": l1_name,
                    "layer_3_id": l3_id,
                    "layer_3_name": l3_name
                })

    if not flattened:
        return 0

    logger.debug("fetch_yes123_cat_parsed", count=len(flattened))
    
    # 存入資料庫
    db = Database()
    saved: int = 0
    for i in range(0, len(flattened), 200):
        chunk = flattened[i : i + 200]
        if await db.upsert_categories(chunk):
            saved += len(chunk)
        
    logger.info("fetch_yes123_cat_complete", saved=saved)
    return saved

if __name__ == "__main__":
    from core.infra import configure_logging
    configure_logging()
    async def run_standalone():
        db = Database()
        try:
            await fetch_yes123_categories()
        finally:
            await db.close_pool()
    asyncio.run(run_standalone())

