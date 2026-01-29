"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：logging_config.py
功能描述：結構化日誌配置模組，配置系統的全域日誌行為，支援 JSON 格式化與開發環境的彩色輸出。
主要入口：由系統啟動入口 (entrypoint) 或各模組首端調用。
"""
import sys
import structlog
import logging
from typing import Any, List

def configure_logging() -> None:
    """
    為爬蟲系統配置嚴謹的結構化日誌。
    
    輸出策略：
    - 終端機模擬器 (TTY)：使用 ConsoleRenderer 提供彩色易讀格式。
    - 生產環境/非 TTY：使用 JSONRenderer 以利日誌收集系統 (如 ELK) 解析。
    """
    
    # 定義處理器 (Processors)
    processors: List[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    
    # 若在終端機執行則使用 ConsoleRenderer，否則使用 JSONRenderer 保持產線一致性
    if sys.stderr.isatty():
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False
    )
    
# 初始化配置
configure_logging()
logger = structlog.get_logger()
base_logger = logger # 提供別名以利不同場景調用

