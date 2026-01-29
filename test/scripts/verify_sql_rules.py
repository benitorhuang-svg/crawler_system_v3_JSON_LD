import asyncio
import structlog
from sqlalchemy import text
from core.infra import Database, configure_logging

configure_logging()
logger = structlog.get_logger(__name__)

async def verify_data_integrity():
    """
    驗證 jobs 資料表的資料完整性，根據 small_sample_test_plan.md 的規則。
    """
    db = Database()
    # await db.ensure_initialized()  <-- SKIPPED
    
    try:
        async with db.safe_cursor() as cursor:
            # 1. 檢查總筆數
            await cursor.execute("SELECT platform, COUNT(*) as count FROM tb_jobs GROUP BY platform")
            rows = await cursor.fetchall()
            logger.info("--- Job Counts by Platform ---")
            for row in rows:
                logger.info(f"Platform: {row[0]}, Count: {row[1]}")
            
            # 2. 檢查經緯度邏輯 (需 Join tb_job_locations)
            # 規則: latitude 不可為 Null
            logger.info("--- Checking Latitude/Longitude Integrity ---")
            await cursor.execute("""
                SELECT j.id, j.platform, j.address, l.latitude, l.longitude 
                FROM tb_jobs j
                LEFT JOIN tb_job_locations l 
                    ON j.platform = l.platform AND j.source_id = l.job_source_id
                WHERE l.latitude IS NULL OR l.longitude IS NULL
            """)
            null_geo_rows = await cursor.fetchall()
            if null_geo_rows:
                logger.warning(f"Found {len(null_geo_rows)} jobs with NULL latitude/longitude:")
                for row in null_geo_rows[:5]:
                    logger.warning(f"  ID: {row[0]}, Platform: {row[1]}, Address: {row[2]}")
            else:
                logger.info("PASS: All jobs have latitude/longitude populated.")

            # 3. 檢查地址品質 (使用 address 欄位)
            # 規則: address 不應包含 json 符號 ({, }) 或純數字
            logger.info("--- Checking Address Quality ---")
            await cursor.execute("""
                SELECT id, platform, address 
                FROM tb_jobs 
                WHERE address LIKE '%{%' 
                   OR address LIKE '%}%'
                   OR address REGEXP '^[0-9]+$'
            """)
            bad_address_rows = await cursor.fetchall()
            if bad_address_rows:
                logger.error(f"FAIL: Found {len(bad_address_rows)} jobs with invalid address format:")
                for row in bad_address_rows:
                    logger.error(f"  ID: {row[0]}, Platform: {row[1]}, Address: {row[2]}")
            else:
                logger.info("PASS: No invalid address formats found (JSON or pure digits).")

            # 4. 檢查公司關聯
            # 規則: company_source_id 不應為 Null (schemas.py 顯示是 company_source_id)
            logger.info("--- Checking Company Association ---")
            await cursor.execute("""
                SELECT id, platform, title 
                FROM tb_jobs 
                WHERE company_source_id IS NULL OR company_source_id = ''
            """)
            orphan_jobs = await cursor.fetchall()
            if orphan_jobs:
                logger.error(f"FAIL: Found {len(orphan_jobs)} jobs without company_source_id:")
                for row in orphan_jobs[:5]:
                     logger.error(f"  ID: {row[0]}, Platform: {row[1]}, Title: {row[2]}")
            else:
                logger.info("PASS: All jobs are associated with a company.")

    except Exception as e:
        logger.error(f"Verification failed: {e}")
    finally:
        await db.close_pool()

if __name__ == "__main__":
    asyncio.run(verify_data_integrity())
