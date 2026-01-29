"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：__init__.py
功能描述：核心套件進入點，統一導出基礎設施、服務與適配器組件。
"""
from .infra import (
    Database, SourcePlatform, JobPydantic, CompanyPydantic, 
    SalaryType, configure_logging, logger, SQLGenerator,
    JobCategoryJunctionPydantic, JobLocationPydantic, JobSkillExtractedPydantic
)
from .services import DiscoveryService, CrawlService, JsonLdExtractor, Throttler
from .adapters import JsonLdAdapter, AdapterFactory

__all__ = [
    "Database",
    "SourcePlatform",
    "JobPydantic",
    "CompanyPydantic",
    "SalaryType",
    "SQLGenerator",
    "configure_logging",
    "logger",
    "DiscoveryService",
    "CrawlService",
    "JsonLdExtractor",
    "Throttler",
    "JsonLdAdapter",
    "AdapterFactory",
    "JobCategoryJunctionPydantic",
    "JobLocationPydantic",
    "JobSkillExtractedPydantic",
]

