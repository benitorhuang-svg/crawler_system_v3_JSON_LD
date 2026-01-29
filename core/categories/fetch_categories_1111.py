"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：fetch_categories_1111.py
功能描述：1111 職缺類別抓取器，解析 1111 的 API 接口以提取階層化分類並同步至資料庫。
主要入口：由 core.categories.fetch_all_categories 或非同步任務調用。
"""
import asyncio
import httpx
import structlog
from typing import List, Dict, Any, Optional

from core.infra import Database, SourcePlatform

# 初始化日誌
logger = structlog.get_logger(__name__)

async def fetch_1111_categories() -> int:
    """
    抓取 1111 人力銀行之職缺分類。
    
    流程：
    1. 請求官方 codeCategories 接口。
    2. 使用層級映射表重建 L1 -> L2 -> L3 關聯。
    3. 扁平化數據並執行資料庫 Upsert。
    
    Returns:
        int: 成功處理的類別總筆數。
    """
    logger.info("fetch_1111_cat_start")
    url: str = "https://www.1111.com.tw/api/v1/codeCategories/"
    
    headers: Dict[str, str] = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }

    raw_data: Optional[Dict[str, Any]] = None
    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        try:
            resp: httpx.Response = await client.get(url, headers=headers)
            resp.raise_for_status()
            raw_data = resp.json()
        except Exception as e:
            logger.error("fetch_1111_cat_error", error=str(e))
            return 0

    if not isinstance(raw_data, dict) or "jobPosition" not in raw_data:
        logger.error("fetch_1111_cat_invalid_format")
        return 0

    # 解析類別數據
    job_pos: List[Dict[str, Any]] = raw_data.get("jobPosition", [])
    
    # 建立查找表
    l1_map: Dict[str, Dict[str, Any]] = {item["code"]: item for item in job_pos if item.get("level") == 1}
    l2_map: Dict[str, Dict[str, Any]] = {item["code"]: item for item in job_pos if item.get("level") == 2}
    
    flattened: List[Dict[str, Any]] = []
    
    # 解析第三層（葉子節點）
    for item in job_pos:
        if item.get("level") == 3:
            l3_id: str = str(item.get("code", ""))
            l3_name: str = str(item.get("name", "") or item.get("description", ""))
            
            l2_code: str = str(item.get("parentCode", ""))
            l2_item: Dict[str, Any] = l2_map.get(l2_code, {})
            l2_id: str = str(l2_item.get("code", ""))
            l2_name: str = str(l2_item.get("name", "") or l2_item.get("description", ""))
            
            l1_code: str = str(l2_item.get("parentCode", ""))
            l1_item: Dict[str, Any] = l1_map.get(l1_code, {})
            l1_id: str = str(l1_item.get("code", ""))
            l1_name: str = str(l1_item.get("name", "") or l1_item.get("description", ""))
            
            flattened.append({
                "platform": SourcePlatform.PLATFORM_1111.value,
                "layer_1_id": l1_id,
                "layer_1_name": l1_name,
                "layer_2_id": l2_id,
                "layer_2_name": l2_name,
                "layer_3_id": l3_id,
                "layer_3_name": l3_name
            })
    
    if not flattened:
        return 0

    logger.debug("fetch_1111_cat_parsed", count=len(flattened))
    
    # 存入資料庫
    db = Database()
    saved: int = 0
    for i in range(0, len(flattened), 200):
        chunk = flattened[i : i + 200]
        if await db.upsert_categories(chunk):
            saved += len(chunk)
        
    logger.info("fetch_1111_cat_complete", saved=saved)
    return saved

if __name__ == "__main__":
    from core.infra import configure_logging
    configure_logging()
    async def run_standalone():
        db = Database()
        try:
            await fetch_1111_categories()
        finally:
            await db.close_pool()
    asyncio.run(run_standalone())

