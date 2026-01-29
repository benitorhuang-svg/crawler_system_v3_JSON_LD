# 主要入口：
#     - 爬取任務：python main.py <platform> [category_id] [--limit=N]
#     - 匯入映射：python main.py import <yaml_path>
#     - 監控服務：python main.py health
#     - 資料庫初始化：python main.py init-db
import asyncio
import sys
import signal
import structlog
from typing import Optional, Dict, Any

from core.infra import SourcePlatform, configure_logging, Database, BrowserFetcher
from core.services import CrawlService, StandardCategoryService, ExportService

# 初始化日誌系統
configure_logging()
logger = structlog.get_logger(__name__)

async def run_crawl_session(platform: SourcePlatform, cat_id: Optional[str] = None, limit: int = 5) -> None:
    """
    啟動一個獨立的爬蟲作業會話。
    
    Args:
        platform: 來源平台枚舉值。
        cat_id: 選擇性指定的類別 ID。
        limit: 最大抓取職缺數量。
    """
    logger.info("session_started", platform=platform.value, category=cat_id, limit=limit)
    svc = CrawlService()
    db = Database()
    
    try:
        # A. 數據庫架構檢查與初始化
        await db.ensure_initialized()
        
        # B. 執行平台級爬取任務
        await svc.run_platform(platform, max_jobs=limit, target_cat_id=cat_id)
        
        logger.info("session_completed", platform=platform.value)
    except Exception as e:
        logger.error("session_failed", platform=platform.value, error=str(e))
    finally:
        # C. 資源清理
        await db.close_pool()
        await BrowserFetcher.close_browser()

async def main() -> None:
    """處理命令行輸入並引導執行。"""
    mapping: Dict[str, SourcePlatform] = {
        "104": SourcePlatform.PLATFORM_104,
        "1111": SourcePlatform.PLATFORM_1111,
        "cakeresume": SourcePlatform.PLATFORM_CAKERESUME,
        "yes123": SourcePlatform.PLATFORM_YES123,
        "yourator": SourcePlatform.PLATFORM_YOURATOR
    }

    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h"):
        print("\n🚀 Crawler System v3 - 指令幫助")
        print("-" * 35)
        print("1. 執行爬蟲任務:")
        print("   python main.py <104|1111|cakeresume|yes123|yourator> [category_id] [--limit=N]")
        print("\n2. 匯入分類標準對應 (YAML):")
        print("   python main.py import <path_to_yaml_file>")
        print("\n3. 啟動健康檢查與指標服務:")
        print("   python main.py health")
        print("\n4. 資料庫初始化 (建立資料表):")
        print("   python main.py init-db")
        print("\n5. 匯出資料:")
        print("   python main.py export <tb_jobs|tb_companies> [--format=csv|json]")
        print("-" * 35)
        return

    # 解析子指令或平台
    cmd_or_plat: str = sys.argv[1].lower()

    # 處理匯入指令
    if cmd_or_plat == "import":
        if len(sys.argv) < 3:
            print("錯誤: 請提供 YAML 檔案路徑。用法: python main.py import <file.yaml>")
            return
        
        yaml_path = sys.argv[2]
        print(f"📥 正在從 {yaml_path} 匯入分類映射...")
        
        svc = StandardCategoryService()
        db = Database()
        try:
            await db.ensure_initialized()
            count = await svc.import_from_yaml(yaml_path)
            print(f"✅ 匯入完成，共計 {count} 筆。")
        finally:
            await db.close_pool()
        return

    # 處理健康檢查服務
    if cmd_or_plat == "health":
        print("🏥 正在啟動健康檢查與指標服務 (FastAPI)...")
        import uvicorn
        from core.services.health_service import app as health_app
        uvicorn.run(health_app, host="0.0.0.0", port=8000)
        return

    # 處理資料庫初始化
    if cmd_or_plat == "init-db":
        print("🗄️ 正在初始化資料庫架構...")
        db = Database()
        try:
            await db.ensure_initialized()
            print("✅ 資料庫初始化完成。")
        finally:
            await db.close_pool()
        return

    # 處理資料匯出
    if cmd_or_plat == "export":
        if len(sys.argv) < 3:
            print("錯誤: 請指定要匯出的資料表。用法: python main.py export <table_name> [--format=csv|json]")
            return
        
        table = sys.argv[2]
        fmt = "csv"
        for arg in sys.argv:
            if arg.startswith("--format="):
                fmt = arg.split("=")[1].lower()
        
        print(f"📤 正在匯出 {table} 到 {fmt} 格式...")
        exporter = ExportService()
        try:
            path = await exporter.export_table(table, format=fmt)
            if path:
                print(f"✅ 匯出成功！檔案路徑: {path}")
            else:
                print("❌ 匯出失敗或無資料。")
        finally:
            await Database().close_pool()
        return

    # 解析參數 (爬取模式)
    plat_key = cmd_or_plat
    cat_id: Optional[str] = None
    limit: int = 5

    for arg in sys.argv[2:]:
        if arg.startswith("--limit="):
            try:
                limit = int(arg.split("=")[1])
            except ValueError:
                pass
        else:
            cat_id = arg

    platform = mapping.get(plat_key)
    if not platform:
        print(f"錯誤: 不支援的平台 {plat_key}")
        return

    # 設置中斷信號處理
    stop_event = asyncio.Event()
    def _handler():
        print("\n🛑 接收到中斷訊號，正在啟動優雅關閉流程...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(sig, _handler)

    try:
        # 使用 wait_for 監聽中斷或完成
        task = asyncio.create_task(run_crawl_session(platform, cat_id, limit))
        while not task.done():
            if stop_event.is_set():
                task.cancel()
                break
            await asyncio.sleep(0.5)
        await task
    except asyncio.CancelledError:
        print("✅ 任務已安全取消。")
    except Exception as e:
        logger.critical("process_fatal_error", error=str(e))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

