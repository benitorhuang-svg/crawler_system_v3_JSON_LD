"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：ollama_client.py
功能描述：Ollama API 用戶端，封裝與本地大語言模型的通訊邏輯，支援技能提取與 AI 自癒提取。
主要入口：由 core.enrichment 模組或 CrawlService 調用。
"""
import httpx
import json
import structlog
from pathlib import Path
from typing import List, Dict, Any, Optional
from core.infra.config import settings

logger = structlog.get_logger(__name__)

class OllamaClient:
    """
    Ollama 本地 AI 服務客戶端。
    
    提供結構化資訊提取功能，包含：
    1. 技術技能識別 (Entity Extraction)。
    2. HTML 語義分析與自癒 (Semantic Self-Healing)。
    """

    _client: Optional[httpx.AsyncClient] = None
    _breaker = None

    def __init__(self) -> None:
        """初始化用戶端，從中央配置讀取。"""
        self.base_url: str = settings.OLLAMA_URL.rstrip('/')
        self.model: str = settings.OLLAMA_MODEL
        if OllamaClient._breaker is None:
            from core.infra.circuit_breaker import CircuitManager
            OllamaClient._breaker = CircuitManager.get_breaker("ollama", failure_threshold=5, recovery_timeout=60)

    async def _get_client(self) -> httpx.AsyncClient:
        """懶加載共用 HTTP 客戶端。"""
        if OllamaClient._client is None or OllamaClient._client.is_closed:
            OllamaClient._client = httpx.AsyncClient(timeout=settings.TIMEOUT_OLLAMA)
        return OllamaClient._client

    async def extract_skills(self, text: str) -> List[Dict[str, str]]:
        """
        從文本中提取技術關鍵字。
        """
        if not text or len(text.strip()) < 10:
            return []

        prompt: str = f"""
        Task: Extract technical skills from the Chinese job description.
        Rules:
        - Return ONLY a valid JSON array.
        - Fields: "name" (string), "type" (string).
        - Type category: Programming, Framework, Database, Tool, Cloud, Other.
        
        Job Description:
        {text}
        
        JSON Result:
        """
        
        async def _do_call():
            client = await self._get_client()
            resp = await client.post(
                f"{self.base_url}/api/generate", # 修正 API 路徑
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.2}
                }
            )
            resp.raise_for_status()
            return resp.json()

        try:
            data = await self._breaker.call(_do_call)
            content: str = data.get("response", "[]")
            content = content.replace("```json", "").replace("```", "").strip()
            return json.loads(content)
        except Exception as e:
            logger.error("ollama_skill_extraction_failed", error=str(e))
            return []

    async def extract_job_from_html(self, html_text: str) -> Dict[str, Any]:
        """
        利用 AI 從 HTML 文本中進行備份提取（當結構化解析失敗時）。
        """
        if not html_text:
            return {}

        context: str = self._get_few_shot_context()
        
        prompt: str = f"""
        Role: Expert Technical Job Classifier.
        Task: Extract job details from the provided text snippet.
        
        Constraints:
        1. Return ONLY a valid JSON object.
        2. Required fields: "title", "company_name", "salary_text", "salary_type".
        3. Allowed salary_type: "月薪", "時薪", "年薪", "日薪", "面議".
        
        {context}

        Data to analyze:
        {html_text[:3500]}
        
        JSON Result:
        """
        
        async def _do_call():
            client = await self._get_client()
            resp = await client.post(
                f"{self.base_url}/api/generate", # 修正 API 路徑
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.1}
                }
            )
            resp.raise_for_status()
            return resp.json()

        try:
            data = await self._breaker.call(_do_call)
            content: str = data.get("response", "{}")
            content = content.replace("```json", "").replace("```", "").strip()
            return json.loads(content)
        except Exception as e:
            logger.error("ollama_html_extraction_failed", error=str(e))
            return {}

    def _get_few_shot_context(self) -> str:
        """讀取基準樣本以提供 Few-shot 引導。"""
        try:
            # 定位至專案內部的測試樣本
            sample_path: Path = Path(__file__).parent.parent.parent / "test" / "unit" / "data" / "bench_sample.json"
            if not sample_path.exists():
                return ""
            
            with open(sample_path, "r", encoding="utf-8") as f:
                data: Any = json.load(f)
            
            return f"Sample Output Format:\n{json.dumps(data, ensure_ascii=False, indent=2)}"
        except Exception as e:
            logger.warning("ollama_few_shot_failed", error=str(e))
            return ""

