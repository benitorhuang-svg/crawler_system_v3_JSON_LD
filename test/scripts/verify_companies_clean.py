import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from core.infra import Database

async def verify():
    try:
        db = Database()
        pool = await db._get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as c:
                # Check for address containing 'no="'
                await c.execute("SELECT count(*) FROM tb_companies WHERE address REGEXP 'no=\"';")
                res = await c.fetchone()
                
                # Also check for empty addresses if that matters, but user focused on 'no='
                # Let's also retrieve one clean address to verify it looks good
                await c.execute("SELECT address FROM tb_companies WHERE address IS NOT NULL LIMIT 1;")
                sample = await c.fetchone()
                
                with open("company_clean_check.txt", "w") as f:
                    f.write(f"Dirty Count: {res[0]}\n")
                    f.write(f"Sample Address: {sample[0] if sample else 'None'}\n")
                    
    except Exception as e:
        with open("company_clean_check.txt", "w") as f:
            f.write(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(verify())
