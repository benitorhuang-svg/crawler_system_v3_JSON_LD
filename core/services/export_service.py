"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：export_service.py
功能描述：資料匯出服務，支援將資料庫中的職缺與公司數據備份為 CSV 或 JSON 格式。
"""
import os
import json
import csv
import aiomysql
import structlog
from datetime import datetime
from typing import List, Dict, Any, Optional
from core.infra import Database, settings

logger = structlog.get_logger(__name__)

class ExportService:
    """提供標準化的檔案匯出功能。"""
    
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.export_dir = settings.EXPORT_PATH or "exports"

    async def export_table(self, table_name: str, format: str = "csv") -> Optional[str]:
        """
        將指定資料表匯出為檔案。
        
        Args:
            table_name: 資料表名稱 (tb_jobs, tb_companies 等)。
            format: 'csv' 或 'json'。
            
        Returns:
            str: 匯出檔案的絕對路徑。
        """
        if not os.path.exists(self.export_dir):
            os.makedirs(self.export_dir, exist_ok=True)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{table_name}_{timestamp}.{format}"
        filepath = os.path.join(self.export_dir, filename)
        
        try:
            async with self.db.safe_cursor(cursor_type=aiomysql.DictCursor) as cursor:
                await cursor.execute(f"SELECT * FROM {table_name}")
                rows = await cursor.fetchall()
                
                if not rows:
                    logger.warning("export_skipped_no_data", table=table_name)
                    return None
                    
                if format == "json":
                    self._write_json(filepath, rows)
                else:
                    self._write_csv(filepath, rows)
                    
                logger.info("export_success", path=filepath, count=len(rows))
                return os.path.abspath(filepath)
                
        except Exception as e:
            logger.error("export_failed", table=table_name, error=str(e))
            return None

    def _write_json(self, path: str, data: List[Dict[str, Any]]):
        """寫入 JSON 檔案，處理日期格式。"""
        def default_ser(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            return str(obj)
            
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=default_ser)

    def _write_csv(self, path: str, data: List[Dict[str, Any]]):
        """寫入 CSV 檔案。"""
        if not data: return
        
        headers = list(data[0].keys())
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for row in data:
                # 處理日期轉字串
                for k, v in row.items():
                    if isinstance(v, datetime):
                        row[k] = v.isoformat()
                writer.writerow(row)
