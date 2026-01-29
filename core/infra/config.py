"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：config.py
功能描述：全域配置管理中心，基於 Pydantic Settings 實現環境變數與預設值的統一管理。
"""
import os
from pathlib import Path
from typing import Optional, List, Dict
from pydantic_settings import BaseSettings, SettingsConfigDict

# 定義專案根目錄
ROOT_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    """系統全域配置設定。"""
    
    # 測試與開發
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False
    
    # 資料庫配置 (MySQL)
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "root"
    DB_NAME: str = "crawler_db"
    
    # Redis 配置 (用於限流與 Taskiq)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    
    # Ollama 配置
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "gemma3:4b"
    
    # 爬蟲行為配置
    BROWSER_HEADLESS: bool = True
    BROWSER_TIMEOUT: int = 30000
    BROWSER_WS_ENDPOINT: Optional[str] = None
    MAX_CONCURRENT_TASKS: int = 5
    EXPORT_PATH: str = "exports/categories"
    
    # 統一超時設定 (單位: 秒)
    TIMEOUT_BROWSER: int = 30
    TIMEOUT_HTTP_SHORT: int = 15
    TIMEOUT_HTTP_LONG: int = 45
    TIMEOUT_OLLAMA: int = 60
    TIMEOUT_DB_TRANSACTION: int = 10
    
    # 分頁限制
    PAGINATION_LIMIT_DEFAULT: int = 10
    PAGINATION_LIMIT_MAX: int = 50
    
    # 冷卻與重試
    RETRY_COUNT: int = 3
    RETRY_BACKOFF_FACTOR: float = 2.0
    COOLDOWN_CATEGORY: int = 3600  # 1 小時
    
    # 平台限流配置 (速率, 突發容量)
    THROTTLE_CONFIG: Dict[str, tuple[float, float]] = {
        "platform_104": (5.0, 20.0),
        "platform_1111": (5.0, 20.0),
        "platform_yes123": (3.0, 15.0),
        "platform_cakeresume": (5.0, 20.0),
        "platform_yourator": (5.0, 20.0),
        "default": (2.0, 10.0)
    }

    # 代理配置
    PROXIES: List[str] = []
    
    # Pydantic Settings 配置
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

# 實例化全域配置物件
settings = Settings()
