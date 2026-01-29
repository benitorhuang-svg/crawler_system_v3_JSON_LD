"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：throttler.py
功能描述：流量限制器服務，提供基於 Redis 的分佈式流量控制、自適應頻率調整與冷卻 (Cooling) 機制，確保爬蟲行為符合 anti-blocking 策略。
主要入口：由 core.services.crawl_service 或非同步工作調用。
"""
import asyncio
import time
import hashlib
import random
from typing import Optional, Any, List, Union, Dict
import structlog
from core.infra.redis_client import RedisClient
from core.infra import SourcePlatform

logger = structlog.get_logger(__name__)

# 用於原子性令牌桶 (Token Bucket) 的 Lua 腳本
# KEYS[1] : throttle_key (例如 throttle:platform_104)
# ARGV[1] : rate (每秒產生的令牌數)
# ARGV[2] : capacity (最大容量/突發大小)
# ARGV[3] : now (當前時間戳)
TOKEN_BUCKET_LUA: str = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = 1

local state = redis.call('HMGET', key, 'last_time', 'tokens')
local last_time = tonumber(state[1]) or now
local tokens = tonumber(state[2]) or capacity

-- 根據經過的時間補充令牌
local delta = math.max(0, now - last_time)
tokens = math.min(capacity, tokens + delta * rate)

if tokens >= requested then
    tokens = tokens - requested
    redis.call('HMSET', key, 'last_time', now, 'tokens', tokens)
    return 1
else
    -- 回傳獲取 1 個令牌所需等待的時間 (負值代表需等待)
    local wait_time = (requested - tokens) / rate
    return -wait_time
end
"""

class Throttler:
    """
    分佈式流量限制器。
    
    支援基於 Redis 的令牌桶算法、自適應頻率調整與冷卻機制。
    用於在多實例環境下協調抓取頻率，防止觸發平台封鎖。
    """
    
    def __init__(self) -> None:
        """初始化 Throttler 並向 Redis 註冊 Lua 腳本。"""
        self.redis: Optional[Any] = RedisClient().get_client()
        self.lua_script: Optional[Any] = None
        if self.redis:
            try:
                self.lua_script = self.redis.register_script(TOKEN_BUCKET_LUA)
            except Exception as e:
                logger.error("throttle_lua_register_failed", error=str(e))

    @staticmethod
    def _get_proxy_hash(proxy_url: Optional[str]) -> str:
        """取得代理伺服器的識別雜湊，用於細粒度限制。"""
        if not proxy_url:
            return ""
        return hashlib.md5(proxy_url.encode()).hexdigest()[:8]

    async def trigger_cooling(self, platform: SourcePlatform, duration: int = 300, proxy_url: Optional[str] = None) -> None:
        """
        觸發特定平台（或代理）的冷卻狀態。
        
        Args:
            platform (SourcePlatform): 來源平台。
            duration (int): 冷卻秒數。
            proxy_url (Optional[str]): 若指定則僅冷卻該代理。
        """
        if not self.redis: return
            
        p_hash: str = self._get_proxy_hash(proxy_url)
        suffix: str = f":proxy:{p_hash}" if p_hash else ""
        key: str = f"cooling:{platform.value}{suffix}"
        
        try:
            self.redis.setex(key, duration, "1")
            logger.warning("throttle_cooling_triggered", 
                           platform=platform.value, 
                           proxy_hash=p_hash,
                           duration=duration)
        except Exception as e:
            logger.error("throttle_set_cooling_failed", error=str(e))

    async def is_cooling(self, platform: SourcePlatform, proxy_url: Optional[str] = None) -> bool:
        """檢查目前是否處於冷卻禁制期。"""
        if not self.redis: return False
        
        try:
            # 1. 檢查全局冷卻
            if self.redis.exists(f"cooling:{platform.value}"):
                return True
            # 2. 檢查代理冷卻
            if proxy_url:
                p_hash = self._get_proxy_hash(proxy_url)
                if self.redis.exists(f"cooling:{platform.value}:proxy:{p_hash}"):
                    return True
        except Exception as e:
            logger.error("throttle_check_cooling_failed", error=str(e))
        return False

    async def get_adaptive_rate(self, platform: SourcePlatform, default_rate: float) -> float:
        """取得當前適配的爬取頻率。"""
        if not self.redis: return default_rate
            
        try:
            val = self.redis.get(f"throttle:adaptive_rate:{platform.value}")
            return float(val) if val else default_rate
        except (ValueError, TypeError, Exception):
            return default_rate

    async def report_success(self, platform: SourcePlatform, default_rate: float) -> None:
        """報告請求成功，推進自適應提速機制。"""
        if not self.redis: return
            
        name: str = platform.value
        try:
            streak: int = self.redis.incr(f"throttle:success_streak:{name}")
            if streak >= 50:
                self.redis.set(f"throttle:success_streak:{name}", 0)
                current: float = await self.get_adaptive_rate(platform, default_rate)
                # 提速 10%，上限為預設 1.5 倍
                new_rate: float = min(current * 1.1, default_rate * 1.5)
                self.redis.set(f"throttle:adaptive_rate:{name}", new_rate)
                logger.info("throttle_adaptive_boost", platform=name, old=current, new=new_rate)
        except Exception as e:
            logger.error("throttle_report_success_failed", error=str(e))

    async def report_429(self, platform: SourcePlatform, default_rate: float, duration: int = 300, proxy_url: Optional[str] = None) -> None:
        """報告遭遇 429 限制，觸發冷卻與降速機制。"""
        await self.trigger_cooling(platform, duration, proxy_url)
        if not self.redis: return
            
        name: str = platform.value
        try:
            self.redis.set(f"throttle:success_streak:{name}", 0)
            current: float = await self.get_adaptive_rate(platform, default_rate)
            # 調降 30%，最低保留 10%
            new_rate: float = max(current * 0.7, default_rate * 0.1)
            self.redis.set(f"throttle:adaptive_rate:{name}", new_rate)
            logger.warning("throttle_adaptive_backoff", platform=name, old=current, new=new_rate)
        except Exception as e:
            logger.error("throttle_report_429_failed", error=str(e))

    async def wait_for_slot(self, platform: SourcePlatform, rate: float = 1.0, capacity: float = 10.0, 
                        timeout: float = 60.0, proxy_url: Optional[str] = None) -> bool:
        """
        分佈式令牌獲取函數（具備阻塞式等待）。
        
        Args:
            platform (SourcePlatform): 來源平台。
            rate (float): 基礎每秒令牌率。
            capacity (float): 令牌桶容量。
            timeout (float): 最大等待秒數。
            proxy_url (Optional[str]): 代理 URL。
            
        Returns:
            bool: 是否成功取得權限。
        """
        if not self.redis or not self.lua_script: return True

        name: str = platform.value
        token_key: str = f"throttle:{name}"
        start_ts: float = time.time()

        while True:
            # 1. 檢查逾時
            if time.time() - start_ts > timeout:
                logger.warning("throttle_wait_timeout", platform=name, timeout=timeout)
                return False

            # 2. 檢查冷卻
            if await self.is_cooling(platform, proxy_url):
                await asyncio.sleep(2.0)
                continue

            # 3. 執行 Lua 獲取
            try:
                curr_rate: float = await self.get_adaptive_rate(platform, rate)
                now: float = time.time()
                result: Union[int, float] = self.lua_script(keys=[token_key], args=[curr_rate, capacity, now])
                
                if result == 1:
                    return True
                
                # 需等待，result 為負值預期等待秒數
                wait_val: float = abs(float(result))
                # 增加 Jitter 抖動
                wait_val = min(wait_val + random.uniform(0.01, 0.05), 5.0)
                await asyncio.sleep(wait_val)
                
            except Exception as e:
                logger.error("throttle_lua_exec_failed", platform=name, error=str(e))
                return True  # 發生錯誤時傾向放行，避免全系統卡死
