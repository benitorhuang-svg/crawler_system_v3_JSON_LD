"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：fetch_categories_104.py
功能描述：104 職缺類別抓取器，自官方 JSON 接口提取階層化分類並同步至資料庫。
主要入口：由 core.categories.fetch_all_categories 或非同步任務調用。
"""
import asyncio
import httpx
import structlog
from typing import List, Dict, Any, Optional

from core.infra import Database, SourcePlatform

# 初始化日誌
logger = structlog.get_logger(__name__)

async def fetch_104_categories() -> int:
    """
    抓取 104 人力銀行之職缺分類樹。
    
    流程：
    1. 請求核心分類 JSON。
    2. 深度遍歷 L1 -> L2 -> L3 結構。
    3. 扁平化數據並執行資料庫 Upsert。
    
    Returns:
        int: 成功處理的類別總筆數。
    """
    logger.info("fetch_104_cat_start")
    url: str = "https://static.104.com.tw/category-tool/json/JobCat.json"
    
    headers: Dict[str, str] = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }

    raw_data: Optional[List[Dict[str, Any]]] = None
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp: httpx.Response = await client.get(url, headers=headers)
            resp.raise_for_status()
            raw_data = resp.json()
        except Exception as e:
            logger.error("fetch_104_cat_error", error=str(e))
            return 0

    if not isinstance(raw_data, list):
        logger.error("fetch_104_cat_invalid_format")
        return 0

    # 解析階層
    flattened: List[Dict[str, Any]] = []
    for l1 in raw_data:
        l1_id: str = str(l1.get("no", ""))
        l1_name: str = l1.get("des", "")
        
        for l2 in l1.get("n", []):
            l2_id: str = str(l2.get("no", ""))
            l2_name: str = l2.get("des", "")
            
            for l3 in l2.get("n", []):
                l3_id: str = str(l3.get("no", ""))
                l3_name: str = l3.get("des", "")
                
                flattened.append({
                    "platform": SourcePlatform.PLATFORM_104.value,
                    "layer_1_id": l1_id,
                    "layer_1_name": l1_name,
                    "layer_2_id": l2_id,
                    "layer_2_name": l2_name,
                    "layer_3_id": l3_id,
                    "layer_3_name": l3_name
                })
    
    if not flattened:
        return 0

    logger.debug("fetch_104_cat_parsed", count=len(flattened))
    
    # 批次寫入資料庫
    db = Database()
    saved: int = 0
    # 每 200 筆一組進行批次存儲
    for i in range(0, len(flattened), 200):
        chunk: List[Dict[str, Any]] = flattened[i : i + 200]
        if await db.upsert_categories(chunk):
            saved += len(chunk)
        
    logger.info("fetch_104_cat_complete", saved=saved)
    return saved

if __name__ == "__main__":
    from core.infra import configure_logging
    configure_logging()
    async def run_standalone():
        db = Database()
        try:
            await fetch_104_categories()
        finally:
            await db.close_pool()
    asyncio.run(run_standalone())

