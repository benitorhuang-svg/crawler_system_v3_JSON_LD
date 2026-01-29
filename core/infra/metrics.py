"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：metrics.py
功能描述：效能監控指標定義，基於 Prometheus 實現。
"""
from prometheus_client import Counter, Histogram, Gauge

# 1. 爬蟲執行指標
CRAWL_REQUEST_TOTAL = Counter(
    "crawler_requests_total",
    "Total number of crawl requests",
    ["platform", "status"] # status: success, failed
)

EXTRACTION_COUNT_TOTAL = Counter(
    "crawler_extraction_total",
    "Total number of job extractions",
    ["platform", "status"] # status: success, failure
)

REQUEST_LATENCY_SECONDS = Histogram(
    "crawler_request_latency_seconds",
    "Crawl request latency in seconds",
    ["platform"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, float("inf"))
)

# 2. 資料庫指標
DB_POOL_USAGE = Gauge(
    "crawler_db_pool_usage",
    "Current number of active database connections",
    ["pool_name"]
)

# 3. AI 服務指標
AI_HEAL_REQUESTS_TOTAL = Counter(
    "crawler_ai_heal_requests_total",
    "Total number of AI healing requests",
    ["platform", "result"] # result: success, fail, timeout
)
