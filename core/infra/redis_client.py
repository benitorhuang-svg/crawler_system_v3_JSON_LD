"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：redis_client.py
功能描述：Redis 客戶端連線管理器，提供全域唯一的 Redis 連線實例，用於流量限制與快取。
主要入口：由 core.services.throttler 或快取邏輯調用。
"""
import redis
import structlog
from typing import Optional, Any
from core.infra.config import settings

# 設置結構化日誌
logger = structlog.get_logger(__name__)

class RedisClient:
    """
    集中化的 Redis 連線管理器 (Singleton)。
    """
    _instance: Optional['RedisClient'] = None
    client: Optional[redis.Redis] = None

    def __new__(cls) -> 'RedisClient':
        """確保全域僅有一個 RedisClient 實例。"""
        if cls._instance is None:
            cls._instance = super(RedisClient, cls).__new__(cls)
            cls._instance._init_client()
        return cls._instance

    def _init_client(self) -> None:
        """從中央配置初始化 Redis 連線並測試。"""
        redis_url: str = settings.REDIS_URL
        try:
            self.client = redis.from_url(redis_url, decode_responses=True)
            self.client.ping()
            logger.info("redis_connected", url=redis_url)
        except Exception as e:
            logger.error("redis_connection_failed", url=redis_url, error=str(e))
            self.client = None

    def get_client(self) -> Optional[redis.Redis]:
        """獲取 Redis 用戶端操作實例。"""
        return self.client

