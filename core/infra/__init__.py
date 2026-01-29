"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：__init__.py (Infrastructure)
功能描述：基礎設施 (Infrastructure) 模組初始化，導出常用的基礎設施工具、模型與配置。
主要入口：由系統各處匯入 core.infra 使用。
"""
from .database import Database
from .schemas import (
    SourcePlatform, JobPydantic, CompanyPydantic, SalaryType, 
    CategoryPydantic, JobCategoryJunctionPydantic, 
    JobLocationPydantic, JobSkillExtractedPydantic
)
from .logging_config import configure_logging, logger
from .sql_generator import SQLGenerator
from .browser_fetcher import BrowserFetcher
from .redis_client import RedisClient
from .config import settings

__all__ = [
    "Database",
    "SourcePlatform",
    "JobPydantic",
    "CompanyPydantic",
    "SalaryType",
    "CategoryPydantic",
    "JobCategoryJunctionPydantic",
    "JobLocationPydantic",
    "JobSkillExtractedPydantic",
    "configure_logging",
    "logger",
    "SQLGenerator",
    "BrowserFetcher",
    "RedisClient",
    "settings",
]
