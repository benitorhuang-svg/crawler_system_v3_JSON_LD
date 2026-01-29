"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：inspect_data.py
功能描述：資料檢查與品質審計工具，提供系統健康狀況、數據完整性審核、個別職缺查詢及富化樣本比對。
主要入口：python test/scripts/inspect_data.py [health|audit|query|categories|enrichment|schema]
"""
import asyncio
import argparse
import sys
import os
import json
from typing import List, Dict, Any, Optional

# 環境路徑修正：確保能從任何位置執行腳本並正確匯入 core 模組
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import aiomysql
import structlog
from core.infra import Database, configure_logging

# 初始化日誌
configure_logging()
logger = structlog.get_logger(__name__)

async def check_health() -> None:
    """
    檢查資料庫連線狀況、職缺總量與平台即時健康指標。
    """
    db: Database = Database()
    try:
        async with db.safe_cursor(cursor_type=aiomysql.DictCursor) as cur:
            # 1. 檢查資料表狀態
            await cur.execute("SHOW TABLES")
            tables: List[Dict[str, str]] = await cur.fetchall()
            print(f"\n✅ 資料庫連線正常。資料表數量：{len(tables)}")
            
            # 2. 統計職缺總數
            await cur.execute("SELECT COUNT(*) as c FROM tb_jobs")
            count_res = await cur.fetchone()
            count: int = count_res['c'] if count_res else 0
            
            await cur.execute("SELECT COUNT(*) as c FROM tb_category_standardization")
            std_count_res = await cur.fetchone()
            std_count: int = std_count_res['c'] if std_count_res else 0
            
            print(f"📊 系統目前職缺總數：{count}")
            print(f"🏷️  已建立標準映射數：{std_count}")

            # 3. 顯示平台運作指標
            print("\n=== 平台監控指標 ===")
            await cur.execute("SELECT * FROM tb_platform_health")
            healths: List[Dict[str, Any]] = await cur.fetchall()
            for h in healths:
                ratio: str = f"{h['success_requests']}/{h['total_requests']}"
                print(f"- {h['platform']:<15}: {ratio:<10} | 最後錯誤: {h['last_error'] or '無'}")
    finally:
        await db.close_pool()

async def audit_quality() -> None:
    """
    執行資料品質審計，計算核心欄位（如標題、薪資、地址）的缺失率。
    """
    db: Database = Database()
    try:
        async with db.safe_cursor(cursor_type=aiomysql.DictCursor) as cur:
            await cur.execute("SELECT title, salary_text, address, company_source_id, std_major_category FROM tb_jobs")
            jobs: List[Dict[str, Any]] = await cur.fetchall()
            total: int = len(jobs)
            
            print(f"\n=== 數據品質審計 (分析樣本 N={total}) ===")
            if total == 0:
                print("目前資料庫為空，無法執行審計。")
                return

            # 定義核心檢驗欄位
            fields: List[str] = ["title", "salary_text", "address", "std_major_category"]
            for f in fields:
                missing: int = sum(1 for j in jobs if not j.get(f))
                rate: float = (missing / total) * 100
                # 燈號指示
                status: str = "🟢" if rate < 2 else "🟡" if rate < 10 else "🔴"
                print(f"{status} {f:<20}: 缺失 {missing:>4} 筆 ({rate:>5.1f}%)")
    finally:
        await db.close_pool()

async def inspect_job(job_id: str) -> None:
    """
    依據 ID 查詢單一職缺的詳細內容。
    """
    db: Database = Database()
    try:
        async with db.safe_cursor(cursor_type=aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM tb_jobs WHERE source_id = %s", (job_id,))
            job = await cur.fetchone()
            if job:
                print(f"\n=== 職缺詳情：{job_id} ===")
                print(json.dumps(job, indent=2, default=str, ensure_ascii=False))
            else:
                print(f"❌ 查無 source_id 為 [{job_id}] 的職缺。")
    finally:
        await db.close_pool()

async def check_categories() -> None:
    """
    統計 tb_categories 中各平台的分類種子分佈情況。
    """
    db: Database = Database()
    try:
        async with db.safe_cursor() as cur:
            await cur.execute("SELECT platform, COUNT(*) FROM tb_categories GROUP BY platform")
            rows = await cur.fetchall()
            print("\n=== 各平台分類種子統計 (Seed) ===")
            for row in rows:
                print(f"- {row[0]:<15}: {row[1]:>5} 筆")
                
            await cur.execute("SELECT platform, COUNT(*) FROM tb_category_standardization GROUP BY platform")
            std_rows = await cur.fetchall()
            print("\n=== 各平台標準類別映射 (Standardization) ===")
            for row in std_rows:
                print(f"- {row[0]:<15}: {row[1]:>5} 筆")
    finally:
        await db.close_pool()

async def check_enrichment() -> None:
    """
    抽查地理座標富化與技能自動提取的數據內容。
    """
    db: Database = Database()
    try:
        async with db.safe_cursor(cursor_type=aiomysql.DictCursor) as cur:
            print("\n=== 地理座標富化抽檢 (Top 5) ===")
            await cur.execute("SELECT * FROM tb_job_locations LIMIT 5")
            locs = await cur.fetchall()
            for l in locs:
                print(f"ID: {l['job_source_id']:<15} | 座標: ({l['latitude']}, {l['longitude']})")
            
            print("\n=== 技能標籤提取抽檢 (Top 5) ===")
            await cur.execute("SELECT * FROM tb_job_skills_extracted LIMIT 5")
            skills = await cur.fetchall()
            for s in skills:
                print(f"ID: {s['job_source_id']:<15} | 技能: {s['skill_name']} [{s['skill_type']}]")
    finally:
        await db.close_pool()

async def check_schema() -> None:
    """
    輸出 tb_jobs 的資料表結構定義。
    """
    db: Database = Database()
    try:
        async with db.safe_cursor() as cur:
            print("\n=== tb_jobs 表結構定義 ===")
            await cur.execute("DESCRIBE tb_jobs")
            rows = await cur.fetchall()
            for row in rows: 
                print(row)
    finally:
        await db.close_pool()

def main() -> None:
    """
    CLI 入口解析。
    """
    parser = argparse.ArgumentParser(description="Crawler 專案資料庫檢查與品質監控工具")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # 子指令註冊
    subparsers.add_parser("health", help="檢核系統整體運作與資料總量")
    subparsers.add_parser("audit", help="執行數據完整性審核 (欄位缺失率)")
    
    q_parser = subparsers.add_parser("query", help="查詢特定職缺之完整原始資料")
    q_parser.add_argument("--id", required=True, help="職缺原始 ID (source_id)")
    
    subparsers.add_parser("categories", help="分析各平台分類種子分佈")
    subparsers.add_parser("enrichment", help="抽樣檢查座標與技能提取成果")
    subparsers.add_parser("schema", help="展示核心職缺表之 Schema 定義")

    args: argparse.Namespace = parser.parse_args()
    
    # 邏輯分發
    loop = asyncio.get_event_loop()
    if args.command == "health":
        loop.run_until_complete(check_health())
    elif args.command == "audit":
        loop.run_until_complete(audit_quality())
    elif args.command == "query":
        loop.run_until_complete(inspect_job(args.id))
    elif args.command == "categories":
        loop.run_until_complete(check_categories())
    elif args.command == "enrichment":
        loop.run_until_complete(check_enrichment())
    elif args.command == "schema":
        loop.run_until_complete(check_schema())

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
