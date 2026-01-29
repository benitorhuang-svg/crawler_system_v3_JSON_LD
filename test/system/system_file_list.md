# 系統測試目錄進出管理登記簿

本目錄存放驗證基礎設施連通性與全流程整合的測試。

## 子目錄檔案清單

### 1. Flows (業務流程)
| 檔案名稱 | 功能說明 |
| :--- | :--- |
| `flows/test_discovery.py` | 整合測試：驗證各平台能否從分類中發現並抓回職缺 URL。 |

### 2. Infra (基礎設施)
| 檔案名稱 | 功能說明 |
| :--- | :--- |
| `infra/test_browser.py` | 測試 Playwright Chromium 的啟動與基礎操作。 |
| `infra/test_fetcher_internal.py` | 測試 `BrowserFetcher` 的網頁抓取功能。 |
| `infra/test_ollama.py` | 測試與本地 Ollama 服務的連線與 LLM 模型呼叫。 |
