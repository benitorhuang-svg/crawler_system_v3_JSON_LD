"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：__init__.py (Adapters)
功能描述：平台適配器入口，導出工廠類與 JSON-LD 適配器。
"""
from .adapter_factory import AdapterFactory
from .jsonld_adapter import JsonLdAdapter

__all__ = ["AdapterFactory", "JsonLdAdapter"]
