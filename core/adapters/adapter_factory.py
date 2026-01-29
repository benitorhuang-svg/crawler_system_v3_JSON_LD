"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：adapter_factory.py
功能描述：JSON-LD 適配器工廠，根據平台枚舉回傳對應的適配器實例。
主要入口：由 core.services.crawl_service 調用。
"""
from typing import Optional, Dict, Type

from .jsonld_adapter import JsonLdAdapter
from .adapter_1111 import Adapter1111
from .adapter_yes123 import AdapterYes123
from .adapter_cakeresume import AdapterCakeResume
from .adapter_yourator import AdapterYourator
from .adapter_104 import Adapter104
from core.infra import SourcePlatform

class AdapterFactory:
    """
    適配器工廠類別。
    實作簡單工廠模式，集中管理各招聘平台的適配器實例化邏輯。
    """

    # 靜態映射字典，便於擴充新平台
    _ADAPTER_MAP: Dict[SourcePlatform, Type[JsonLdAdapter]] = {
        SourcePlatform.PLATFORM_1111: Adapter1111,
        SourcePlatform.PLATFORM_YES123: AdapterYes123,
        SourcePlatform.PLATFORM_CAKERESUME: AdapterCakeResume,
        SourcePlatform.PLATFORM_YOURATOR: AdapterYourator,
        SourcePlatform.PLATFORM_104: Adapter104,
    }

    @staticmethod
    def get_adapter(platform: SourcePlatform) -> Optional[JsonLdAdapter]:
        """
        根據平台識別枚舉獲取對應的適配器。
        
        Args:
            platform (SourcePlatform): 目標平台的識別枚舉。
            
        Returns:
            Optional[JsonLdAdapter]: 初始化後的適配器實例，若平台尚未支援則回傳 None。
        """
        adapter_cls: Optional[Type[JsonLdAdapter]] = AdapterFactory._ADAPTER_MAP.get(platform)
        if adapter_cls:
            return adapter_cls()
        
        # 目前未知或通用平台暫不提供預設適配器
        return None
