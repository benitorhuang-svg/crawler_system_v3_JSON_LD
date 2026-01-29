import asyncio
import aiomysql
import json
import os

async def dump_raw_json():
    conn = await aiomysql.connect(
        host="localhost",
        port=3306,
        user="root",
        password="root",
        db="crawler_db"
    )
    async with conn.cursor(aiomysql.DictCursor) as cur:
        await cur.execute("SELECT url, raw_json FROM tb_jobs WHERE platform = 'platform_104' AND url = 'https://www.104.com.tw/job/6szw1' LIMIT 1")
        row = await cur.fetchone()
        if row:
            print(f"URL: {row['url']}")
            raw = row['raw_json']
            if isinstance(raw, str):
                raw = json.loads(raw)
            print("--- RAW JSON ---")
            print(json.dumps(raw, indent=2, ensure_ascii=False))
        else:
            print("Row not found")
    conn.close()

if __name__ == "__main__":
    asyncio.run(dump_raw_json())
