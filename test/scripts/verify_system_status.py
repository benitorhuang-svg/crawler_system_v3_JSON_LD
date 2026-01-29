
import asyncio
import os
import sys
from datetime import datetime
from core.infra import Database

async def verify_status():
    db = Database()
    pool = await db._get_pool()
    
    print("=== DATABASE VERIFICATION REPORT ===")
    
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as c:
                # 1. Check Row Counts
                print("\n[1. Row Counts]")
                await c.execute("SELECT COUNT(*) FROM tb_jobs WHERE platform='platform_104'")
                job_count = (await c.fetchone())[0]
                print(f"tb_jobs (104): {job_count}")
                
                await c.execute("SELECT COUNT(*) FROM tb_companies WHERE platform='platform_104'")
                comp_count = (await c.fetchone())[0]
                print(f"tb_companies (104): {comp_count}")
                
                if comp_count == 0:
                    print("!! WARNING: No company data found. Identifying why persistence failed.")
                
                # 2. Check Cleanliness
                print("\n[2. Address Cleanliness]")
                await c.execute("SELECT COUNT(*) FROM tb_companies WHERE platform='platform_104' AND address LIKE '%no=\"%'")
                dirty_count = (await c.fetchone())[0]
                print(f"Dirty Addresses (containing 'no=\"'): {dirty_count}")
                
                if dirty_count == 0 and comp_count > 0:
                    print("PASS: Data is present and clean.")
                elif dirty_count > 0:
                    print("FAIL: Dirty data persists.")
                    # Show sample
                    await c.execute("SELECT address FROM tb_companies WHERE platform='platform_104' AND address LIKE '%no=\"%' LIMIT 1")
                    sample = await c.fetchone()
                    print(f"Sample Dirty Address: {sample[0]}")
                
                # 3. Verify updated_at logic
                print("\n[3. updated_at Trigger Test]")
                test_id = "TEST_VERIFY_999"
                
                # Cleanup previous test
                await c.execute("DELETE FROM tb_companies WHERE source_id=%s", (test_id,))
                await conn.commit()
                
                # Insert initial
                print("Action: Inserting test record...")
                await c.execute("""
                    INSERT INTO tb_companies (source_id, platform, name, updated_at) 
                    VALUES (%s, 'platform_104', 'Test Company A', NOW())
                """, (test_id,))
                await conn.commit()
                
                await c.execute("SELECT updated_at FROM tb_companies WHERE source_id=%s", (test_id,))
                t1 = (await c.fetchone())[0]
                print(f"Initial updated_at: {t1}")
                
                await asyncio.sleep(1.1) # Wait >1s for second precision
                
                # Update via upsert logic (simulate SQLGenerator behavior)
                print("Action: Performing ON DUPLICATE KEY UPDATE...")
                await c.execute("""
                    INSERT INTO tb_companies (source_id, platform, name) 
                    VALUES (%s, 'platform_104', 'Test Company B') 
                    AS new_values 
                    ON DUPLICATE KEY UPDATE 
                        name = IFNULL(new_values.name, tb_companies.name),
                        updated_at = CURRENT_TIMESTAMP
                """, (test_id,))
                await conn.commit()
                
                await c.execute("SELECT updated_at FROM tb_companies WHERE source_id=%s", (test_id,))
                t2 = (await c.fetchone())[0]
                print(f"Post-Update updated_at: {t2}")
                
                if t2 > t1:
                    print("PASS: updated_at updated successfully.")
                else:
                    print(f"FAIL: updated_at did not change. ({t1} == {t2})")

                # Cleanup
                await c.execute("DELETE FROM tb_companies WHERE source_id=%s", (test_id,))
                await conn.commit()
    finally:
        await db.close_pool()

if __name__ == "__main__":
    asyncio.run(verify_status())
