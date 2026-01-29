"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：seed_test_categories.py
功能描述：測試分類資料填充工具，為資料庫注入各平台的預設測試分類種子。
主要入口：python test/scripts/seed_test_categories.py
"""
import asyncio
import structlog
from typing import List

from core.infra import Database, CategoryPydantic, SourcePlatform, SQLGenerator

# 初始化日誌
logger = structlog.get_logger(__name__)

async def seed_categories() -> None:
    """
    將預設的跨平台測試分類種子寫入 tb_categories 表中。
    """
    print("🚀 正在注入測試分類種子...")
    db = Database()
    
    categories: List[CategoryPydantic] = [
        # 104: 軟體設計工程師
        CategoryPydantic(
            platform=SourcePlatform.PLATFORM_104, 
            layer_1_id="2007000000", layer_1_name="資訊軟體", 
            layer_2_id="2007001000", layer_2_name="軟體/工程", 
            layer_3_id="2007001004", layer_3_name="軟體設計工程師"
        ),
        # 1111: 軟體工程師
        CategoryPydantic(
            platform=SourcePlatform.PLATFORM_1111, 
            layer_1_id="1", layer_1_name="資訊", 
            layer_2_id="2", layer_2_name="軟體", 
            layer_3_id="100501", layer_3_name="軟體工程師"
        ),
        # CakeResume: Backend
        CategoryPydantic(
            platform=SourcePlatform.PLATFORM_CAKERESUME, 
            layer_1_id="tech", layer_1_name="Tech", 
            layer_2_id="dev", layer_2_name="Dev", 
            layer_3_id="backend-engineer", layer_3_name="Backend"
        ),
        # Yes123: 軟體工程師
        CategoryPydantic(
            platform=SourcePlatform.PLATFORM_YES123, 
            layer_1_id="1", layer_1_name="1", 
            layer_2_id="2", layer_2_name="2", 
            layer_3_id="230100", layer_3_name="軟體工程師"
        ),
        # Yourator: Backend
        CategoryPydantic(
            platform=SourcePlatform.PLATFORM_YOURATOR, 
            layer_1_id="1", layer_1_name="1", 
            layer_2_id="2", layer_2_name="2", 
            layer_3_id="backend_engineer", layer_3_name="Backend"
        ),
    ]
    
    try:
        async with db.safe_cursor() as cursor:
            # 使用 SQLGenerator 生成 Upsert 語句
            sql: str = SQLGenerator.generate_upsert_sql(
                CategoryPydantic, 
                "tb_categories", 
                ["platform", "layer_3_id"]
            )
            params: List[List[Any]] = [SQLGenerator.to_sql_params(c) for c in categories]
            
            await cursor.executemany(sql, params)
            print(f"✅ 已成功同步 {len(categories)} 筆測試分類至 tb_categories。")
    except Exception as e:
        logger.error("seed_categories_failed", error=str(e))
    finally:
        await db.close_pool()

if __name__ == "__main__":
    try:
        asyncio.run(seed_categories())
    except KeyboardInterrupt:
        pass
