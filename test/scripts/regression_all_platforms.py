"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：regression_all_platforms.py
功能描述：全平台回歸測試工具，針對各指定平台執行完整爬取生命週期並驗證資料庫中的儲存結果。
主要入口：python test/scripts/regression_all_platforms.py [104|1111|yes123|yourator|cakeresume|all]
"""
import asyncio
import argparse
import structlog
from typing import Dict, Any, List, Optional

from main import run_crawl_session
from core.infra import SourcePlatform, Database, configure_logging

# 初始化日誌
configure_logging()
logger = structlog.get_logger(__name__)

# 各平台測試基準配置
PLATFORM_CONFIGS: Dict[str, Dict[str, Any]] = {
    "104": {
        "platform": SourcePlatform.PLATFORM_104,
        "cats": ["2007001007", "2006001001"],  # 軟體工程, 行銷
        "limit": 5
    },
    "1111": {
        "platform": SourcePlatform.PLATFORM_1111,
        "cats": ["100101", "100105"],  # 經營管理, 特別助理
        "limit": 5
    },
    "yes123": {
        "platform": SourcePlatform.PLATFORM_YES123,
        "cats": ["2_1001_0001_0003", "2_1008_0001_0001"],  # 行政, 行銷
        "limit": 5
    },
    "yourator": {
        "platform": SourcePlatform.PLATFORM_YOURATOR,
        "cats": ["1", "10"],  # 商業開發, Growth Hacker
        "limit": 5
    },
    "cakeresume": {
        "platform": SourcePlatform.PLATFORM_CAKERESUME,
        "cats": ["it_back-end-engineer", "design_graphic-designer"],
        "limit": 5
    }
}

async def run_regression(platform_key: str) -> None:
    """
    對特定平台執行一系列類別的爬取回歸測試。
    
    Args:
        platform_key (str): 平台辨別名稱。
    """
    config: Optional[Dict[str, Any]] = PLATFORM_CONFIGS.get(platform_key)
    if not config:
        print(f"❌ 未知平台：{platform_key}。可用清單：{list(PLATFORM_CONFIGS.keys())}")
        return

    platform: SourcePlatform = config["platform"]
    cats: List[str] = config["cats"]
    limit: int = config["limit"]

    print(f"\n🚀 啟動 {platform_key.upper()} 回歸測試，類別總數：{len(cats)}...")
    
    for cat in cats:
        print(f"--- 執行分類週期：{cat} ---")
        # 直接使用 main.py 導出的會話執行函數
        await run_crawl_session(platform, cat_id=cat, limit=limit)
    
    # 執行資料庫結果校驗
    print(f"\n🔍 正在校驗 {platform_key.upper()} 提取品質...")
    db = Database()
    try:
        async with db.safe_cursor() as cursor:
            sql: str = """
            SELECT j.source_id, j.title, j.district, j.address, c.name as company, j.valid_through
            FROM tb_jobs j
            LEFT JOIN tb_companies c ON j.company_source_id = c.source_id
            WHERE j.platform = %s
            ORDER BY j.updated_at DESC
            LIMIT 10
            """
            await cursor.execute(sql, (platform.value,))
            rows = await cursor.fetchall()
            
            print("-" * 120)
            print(f"{'來源 ID':<15} | {'職稱':<35} | {'區域':<12} | {'公司名稱'}")
            print("-" * 120)
            for r in rows:
                r_dict: Dict[str, Any] = dict(zip([col[0] for col in cursor.description], r))
                title: str = str(r_dict['title'])[:33] + ".." if len(str(r_dict['title'])) > 35 else str(r_dict['title'])
                print(f"{str(r_dict['source_id'])[:15]:<15} | {title:<35} | {str(r_dict['district']):<12} | {str(r_dict['company'])[:20]}")
            print("-" * 120)
    finally:
        await db.close_pool()

async def main() -> None:
    """
    命令行入口。
    """
    parser = argparse.ArgumentParser(description="全平台自動化回歸測試工具")
    parser.add_argument(
        "platform", 
        choices=list(PLATFORM_CONFIGS.keys()) + ["all"], 
        help="選擇單一平台或 'all' 執行全量測試"
    )
    args = parser.parse_args()

    if args.platform == "all":
        for p in PLATFORM_CONFIGS.keys():
            await run_regression(p)
    else:
        await run_regression(args.platform)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n使用者中斷測試。")
