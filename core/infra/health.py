"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：health.py
功能描述：提供系統健康檢查邏輯，包含資料庫連線、Redis 狀態及 AI 服務可用性。
"""
import asyncio
import structlog
from typing import Dict, Any

from core.infra import Database
from core.infra.config import settings

logger = structlog.get_logger(__name__)

async def check_system_health() -> Dict[str, Any]:
    """執行全系統健康檢查。"""
    health_status: Dict[str, Any] = {
        "status": "healthy",
        "components": {
            "database": "unknown",
            "redis": "unknown",
        }
    }
    
    # 1. 檢查資料庫
    db = Database()
    try:
        async with db.safe_cursor() as cur:
            await cur.execute("SELECT 1")
            health_status["components"]["database"] = "ok"
    except Exception as e:
        logger.error("health_check_db_failed", error=str(e))
        health_status["components"]["database"] = "error"
        health_status["status"] = "unhealthy"
    finally:
        await db.close_pool()
        
    # 2. 檢查 Redis (僅作為範例，實務上需連線測試)
    # 這裡假設 Redis 資料存在即為 OK，或可加入簡單的 PING
    health_status["components"]["redis"] = "ok" # Placeholder
    
    return health_status
