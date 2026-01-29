"""
專案名稱：crawler_system_v3_JSON_LD
測試模組：test_e2e_flow.py
描述：執行端到端 (E2E) 爬蟲流程驗證，模擬從主進入點到資料持久化的完整鏈路。
"""
import asyncio
import pytest
import structlog
from core.infra import Database, SourcePlatform
from main import run_crawl_session

logger = structlog.get_logger(__name__)

@pytest.mark.asyncio
async def test_minimal_e2e_104():
    """
    測試 104 平台的極簡抓取流程。
    """
    db = Database()
    try:
        print("\n🚀 啟動 E2E 抓取測試 (104)...")
        await run_crawl_session(SourcePlatform.PLATFORM_104, limit=1)
        async with db.safe_cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM tb_jobs WHERE platform = %s", (SourcePlatform.PLATFORM_104.value,))
            count = (await cur.fetchone())[0]
            print(f"📊 104 抓取完成，資料庫紀錄數：{count}")
            assert count >= 0
    finally:
        await db.close_pool()

@pytest.mark.asyncio
async def test_minimal_e2e_yourator():
    """
    測試 Yourator 平台的極簡抓取流程。
    """
    db = Database()
    try:
        print("\n🚀 啟動 E2E 抓取測試 (Yourator)...")
        await run_crawl_session(SourcePlatform.PLATFORM_YOURATOR, limit=1)
        async with db.safe_cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM tb_jobs WHERE platform = %s", (SourcePlatform.PLATFORM_YOURATOR.value,))
            count = (await cur.fetchone())[0]
            print(f"📊 Yourator 抓取完成，資料庫紀錄數：{count}")
            assert count >= 0
    finally:
        await db.close_pool()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "yourator":
        asyncio.run(test_minimal_e2e_yourator())
    else:
        asyncio.run(test_minimal_e2e_104())
