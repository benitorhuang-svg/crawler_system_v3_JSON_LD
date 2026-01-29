"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：manage_db.py
功能描述：資料庫管理與運維工具，提供重置、初始化、清空資料表內容及緊急 Schema 修補功能。
主要入口：python test/scripts/manage_db.py [reset|init|clean|dump|fix-schema]
"""
import asyncio
import argparse
import sys
import os
import aiomysql
import structlog
from typing import Any, Optional, List, Dict

# 環境路徑修正
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from core.infra import Database, configure_logging

# 初始化日誌
configure_logging()
logger = structlog.get_logger(__name__)

async def _get_root_conn() -> aiomysql.Connection:
    """
    獲取具備管理權限的資料庫連線。
    """
    return await aiomysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "root"),
        autocommit=True
    )

async def reset_db() -> None:
    """
    ⚠️ 危險操作：重置整個資料庫環境。
    流程：刪除 crawler_db -> 重建 crawler_db -> 依據模型初始化資料表。
    """
    print("\n⚠️ 警報：正在重置資料庫環境...")
    
    try:
        conn: aiomysql.Connection = await _get_root_conn()
        async with conn.cursor() as cur:
            await cur.execute("DROP DATABASE IF EXISTS crawler_db")
            await cur.execute("CREATE DATABASE crawler_db")
        conn.close()
        
        # 重新初始化表結構
        db: Database = Database()
        await db.create_tables()
        await db.close_pool()
        print("✅ 資料庫重建並初始化完畢。")
    except Exception as e:
        logger.error("reset_db_failed", error=str(e))
        print(f"❌ 重置失敗：{e}")

async def init_db() -> None:
    """
    初始化資料表結構（冪等操作，不會影響既有數據）。
    """
    print("🚀 正在執行資料表結構檢查與初始化...")
    db: Database = Database()
    try:
        await db.create_tables()
        print("✅ 資料表結構同步完成。")
    finally:
        await db.close_pool()

async def clean_tables() -> None:
    """
    ⚠️ 危險操作：清空所有職缺相關資料表的內容。
    """
    print("\n⚠️ 正在清空核心資料表數據...")
    db: Database = Database()
    try:
        async with db.safe_cursor() as cur:
            # 關閉外鍵檢查以便執行 TRUNCATE
            await cur.execute("SET FOREIGN_KEY_CHECKS = 0")
            tables: List[str] = [
                "tb_jobs", "tb_companies", "tb_categories_jobs", 
                "tb_data_issues"
            ]
            for t in tables:
                print(f" [+] 正在清空 {t}...")
                await cur.execute(f"TRUNCATE TABLE {t}")
            await cur.execute("SET FOREIGN_KEY_CHECKS = 1")
        print("✅ 指定資料表已清空。")
    finally:
        await db.close_pool()

async def dump_db_sample() -> None:
    """
    快照展示當前資料庫內的職缺樣本與健康狀態。
    """
    db: Database = Database()
    try:
        async with db.safe_cursor(cursor_type=aiomysql.DictCursor) as cursor:
            print("\n=== 職缺提取樣本抽查 ===")
            await cursor.execute("SELECT platform, source_id, title, layer_category_name FROM tb_jobs LIMIT 5")
            jobs = await cursor.fetchall()
            for j in jobs: 
                cat_tag = f"[{j['layer_category_name']}]" if j['layer_category_name'] else "[未對應]"
                print(f"- [{j['platform']}] {cat_tag} {j['title']}")
            
            print("\n=== 各平台即時運作狀態 ===")
            await cursor.execute("SELECT * FROM tb_platform_health")
            health = await cursor.fetchall()
            for h in health: 
                print(f"- {h['platform']}: {h['success_requests']}/{h['total_requests']}")
    finally:
        await db.close_pool()

async def fix_schema_patch() -> None:
    """
    執行非破壞性的 Schema 熱修補程式。
    """
    print("🚀 正在掃描並套用 Schema 修補程式...")
    db: Database = Database()
    try:
        async with db.safe_cursor() as cursor:
            # 範例修補：確保新欄位與新表存在
            patches: List[str] = [
                "ALTER TABLE tb_jobs ADD COLUMN IF NOT EXISTS layer_category_name VARCHAR(100) AFTER industry",
                "ALTER TABLE tb_jobs ADD COLUMN IF NOT EXISTS data_source_layer VARCHAR(20) DEFAULT 'L1' COMMENT '來源層級'"
            ]
            for sql in patches:
                try:
                    await cursor.execute(sql)
                except Exception:
                    pass
        print("✅ Schema 修補程序執行結束。")
    finally:
        await db.close_pool()

def main() -> None:
    """
    指令解析入口。
    """
    parser = argparse.ArgumentParser(description="Crawler 專案維護與資料庫管理組件")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    subparsers.add_parser("reset", help="徹底刪除並重建資料庫環境")
    subparsers.add_parser("init", help="同步資料表結構 (Create if not exists)")
    subparsers.add_parser("clean", help="清空所有職缺與公司相關數據")
    subparsers.add_parser("dump", help="檢視資料庫內容快照")
    subparsers.add_parser("fix-schema", help="套用預定義的 Schema 熱修補程式")
    
    args: argparse.Namespace = parser.parse_args()
    
    loop = asyncio.get_event_loop()
    if args.command == "reset":
        loop.run_until_complete(reset_db())
    elif args.command == "init":
        loop.run_until_complete(init_db())
    elif args.command == "clean":
        loop.run_until_complete(clean_tables())
    elif args.command == "dump":
        loop.run_until_complete(dump_db_sample())
    elif args.command == "fix-schema":
        loop.run_until_complete(fix_schema_patch())

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
