"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：dashboard_server.py
功能描述：數據看板後端伺服器，提供職缺數據與系統健康狀態的 API 接口。
主要入口：uvicorn dashboard.dashboard_server:app --reload
"""
import os
import structlog
import aiomysql
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from core.infra import Database

# 1. 初始化與配置
logger = structlog.get_logger(__name__)
app = FastAPI(title="Job Crawler Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db = Database()

# --- API 路由 ---

@app.get("/api/stats")
async def get_system_stats() -> Dict[str, Any]:
    """獲取系統層次的彙總數據。"""
    try:
        async with db.safe_cursor(cursor_type=aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT COUNT(*) as total FROM tb_jobs")
            jobs = await cursor.fetchone()
            await cursor.execute("SELECT COUNT(*) as total FROM tb_companies")
            comps = await cursor.fetchone()
            
            # 獲取地理座標覆蓋率 (如果有座標則視為已覆蓋)
            await cursor.execute("SELECT COUNT(*) as total FROM tb_job_locations")
            locs = await cursor.fetchone()
            
            total_jobs = jobs["total"] if jobs else 0
            geo_coverage = (locs["total"] / total_jobs * 100) if total_jobs > 0 else 0
            
            # 獲取資料來源層級分佈
            await cursor.execute("SELECT data_source_layer, COUNT(*) as count FROM tb_companies GROUP BY data_source_layer")
            layers = await cursor.fetchall()
            
            return {
                "job_count": total_jobs,
                "company_count": comps["total"] if comps else 0,
                "geo_coverage": round(geo_coverage, 1),
                "layers": {row["data_source_layer"]: row["count"] for row in layers}
            }
    except Exception as e:
        logger.error("api_stats_error", error=str(e))
        raise HTTPException(status_code=500, detail="數據統計異常")

@app.get("/api/health")
async def get_platform_health() -> List[Dict[str, Any]]:
    """獲取各爬蟲平台的連線與提取健康度。"""
    try:
        async with db.safe_cursor(cursor_type=aiomysql.DictCursor) as cursor:
            await cursor.execute("SELECT * FROM tb_platform_health")
            data = await cursor.fetchall()
            
            # 轉換為前端可用的燈號狀態
            for p in data:
                total: int = p.get("total_requests", 0)
                success: int = p.get("success_requests", 0)
                if total > 0:
                    ratio: float = success / total
                    if ratio >= 0.9: p["status"] = "green"
                    elif ratio >= 0.7: p["status"] = "yellow"
                    else: p["status"] = "red"
                else:
                    p["status"] = "gray"
            return data
    except Exception as e:
        logger.error("api_health_error", error=str(e))
        raise HTTPException(status_code=500, detail="健康檢查異常")

@app.get("/api/jobs")
async def get_recent_jobs(limit: int = 50) -> List[Dict[str, Any]]:
    """獲取最近抓取的職缺列表。"""
    try:
        async with db.safe_cursor(cursor_type=aiomysql.DictCursor) as cursor:
            sql = "SELECT * FROM tb_jobs ORDER BY created_at DESC LIMIT %s"
            await cursor.execute(sql, (limit,))
            return await cursor.fetchall() or []
    except Exception as e:
        logger.error("api_jobs_error", error=str(e))
        raise HTTPException(status_code=500, detail="職缺查詢異常")

# --- 頁面路由 ---

@app.get("/")
async def index():
    """根目錄重定向。"""
    return RedirectResponse(url="/dashboard")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page():
    """渲染主看板頁面。"""
    path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Dashboard UI Not Found")
        
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
