"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：fetch_categories_yourator.py
功能描述：Yourator 職缺類別抓取器，自官方 API 接口提取類別數據並同步至資料庫。
主要入口：由 core.categories.fetch_all_categories 或非同步任務調用。
"""
import asyncio
import httpx
import structlog
from typing import List, Dict, Any, Optional

from core.infra import Database, SourcePlatform

# 初始化日誌
logger = structlog.get_logger(__name__)

async def fetch_yourator_categories() -> int:
    """
    抓取 Yourator 之職缺分類。
    
    流程：
    1. 請求官方 job_categories API。
    2. 解析 categoryGroups 結構並提取 L1 與 L3 數據。
    3. 扁平化數據並執行資料庫 Upsert。
    
    Returns:
        int: 成功處理的類別總筆數。
    """
    logger.info("fetch_yourator_cat_start")
    url: str = "https://www.yourator.co/api/v4/job_categories"
    
    headers: Dict[str, str] = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }

    raw_data: Optional[Dict[str, Any]] = None
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp: httpx.Response = await client.get(url, headers=headers)
            resp.raise_for_status()
            raw_data = resp.json()
        except Exception as e:
            logger.error("fetch_yourator_cat_error", error=str(e))
            return 0

    if not isinstance(raw_data, dict) or "payload" not in raw_data:
        logger.error("fetch_yourator_cat_invalid_format")
        return 0

    # 提取職缺類別
    payload: Dict[str, Any] = raw_data.get("payload", {})
    groups: List[Dict[str, Any]] = payload.get("categoryGroups", [])
    flattened: List[Dict[str, Any]] = []
    
    for g in groups:
        l1_id: str = str(g.get("id", ""))
        l1_name: str = str(g.get("name", ""))
        
        subs: List[Dict[str, Any]] = g.get("jobCategories", [])
        if not subs:
            # 第一層無子項目時，將自身映射至 L3
            flattened.append({
                "platform": SourcePlatform.PLATFORM_YOURATOR.value,
                "layer_1_id": l1_id,
                "layer_1_name": l1_name,
                "layer_3_id": l1_id,
                "layer_3_name": l1_name
            })
        else:
            for s in subs:
                l3_id: str = str(s.get("id", ""))
                l3_name: str = str(s.get("name", ""))
                
                flattened.append({
                    "platform": SourcePlatform.PLATFORM_YOURATOR.value,
                    "layer_1_id": l1_id,
                    "layer_1_name": l1_name,
                    "layer_3_id": l3_id,
                    "layer_3_name": l3_name
                })

    if not flattened:
        return 0

    logger.debug("fetch_yourator_cat_parsed", count=len(flattened))
    
    # 存入資料庫
    db = Database()
    saved: int = 0
    for i in range(0, len(flattened), 200):
        chunk = flattened[i : i + 200]
        if await db.upsert_categories(chunk):
            saved += len(chunk)
        
    logger.info("fetch_yourator_cat_complete", saved=saved)
    return saved

if __name__ == "__main__":
    from core.infra import configure_logging
    configure_logging()
    async def run_standalone():
        db = Database()
        try:
            await fetch_yourator_categories()
        finally:
            await db.close_pool()
    asyncio.run(run_standalone())

