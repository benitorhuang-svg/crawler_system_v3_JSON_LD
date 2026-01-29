import asyncio
import aiomysql
from core.infra.config import settings

async def check_db():
    conn = await aiomysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        autocommit=True
    )
    async with conn.cursor() as cursor:
        await cursor.execute("SHOW DATABASES")
        dbs = await cursor.fetchall()
        print("Databases found via aiomysql:")
        for db in dbs:
            print(f" - {db[0]}")
    conn.close()

if __name__ == "__main__":
    asyncio.run(check_db())
