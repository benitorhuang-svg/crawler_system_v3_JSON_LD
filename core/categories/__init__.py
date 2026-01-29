"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：__init__.py (Categories)
功能描述：職缺類別 (Categories) 模組入口，導出各平台的職缺類別抓取函數與統整器。
主要入口：由 core.celery_app 或同步腳本調用。
"""
from .fetch_categories_104 import fetch_104_categories
from .fetch_categories_1111 import fetch_1111_categories
from .fetch_categories_cakeresume import fetch_cakeresume_categories
from .fetch_categories_yes123 import fetch_yes123_categories
from .fetch_categories_yourator import fetch_yourator_categories
from .fetch_categories_all import fetch_all_categories

__all__ = [
    "fetch_104_categories",
    "fetch_1111_categories",
    "fetch_cakeresume_categories",
    "fetch_yes123_categories",
    "fetch_yourator_categories",
    "fetch_all_categories",
]

