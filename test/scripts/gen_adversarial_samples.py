"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：gen_adversarial_samples.py
功能描述：對抗性樣本生成器，利用 Ollama 生成刻意違反 Schema 規約的 HTML/JSON-LD 樣本，用於魯棒性測試。
主要入口：python test/scripts/gen_adversarial_samples.py
"""
import asyncio
import json
import httpx
import structlog
from pathlib import Path
from typing import List, Dict, Any

from core.enrichment.ollama_client import OllamaClient

# 初始化日誌
logger = structlog.get_logger(__name__)

async def generate_adversarial_samples() -> None:
    """
    執行對抗性樣本生成任務。
    
    流程：
    1. 讀取標準 Job Schema 內容。
    2. 定義各類型的異常導向 (Adversarial Types)。
    3. 請求本地 LLM (Ollama) 生成對應之錯誤資料格式。
    4. 將生成的樣本持久化至 test/data/adversarial 目錄。
    """
    base_dir: Path = Path(__file__).parent.parent
    schema_path: Path = base_dir.parent / "core" / "schemas" / "job_schema.json"
    output_dir: Path = base_dir / "data" / "adversarial"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not schema_path.exists():
        logger.error("schema_not_found", path=str(schema_path))
        return

    with open(schema_path, "r", encoding="utf-8") as f:
        schema_text: str = f.read()

    client: OllamaClient = OllamaClient()
    
    # 定義要測試的錯誤場景
    adversarial_types: List[Dict[str, str]] = [
        {"type": "missing_required", "desc": "缺少必要的 'title' 與 'url' 欄位"},
        {"type": "invalid_enum", "desc": "不正確的 'platform' 枚舉值 (例如 'platform_fake_site')"},
        {"type": "type_mismatch", "desc": "'salary_min' 欄位型別錯誤 (應為數字卻給予長字串)"}
    ]

    print(f"\n--- [SDD] 對抗性樣本生成啟動 (模型: {client.model}) ---")

    for adv in adversarial_types:
        prompt: str = f"""
        Based on this JSON Schema:
        {schema_text}
        
        Generate a 'JobPosting' dataset in JSON-LD format that is DELIBERATELY INVALID.
        Specifically, make it fail because it is {adv['desc']}.
        
        Return ONLY the JSON-LD object.
        """
        
        print(f" [+] 正在生成場景：{adv['type']}...")
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as http_client:
                resp: httpx.Response = await http_client.post(
                    f"{client.base_url}/generate",
                    json={
                        "model": client.model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json"
                    }
                )
                resp.raise_for_status()
                data: Dict[str, Any] = resp.json()
                content: str = data.get("response", "{}")
                
                # 儲存至對抗性樣本目錄
                filename: str = f"adv_{adv['type']}.json"
                save_path: Path = output_dir / filename
                
                # 重新解析並格式化 JSON 以確保正確性
                sample_data: Any = json.loads(content)
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(sample_data, f, indent=2, ensure_ascii=False)
                
                print(f"     -> 成功儲存至：{save_path.name}")
        except Exception as e:
            logger.error("adversarial_gen_failed", type=adv['type'], error=str(e))

    print("\n--- [SDD] 對抗性樣本生成任務完成 ---")

if __name__ == "__main__":
    try:
        asyncio.run(generate_adversarial_samples())
    except KeyboardInterrupt:
        pass
