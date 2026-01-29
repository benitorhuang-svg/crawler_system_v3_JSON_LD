"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：database.py
功能描述：資料庫基礎設施模組，負責與 MySQL 進行連線池管理、自動建立資料表及實體資料的持久化操作。
主要入口：由 core.services 與 core.tasks 調用。
"""
import os
import asyncio
import aiomysql
import structlog
from typing import Any, Optional, List, Tuple, Dict, Union, AsyncGenerator
from contextlib import asynccontextmanager
from core.infra.config import settings

from core.infra.schemas import (
    CompanyPydantic, JobPydantic, CategoryPydantic, 
    JobCategoryJunctionPydantic, PlatformHealthPydantic,
    JobLocationPydantic, JobSkillExtractedPydantic
)
from .sql_generator import SQLGenerator
from core.infra.metrics import DB_POOL_USAGE

# 設置結構化日誌
logger = structlog.get_logger(__name__)

class Database:
    """
    資料庫存取層，封裝連線池與核心業務表的 CRUD 邏輯。
    """
    _pool: Optional[aiomysql.Pool] = None

    def __init__(self) -> None:
        """初始化資料庫配置參數。"""
        self.host: str = settings.DB_HOST
        self.port: int = settings.DB_PORT
        self.user: str = settings.DB_USER
        self.password: str = settings.DB_PASSWORD
        self.dbname: str = settings.DB_NAME

    async def _get_pool(self) -> aiomysql.Pool:
        """獲取或懶加載非同步連線池。"""
        if Database._pool is None:
            await self._ensure_db_exists()
            Database._pool = await aiomysql.create_pool(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                db=self.dbname,
                minsize=10,
                maxsize=50,
                charset='utf8mb4',
                autocommit=True
            )
        return Database._pool

    async def _ensure_db_exists(self) -> None:
        """確保目標資料庫已在 MySQL 中建立。"""
        try:
            conn: aiomysql.Connection = await aiomysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                autocommit=True
            )
            async with conn.cursor() as cursor:
                await cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.dbname} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            conn.close()
        except Exception as e:
            logger.error("ensure_db_failed", error=str(e))

    @asynccontextmanager
    async def safe_cursor(self, cursor_type: Any = aiomysql.Cursor) -> AsyncGenerator[aiomysql.Cursor, None]:
        """安全獲取 Cursor 的非同步上下文管理器。"""
        pool: aiomysql.Pool = await self._get_pool()
        DB_POOL_USAGE.labels(pool_name=self.dbname).inc()
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(cursor_type) as cursor:
                    yield cursor
        finally:
            DB_POOL_USAGE.labels(pool_name=self.dbname).dec()

    @asynccontextmanager
    async def safe_transaction(self) -> AsyncGenerator[aiomysql.Cursor, None]:
        """安全事務處理上下文管理器。"""
        pool: aiomysql.Pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.begin()
            try:
                async with conn.cursor() as cursor:
                    yield cursor
                await conn.commit()
            except Exception as e:
                await conn.rollback()
                raise e

    async def ensure_initialized(self) -> bool:
        """
        初始化資料庫：建立資料表並預填種子資料。
        """
        logger.info("db_init_started")
        await self.create_tables()
        
        async with self.safe_cursor() as cursor:
            from core.infra import SourcePlatform
            for platform in SourcePlatform:
                if platform == SourcePlatform.PLATFORM_UNKNOWN:
                    continue
                await cursor.execute("SELECT COUNT(*) FROM tb_categories WHERE platform = %s", (platform.value,))
                res = await cursor.fetchone()
                if res and res[0] == 0:
                    logger.info("seeding_platform_categories", platform=platform.value)
                    # 這裡調用各平台專屬的抓取邏輯
                    if platform == SourcePlatform.PLATFORM_104:
                        from core.categories.fetch_categories_104 import fetch_104_categories
                        await fetch_104_categories()
                    elif platform == SourcePlatform.PLATFORM_1111:
                        from core.categories.fetch_categories_1111 import fetch_1111_categories
                        await fetch_1111_categories()
                    elif platform == SourcePlatform.PLATFORM_CAKERESUME:
                        from core.categories.fetch_categories_cakeresume import fetch_cakeresume_categories
                        await fetch_cakeresume_categories()
                    elif platform == SourcePlatform.PLATFORM_YES123:
                        from core.categories.fetch_categories_yes123 import fetch_yes123_categories
                        await fetch_yes123_categories()
                    elif platform == SourcePlatform.PLATFORM_YOURATOR:
                        from core.categories.fetch_categories_yourator import fetch_yourator_categories
                        await fetch_yourator_categories()
        
        logger.info("db_init_finished")
        return True

    async def insert(self, cursor: aiomysql.Cursor, table: str, data: Dict[str, Any]) -> None:
        """基於 Pydantic 到 SQL 的自動插入工具。"""
        columns: List[str] = list(data.keys())
        placeholders: str = ", ".join(["%s"] * len(columns))
        sql: str = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
        await cursor.execute(sql, tuple(data.values()))

    async def save_full_job_data(
        self, 
        job: JobPydantic, 
        company: Optional[CompanyPydantic], 
        category_id: Optional[str] = None,
        skills: Optional[List[JobSkillExtractedPydantic]] = None,
        location: Optional[JobLocationPydantic] = None
    ) -> bool:
        """
        職缺完整資料持久化（事務原子性）。
        包含：公司、職缺主體、地理座標、技能標籤、分類關聯。
        """
        try:
            async with self.safe_transaction() as cursor:
                # 1. 存儲公司
                if company and company.source_id:
                    c_sql: str = SQLGenerator.generate_upsert_sql(CompanyPydantic, "tb_companies", ["platform", "source_id"])
                    await cursor.execute(c_sql, SQLGenerator.to_sql_params(company, exclude_cols=["created_at", "updated_at"]))
                
                # 2. 存儲職缺
                j_sql: str = SQLGenerator.generate_upsert_sql(JobPydantic, "tb_jobs", ["platform", "source_id"])
                await cursor.execute(j_sql, SQLGenerator.to_sql_params(job, exclude_cols=["created_at", "updated_at"]))
                
                # 3. 存儲地點
                if location:
                    l_sql: str = SQLGenerator.generate_upsert_sql(JobLocationPydantic, "tb_job_locations", ["platform", "job_source_id"])
                    await cursor.execute(l_sql, SQLGenerator.to_sql_params(location, exclude_cols=["created_at", "updated_at"]))
                
                # 4. 建立分類關聯
                if category_id:
                    link_sql: str = """
                        INSERT INTO tb_categories_jobs (platform, category_id, job_source_id, job_url)
                        VALUES (%s, %s, %s, %s)
                        AS new_values
                        ON DUPLICATE KEY UPDATE job_url = new_values.job_url, created_at = CURRENT_TIMESTAMP
                    """
                    await cursor.execute(link_sql, (job.platform.value, category_id, job.source_id, job.url))
                
                # 5. 存儲技能標籤
                if skills:
                    s_sql: str = SQLGenerator.generate_upsert_sql(JobSkillExtractedPydantic, "tb_job_skills_extracted", ["platform", "job_source_id", "skill_name"])
                    for s in skills:
                        await cursor.execute(s_sql, SQLGenerator.to_sql_params(s, exclude_cols=["created_at", "updated_at"]))
            return True
        except Exception as e:
            logger.error("persistence_failed", url=job.url, error=str(e))
            return False

    async def save_company(self, company: CompanyPydantic) -> bool:
        """單獨儲存公司資料。"""
        try:
            async with self.safe_cursor() as cursor:
                sql: str = SQLGenerator.generate_upsert_sql(CompanyPydantic, "tb_companies", ["platform", "source_id"])
                await cursor.execute(sql, SQLGenerator.to_sql_params(company, exclude_cols=["created_at", "updated_at"]))
            return True
        except Exception as e:
            logger.error("save_company_failed", name=company.name, error=str(e))
            return False

    async def save_job(self, job: JobPydantic) -> bool:
        """單獨儲存職缺資料。"""
        try:
            async with self.safe_cursor() as cursor:
                sql: str = SQLGenerator.generate_upsert_sql(JobPydantic, "tb_jobs", ["platform", "source_id"])
                await cursor.execute(sql, SQLGenerator.to_sql_params(job, exclude_cols=["created_at", "updated_at"]))
            return True
        except Exception as e:
            logger.error("save_job_failed", url=job.url, error=str(e))
            return False

    async def save_job_location(self, loc: JobLocationPydantic) -> None:
        """儲存職缺地理座標。"""
        try:
            async with self.safe_cursor() as cursor:
                sql: str = SQLGenerator.generate_upsert_sql(JobLocationPydantic, "tb_job_locations", ["platform", "job_source_id"])
                await cursor.execute(sql, SQLGenerator.to_sql_params(loc, exclude_cols=["created_at", "updated_at"]))
        except Exception as e:
            logger.error("save_loc_failed", id=loc.job_source_id, error=str(e))

    async def save_job_skills(self, skills: List[JobSkillExtractedPydantic]) -> None:
        """批量儲存提取出的技能。"""
        if not skills: return
        try:
            async with self.safe_transaction() as cursor:
                sql: str = SQLGenerator.generate_upsert_sql(JobSkillExtractedPydantic, "tb_job_skills_extracted", ["platform", "job_source_id", "skill_name"])
                params = [SQLGenerator.to_sql_params(sk, exclude_cols=["created_at", "updated_at"]) for sk in skills]
                await cursor.executemany(sql, params)
        except Exception as e:
            logger.error("save_skills_failed", error=str(e))

    async def save_job_category_junction(self, junction: JobCategoryJunctionPydantic) -> bool:
        """建立職缺與分類的關聯紀錄。"""
        try:
            async with self.safe_cursor() as cursor:
                sql: str = """
                    INSERT INTO tb_categories_jobs (platform, category_id, job_source_id, job_url)
                    VALUES (%s, %s, %s, %s)
                    AS new_values
                    ON DUPLICATE KEY UPDATE job_url = new_values.job_url
                """
                await cursor.execute(sql, (junction.platform.value, junction.category_id, junction.job_source_id, junction.job_url))
            return True
        except Exception as e:
            logger.error("save_junction_failed", error=str(e))
            return False

    async def record_platform_health(self, platform: str, success: bool, extraction_success: bool = True, latency_ms: int = 0, error_msg: Optional[str] = None) -> None:
        """更新平台健康度指標（SDD 監控標準）。"""
        try:
            async with self.safe_transaction() as cursor:
                sql: str = """
                INSERT INTO tb_platform_health (
                    platform, total_requests, success_requests, failed_requests, 
                    extraction_success, extraction_failure, avg_latency_ms, last_error
                ) VALUES (%s, 1, %s, %s, %s, %s, %s, %s)
                AS new_v
                ON DUPLICATE KEY UPDATE
                    tb_platform_health.total_requests = tb_platform_health.total_requests + 1,
                    tb_platform_health.success_requests = tb_platform_health.success_requests + new_v.success_requests,
                    tb_platform_health.failed_requests = tb_platform_health.failed_requests + new_v.failed_requests,
                    tb_platform_health.extraction_success = tb_platform_health.extraction_success + new_v.extraction_success,
                    tb_platform_health.extraction_failure = tb_platform_health.extraction_failure + new_v.extraction_failure,
                    tb_platform_health.avg_latency_ms = (tb_platform_health.avg_latency_ms * 0.9) + (new_v.avg_latency_ms * 0.1),
                    tb_platform_health.last_error = IF(new_v.last_error IS NOT NULL, new_v.last_error, tb_platform_health.last_error),
                    tb_platform_health.updated_at = CURRENT_TIMESTAMP
                """
                s_i: int = 1 if success else 0
                f_i: int = 0 if success else 1
                ex_s: int = 1 if extraction_success else 0
                ex_f: int = 0 if extraction_success else 1
                
                params: Tuple = (
                    platform, s_i, f_i, ex_s, ex_f, latency_ms, error_msg
                )
                await cursor.execute(sql, params)
        except Exception as e:
            logger.error("health_record_failed", platform=platform, error=str(e))

    async def mark_category_as_crawled(self, platform: str, category_id: str) -> None:
        """更新分類的最後抓取狀態。"""
        try:
            async with self.safe_cursor() as cursor:
                await cursor.execute(
                    "UPDATE tb_categories SET updated_at = CURRENT_TIMESTAMP WHERE platform = %s AND layer_3_id = %s",
                    (platform, category_id)
                )
        except Exception as e:
            logger.error("mark_crawled_failed", platform=platform, cat=category_id, error=str(e))

    async def get_crawled_categories(self, platform: str, days: int = 30) -> set:
        """
        取得指定平台已爬取的分類列表。
        
        Args:
            platform (str): 平台名稱 (e.g., 'platform_104')。
            days (int): 查詢時間範圍（天數，預設 30 天）。
        
        Returns:
            set: 已爬取的分類 ID 集合。
        """
        try:
            async with self.safe_cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT DISTINCT layer_3_id 
                    FROM tb_categories 
                    WHERE platform = %s 
                      AND updated_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                    """,
                    (platform, days)
                )
                rows = await cursor.fetchall()
                return {row[0] for row in rows}
        except Exception as e:
            logger.error("get_crawled_categories_failed", platform=platform, error=str(e))
            return set()

    async def upsert_categories(self, categories: List[Dict[str, Any]]) -> bool:
        """
        批次 Upsert 分類資料。
        基於 CategoryPydantic 定義執行 ON DUPLICATE KEY UPDATE。
        """
        if not categories: return True
        try:
            async with self.safe_transaction() as cursor:
                sql: str = SQLGenerator.generate_upsert_sql(CategoryPydantic, "tb_categories", ["platform", "layer_3_id"])
                # 確保數據符合 Pydantic 模型定義
                params = [SQLGenerator.to_sql_params(CategoryPydantic(**cat_dict), exclude_cols=["created_at", "updated_at"]) for cat_dict in categories]
                await cursor.executemany(sql, params)
            return True
        except Exception as e:
            logger.error("upsert_categories_failed", error=str(e))
            return False

    async def create_tables(self) -> bool:
        """根據 Pydantic 模型定義自動同步資料表結構。"""
        try:
            async with self.safe_transaction() as cursor:
                await cursor.execute("SET sql_notes = 0")
                await cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
                
                # 定義資料表建置清單 (順序優化：被參考之父表優先)
                table_configs: List[Tuple[Any, str, str, List[str]]] = [
                    (CompanyPydantic, "tb_companies", "公司詳情表", [
                        "UNIQUE KEY uniq_comp (platform, source_id)",
                        "INDEX idx_source_id (source_id)"  # 支援外鍵跳轉
                    ]),
                    (CategoryPydantic, "tb_categories", "類別種子表", [
                        "UNIQUE KEY uniq_cat (platform, layer_3_id)",
                        "INDEX idx_layer3_id (layer_3_id)" # 支援外鍵跳轉
                    ]),
                    (JobPydantic, "tb_jobs", "職缺詳情表", [
                        "UNIQUE KEY uniq_job (platform, source_id)",
                        "INDEX idx_source_id (source_id)"  # 支援外鍵跳轉
                    ]),
                    (JobCategoryJunctionPydantic, "tb_categories_jobs", "分類職缺關聯", ["UNIQUE KEY uniq_rel (platform, category_id, job_source_id)"]),
                    (PlatformHealthPydantic, "tb_platform_health", "健康度監控", []),
                    (JobLocationPydantic, "tb_job_locations", "地理座標表", ["UNIQUE KEY uniq_loc (platform, job_source_id)"]),
                    (JobSkillExtractedPydantic, "tb_job_skills_extracted", "技能提取表", ["UNIQUE KEY uniq_skill (platform, job_source_id, skill_name)"])
                ]
                
                for model, name, desc, constr in table_configs:
                    sql: str = SQLGenerator.generate_create_table_sql(model, name, desc, extra_constraints=constr)
                    await cursor.execute(sql)
                
                await cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
                
                # 建立額外優化索引
                extra_indexes = [
                    "CREATE INDEX idx_jobs_platform_date ON tb_jobs (platform, posted_at)",
                    "CREATE INDEX idx_categories_platform_crawl ON tb_categories (platform, updated_at)",
                    "CREATE INDEX idx_jobs_layer_cat ON tb_jobs (layer_category_name, posted_at)"
                ]
                for idx_sql in extra_indexes:
                    try:
                        await cursor.execute(idx_sql)
                    except Exception:
                        pass # 忽略已存在的索引錯誤
            return True
        except Exception as e:
            logger.error("schema_sync_failed", error=str(e))
            return False

    async def close_pool(self) -> None:
        """優雅關閉全域連線池。"""
        if Database._pool:
            pool: aiomysql.Pool = Database._pool
            Database._pool = None
            pool.close()
            await pool.wait_closed()
            logger.info("db_pool_closed")
