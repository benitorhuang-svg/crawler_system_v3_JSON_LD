# 維運手冊：優化版職缺爬蟲系統 v3

本文件說明優化後爬蟲系統的性能架構、可靠性機制與日常維護流程。

## 性能架構
- **分散式限流 (Distributed Throttling)**：地理編碼 (Geocoding) 與平台請求透過 Redis 進行全域頻率控制。這允許系統跨多個節點水平擴展，且不會違反第三方供應商的使用規範。
- **瀏覽器 Context 池化**：管理一個固定大小的瀏覽器上下文環境池（大小約 5-10），能有效減少 Chromium 進程頻繁啟動與關閉帶來的開銷。
- **響應快取 (Response Caching)**：職缺頁面的 HTML 內容會在 Redis 中快取 1 小時，避免重複的外部請求並降低 AI 提取成本。

## 可靠性機制 (Reliability)
- **斷路器模式 (Circuit Breaker)**：外部服務（如 Ollama AI、瀏覽器抓取）接由斷路器保護。狀態包含：
    - **CLOSED (關閉)**：正常運作中。
    - **OPEN (開啟)**：服務因失敗率過高而進入隔離狀態（快速失敗），保護系統不被拖垮。
    - **HALF-OPEN (半開)**：冷卻時間過後，嘗試少量請求以確認服務是否恢復。
- **指數退避重試 (Exponential Backoff)**：所有發現與抓取操作在失敗時會自動重試，並隨重試次數增加延遲時間。

## 系統健康檢查
執行以下代碼即可驗證系統組件的連線狀態：
```python
from core.services.health_service import HealthService
import asyncio

async def main():
    # 檢查 MySQL, Redis, Ollama 的健康狀況
    await HealthService.check_all()

asyncio.run(main())
```

## 故障排除 (Troubleshooting)
| 問題現象 | 常見原因 | 解決方案 |
|-------|--------------|----------|
| 429 錯誤 (請求過快) | Redis Throttler 服務異常 | 檢查 Redis 連線狀態。 |
| 瀏覽器抓取超時 | 代理伺服器 (Proxy) 失效 | 驗證 `settings.PROXIES` 清單中的代理是否可用。 |
| AI 提取欄位為空 | Ollama 斷路器目前為 OPEN | 檢查 Ollama 服務狀態與模型是否正確加載。 |

## 系統配置
所有關鍵常數與超時設定皆集中管理於 [config.py](file:///home/soldier/crawler_system_v3_JSON_LD/core/infra/config.py)。
