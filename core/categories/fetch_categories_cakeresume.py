"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：fetch_categories_cakeresume.py
功能描述：CakeResume 職缺類別抓取器，透過解析頁面 __NEXT_DATA__ 提取階層化分類並同步至資料庫。
主要入口：由 core.categories.fetch_all_categories 或非同步任務調用。
"""
import asyncio
import json
import httpx
import structlog
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional

from core.infra import Database, SourcePlatform

# 初始化日誌
logger = structlog.get_logger(__name__)

async def fetch_cakeresume_categories() -> int:
    """
    抓取 CakeResume 之職缺分類。
    
    流程：
    1. 請求職缺首頁獲取 HTML。
    2. 解析 __NEXT_DATA__ 腳本中的 i18n JSON 數據。
    3. 提取 profession 相關的群組與項目並扁平化。
    4. 執行資料庫 Upsert。
    
    Returns:
        int: 成功處理的類別總筆數。
    """
    logger.info("fetch_cake_cat_start")
    url: str = "https://www.cake.me/jobs"
    
    headers: Dict[str, str] = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    }

    html_content: str = ""
    async with httpx.AsyncClient(follow_redirects=True, verify=False, http2=True, timeout=30.0) as client:
        try:
            resp: httpx.Response = await client.get(url, headers=headers)
            resp.raise_for_status()
            html_content = resp.text
        except Exception as e:
            logger.error("fetch_cake_cat_error", error=str(e))
            return 0

    # 提取頁面數據
    soup = BeautifulSoup(html_content, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    
    if not script or not script.string:
        logger.error("fetch_cake_cat_data_not_found")
        return 0

    try:
        data: Dict[str, Any] = json.loads(script.string)
        page_props: Dict[str, Any] = data.get("props", {}).get("pageProps", {})
        
        # 提取 i18n 資源包
        i18n_store: Dict[str, Any] = page_props.get("_nextI18Next", {}).get("initialI18nStore", {})
        zh_tw: Dict[str, Any] = i18n_store.get("zh-TW", {}) or i18n_store.get("zh-HK", {}) or next(iter(i18n_store.values()), {})
        
        profession_data: Dict[str, Any] = zh_tw.get("profession", {})
        groups: Dict[str, str] = profession_data.get("profession_groups", {}) 
        items: Dict[str, str] = profession_data.get("professions", {}) 

        flattened: List[Dict[str, Any]] = []
        for item_id, item_name in items.items():
            # ID 格式通常為 group_item，例如 it_software-engineer
            parts: List[str] = item_id.split("_")
            l1_id: str = parts[0]
            l1_name: str = groups.get(l1_id, "其他")
            
            flattened.append({
                "platform": SourcePlatform.PLATFORM_CAKERESUME.value,
                "layer_1_id": l1_id,
                "layer_1_name": l1_name,
                "layer_3_id": item_id, 
                "layer_3_name": item_name
            })
            
        if not flattened:
            return 0

        logger.debug("fetch_cake_cat_parsed", count=len(flattened))

        # 持久化
        db = Database()
        saved: int = 0
        for i in range(0, len(flattened), 200):
            chunk: List[Dict[str, Any]] = flattened[i : i + 200]
            if await db.upsert_categories(chunk):
                saved += len(chunk)
            
        logger.info("fetch_cake_cat_complete", saved=saved)
        return saved

    except Exception as e:
        logger.error("fetch_cake_cat_parse_failed", error=str(e))
        return 0

if __name__ == "__main__":
    from core.infra import configure_logging
    configure_logging()
    async def run_standalone():
        db = Database()
        try:
            await fetch_cakeresume_categories()
        finally:
            await db.close_pool()
    asyncio.run(run_standalone())

