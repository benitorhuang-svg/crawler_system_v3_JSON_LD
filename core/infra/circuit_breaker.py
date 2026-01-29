"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：circuit_breaker.py
功能描述：斷路器模式實作，用於隔離不穩定的外部服務（如 AI 模型、瀏覽器實例）。
"""
import time
import structlog
import asyncio
from enum import Enum
from typing import Optional, Any, Callable, Dict

logger = structlog.get_logger(__name__)

class CircuitState(Enum):
    CLOSED = "CLOSED"      # 正常運行
    OPEN = "OPEN"          # 斷路中 (隔離)
    HALF_OPEN = "HALF_OPEN" # 嘗試恢復

class CircuitBreaker:
    """
    斷路器封裝器。
    基於失敗率與冷卻時間判定服務健康狀態。
    """
    def __init__(
        self, 
        name: str, 
        failure_threshold: int = 5, 
        recovery_timeout: int = 60,
        expected_exception: Exception = Exception
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: float = 0
        self._lock = asyncio.Lock()

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """執行受保護的調用。"""
        async with self._lock:
            await self._before_call()

        if self.state == CircuitState.OPEN:
            logger.warning("circuit_open", name=self.name, remaining=(self.last_failure_time + self.recovery_timeout - time.time()))
            raise RuntimeError(f"Circuit Breaker [{self.name}] is OPEN")

        try:
            result = await func(*args, **kwargs)
            async with self._lock:
                self._on_success()
            return result
        except self.expected_exception as e:
            async with self._lock:
                self._on_failure(e)
            raise e

    async def _before_call(self):
        """調用前的狀態檢查。"""
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                logger.info("circuit_half_opening", name=self.name)
                self.state = CircuitState.HALF_OPEN

    def _on_success(self):
        """成功調用後的狀態更新。"""
        if self.state == CircuitState.HALF_OPEN:
            logger.info("circuit_closing", name=self.name)
            self.state = CircuitState.CLOSED
        self.failure_count = 0

    def _on_failure(self, error: Exception):
        """失敗調用後的狀態更新。"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        logger.warning("circuit_call_failed", name=self.name, count=self.failure_count, error=str(error))

        if self.state == CircuitState.HALF_OPEN or self.failure_count >= self.failure_threshold:
            logger.error("circuit_opening", name=self.name, error=str(error))
            self.state = CircuitState.OPEN

class CircuitManager:
    """管理多個斷路器實例的全域容器。"""
    _instances: Dict[str, CircuitBreaker] = {}

    @classmethod
    def get_breaker(cls, name: str, **kwargs) -> CircuitBreaker:
        if name not in cls._instances:
            cls._instances[name] = CircuitBreaker(name, **kwargs)
        return cls._instances[name]
