"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：standard_category_service.py
功能描述：負責處理平台類別與標準化類別之間的映射與匯入。
"""
import yaml
import structlog
from typing import Dict, List, Any
from core.infra import Database

logger = structlog.get_logger(__name__)

class StandardCategoryService:
    """處理標準類別映射匯入。"""
    
    def __init__(self, db: Database = None):
        self.db = db or Database()

    async def import_from_yaml(self, path: str) -> int:
        """
        從 YAML 檔案匯入映射數據。
        格式預期為: 
        platform_name:
          - id: "..."
            name: "..."
            major: "..."
            minor: "..."
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            
            if not data:
                return 0
                
            count = 0
            async with self.db.safe_cursor() as cursor:
                for platform, items in data.items():
                    for item in items:
                        sql = """
                        INSERT INTO tb_standard_categories 
                        (platform, platform_cat_id, platform_cat_name, major_category, minor_category)
                        VALUES (%s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE 
                        platform_cat_name=VALUES(platform_cat_name),
                        major_category=VALUES(major_category),
                        minor_category=VALUES(minor_category)
                        """
                        await cursor.execute(sql, (
                            platform, 
                            item["id"], 
                            item["name"], 
                            item.get("major", ""), 
                            item.get("minor", "")
                        ))
                        count += 1
            
            logger.info("category_import_success", path=path, count=count)
            return count
        except Exception as e:
            logger.error("category_import_failed", path=path, error=str(e))
            raise
