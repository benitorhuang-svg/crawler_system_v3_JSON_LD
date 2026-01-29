"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：validator.py
功能描述：數據架構校驗組件，基於 JSON Schema 執行 SDD 校驗，並監控平台結構變異。
主要入口：由 core.services.crawl_service 調用。
"""
import json
import time
import structlog
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, Union
from jsonschema import validate, ValidationError

from core.infra.redis_client import RedisClient

# 設置結構化日誌
logger = structlog.get_logger(__name__)

class SchemaValidator:
    """
    數據規約校驗器 (Spec-Driven Validator)。
    負責確保解析結果符合 SSOT 定義，並在錯誤率偏高時發出警報。
    """
    
    def __init__(self, job_schema_path: Optional[str] = None, company_schema_path: Optional[str] = None) -> None:
        """初始化校驗規則。"""
        root: Path = Path(__file__).parent
        j_path: str = job_schema_path or str(root / "job_schema.json")
        c_path: str = company_schema_path or str(root / "company_schema.json")
        
        try:
            with open(j_path, "r", encoding="utf-8") as f:
                self.job_schema: Dict[str, Any] = json.load(f)
            with open(c_path, "r", encoding="utf-8") as f:
                self.company_schema: Dict[str, Any] = json.load(f)
        except Exception as e:
            logger.error("schema_load_failed", error=str(e))
            self.job_schema, self.company_schema = {}, {}

        # 失敗樣本存檔目錄
        self.sample_dir: Path = Path("test/fixtures/failed_samples")
        self.sample_dir.mkdir(parents=True, exist_ok=True)

    async def _update_stats_and_check(self, platform: str, is_fail: bool) -> None:
        """更新 Redis 中的校驗統計，並在異常時觸發警報。"""
        redis = RedisClient().get_client()
        if not redis: return

        try:
            total_key: str = f"v3:stats:{platform}:total"
            fail_key: str = f"v3:stats:{platform}:fail"
            
            await redis.incr(total_key)
            if is_fail:
                await redis.incr(fail_key)
            
            # 獲取最新比率
            total: int = int(await redis.get(total_key) or 1)
            fails: int = int(await redis.get(fail_key) or 0)
            
            if total >= 10 and (fails / total) > 0.3:
                logger.critical("structural_drift_alert", platform=platform, rate=f"{fails/total:.1%}")
        except Exception as e:
            logger.debug("stats_update_failed", error=str(e))

    def _save_sample(self, data: Dict[str, Any], label: str) -> None:
        """保存失敗樣本以供 SDD 回歸分析。"""
        try:
            pf: str = str(data.get("platform", "unknown"))
            sid: str = str(data.get("source_id") or "null")
            ts: str = str(int(time.time()))
            path: Path = self.sample_dir / f"{label}_{pf}_{sid}_{ts}.json"
            
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=self._json_serial)
            logger.info("failed_sample_saved", path=str(path))
        except Exception as e:
            logger.error("sample_save_failed", error=str(e))

    def _json_serial(self, obj: Any) -> str:
        """JSON 序列化補丁 (支援 datetime/date)。"""
        from datetime import datetime, date
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")

    async def _do_validate(self, data: Dict[str, Any], schema: Dict[str, Any], label: str) -> bool:
        """執行核心校驗邏輯。"""
        platform: str = str(data.get("platform", "unknown"))
        
        if not schema:
            return True

        try:
            validate(instance=data, schema=schema)
            await self._update_stats_and_check(platform, is_fail=False)
            return True
        except ValidationError as e:
            logger.error("schema_validation_error", type=label, path=list(e.path), msg=e.message)
            self._save_sample(data, label)
            await self._update_stats_and_check(platform, is_fail=True)
            return False

    async def validate_job(self, job_data: Dict[str, Any]) -> bool:
        """驗證職缺數據物件。"""
        return await self._do_validate(job_data, self.job_schema, "job")

    async def validate_company(self, company_data: Dict[str, Any]) -> bool:
        """驗證公司數據物件。"""
        return await self._do_validate(company_data, self.company_schema, "company")



