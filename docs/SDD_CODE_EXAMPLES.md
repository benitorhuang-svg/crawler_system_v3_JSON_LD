# SDD 程式範例 (Executable Code Examples)

> [!TIP]
> 本文件提供開發者最常用的程式碼片段，可用於快速開發新功能或進行手動偵錯。

---

## 1. 新增平台適配器 (Adding a New Adapter)

若要支援新平台（例如 `JobBank-X`），請在 `core/adapters/` 建立 `adapter_jobbank_x.py`：

```python
from core.adapters.jsonld_adapter import JsonLdAdapter
from core.infra import SourcePlatform, SalaryType

class AdapterJobBankX(JsonLdAdapter):
    @property
    def platform(self) -> SourcePlatform:
        # 需先在 core/infra/__init__.py 的 SourcePlatform 新增成員
        return SourcePlatform.PLATFORM_JOBBANK_X

    def get_source_id(self, ld: dict, url: str | None = None) -> str | None:
        # 從 JSON-LD 或 URL 提取唯一 ID
        return ld.get("identifier") or url.split("/")[-1]

    def get_salary(self, ld: dict) -> dict:
        # 使用工具類解析薪資
        from core.utils.parsers import SalaryParser
        return SalaryParser.parse(ld.get("baseSalary"))

    # ... 實作其餘 @abstractmethod 方法 ...
```

---

## 2. 手動測試單一網址 (Manual URL Test)

當適配器開發完成，可建立一個暫時腳本測試提取效果：

```python
import asyncio
import httpx
from core.services import CrawlService
from core.infra import SourcePlatform

async def test_single_url():
    url = "https://www.104.com.tw/job/7xxxx"
    service = CrawlService()
    
    async with httpx.AsyncClient() as client:
        # 執行完整處理 (抓取 + 映射 + 驗證)
        job, company, location, raw_json = await service.process_url(
            url, 
            SourcePlatform.PLATFORM_104, 
            client
        )
        
        if job:
            print(f"✅ Success: {job.title} @ {job.company_source_id}")
            print(f"📍 Location: {location.latitude}, {location.longitude}")
        else:
            print("❌ Extraction Failed")

if __name__ == "__main__":
    asyncio.run(test_single_url())
```

---

## 3. 調用 AI 自癒機制 (Using AI Healing Manually)

若要在 L1 失敗時手動測試 Ollama 的提取效果：

```python
from core.enrichment.ollama_client import OllamaClient

async def test_ai_extraction():
    html_content = "<html>...頁面內容...</html>"
    client = OllamaClient()
    
    # 傳入網頁文本內容
    result = await client.extract_job_from_html(html_content)
    
    # 預期回傳包含 title, salary_min, address 等欄位的 dict
    print(result)

# 執行: uv run python test_ai.py
```

---

## 4. 資料庫查詢與存儲 (DB Operations)

使用 Pydantic Model 與 `Database` 類別進行操作：

```python
from core.infra import Database, JobPydantic, SourcePlatform

async def db_example():
    db = Database()
    
    # 1. 建立 Job 物件
    job = JobPydantic(
        platform=SourcePlatform.PLATFORM_104,
        source_id="TEST_001",
        title="Python Engineer",
        url="http://test.com",
        # ... 其他必要欄位 ...
    )
    
    # 2. 儲存 (會自動處理 Upsert)
    await db.save_job(job)
    
    # 3. 關閉連線池 (腳本結束前)
    await db.close_pool()
```

---

## 5. 常用的測試指令 (CLI Reference)

```bash
# 執行所有 SDD 規格測試 (最快)
uv run pytest test/sdd/

# 執行特定平台的單元測試
uv run pytest test/unit/adapters/test_adapter_logic.py -k "104"

# 偵錯模式 (不捕捉 stdout)
uv run pytest -s test/unit/test_jsonld.py
```

---

> [!IMPORTANT]
> 撰寫任何存取資料庫的腳本時，切記在 `try...finally` 區塊中調用 `await db.close_pool()`，以避免資料庫連線洩漏。
