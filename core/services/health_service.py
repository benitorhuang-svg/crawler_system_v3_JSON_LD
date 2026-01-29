"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：health_service.py
功能描述：系統健康檢查服務，驗證資料庫、Redis 與 AI 服務連線狀態。
"""
import asyncio
import structlog
from core.infra.database import Database
from core.infra.redis_client import RedisClient
from core.enrichment.ollama_client import OllamaClient

logger = structlog.get_logger(__name__)

class HealthService:
    """提供系統健康狀態診斷。"""
    
    @classmethod
    async def check_all(cls) -> dict:
        """執行全方位健康檢查。"""
        results = await asyncio.gather(
            cls.check_database(),
            cls.check_redis(),
            cls.check_ollama(),
            return_exceptions=True
        )
        
        status = {
            "database": results[0] if not isinstance(results[0], Exception) else False,
            "redis": results[1] if not isinstance(results[1], Exception) else False,
            "ollama": results[2] if not isinstance(results[2], Exception) else False,
        }
        
        overall = all(status.values())
        logger.info("health_check_completed", status=status, overall=overall)
        return status

    @classmethod
    async def check_database(cls) -> bool:
        """檢查 MySQL 連線。"""
        try:
            db = Database()
            conn = await db._get_pool()
            async with conn.acquire() as cur:
                await cur.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error("health_check_db_failed", error=str(e))
            return False

    @classmethod
    async def check_redis(cls) -> bool:
        """檢查 Redis 連線。"""
        try:
            client = RedisClient().get_client()
            if not client: return False
            return client.ping()
        except Exception as e:
            logger.error("health_check_redis_failed", error=str(e))
            return False

    @classmethod
    async def check_ollama(cls) -> bool:
        """檢查 Ollama AI 服務連線。"""
        try:
            client = OllamaClient()
            # 簡單調用 list 或 tags API 
            async with (await client._get_client()) as c:
                 r = await c.get(f"{client.base_url}/api/tags")
                 return r.status_code == 200
        except Exception as e:
            logger.error("health_check_ollama_failed", error=str(e))
            return False
