"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：benchmark_ollama.py
功能描述：AI 提取效能基準測試工具，用於對照 Ground Truth (L1) 評估 Ollama 模型的提取準確性與延遲。
主要入口：uv run python test/scripts/benchmark_ollama.py
"""
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
import structlog
from core.enrichment.ollama_client import OllamaClient

logger = structlog.get_logger(__name__)

class OllamaBenchmarker:
    """
    SDD 階段 4：AI 能力驗證與品質監控工具。
    
    透過批次處理標竿樣本，計算 Ollama 在實體提取任務中的各項指標（準確率、延遲）。
    此工具確保 AI 組件符合系統規格。
    """
    def __init__(self) -> None:
        """初始化測試環境，配置路徑與 Ollama 客戶端。"""
        self.client: OllamaClient = OllamaClient()
        self.base_dir: Path = Path(__file__).parent.parent.parent
        self.data_dir: Path = self.base_dir / "test" / "fixtures" / "data"
        self.results_dir: Path = self.base_dir / "test" / "unit" / "debug" / "benchmarks"
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def _calculate_score(self, truth: Dict[str, Any], extracted: Dict[str, Any]) -> Dict[str, float]:
        """
        計算單一提取結果與標準答案的匹配得分。
        """
        metrics: Dict[str, float] = {}
        fields: List[str] = ["title", "company_name", "salary_text", "salary_type"]
        
        for field in fields:
            t_val: str = str(truth.get(field, "")).strip().lower()
            e_val: str = str(extracted.get(field, "")).strip().lower()
            
            # 寬鬆匹配邏輯 (Substring 匹配)
            if t_val == e_val and t_val != "":
                metrics[field] = 1.0
            elif t_val in e_val and t_val != "":
                metrics[field] = 0.8
            elif t_val == "" and e_val == "":
                metrics[field] = 1.0
            else:
                metrics[field] = 0.0
                
        metrics["total"] = sum(metrics.values()) / len(fields)
        return metrics

    async def run_benchmark(self, limit: int = 20) -> None:
        """
        對指定數量的樣本執行循環提取測試。
        
        Args:
            limit (int): 最大測試樣本數。
        """
        print(f"\n🚀 Ollama 基準測試啟動 (模型: {self.client.model})")
        print(f"📁 數據來源: {self.data_dir}")
        
        # 1. 識別 JSON 格式的 Ground Truth 檔案
        samples: List[Path] = [p for p in self.data_dir.glob("*.json") if "metadata" not in p.name]
        if not samples:
            print("❌ 錯誤: 找不到測試樣本 (JSON)。")
            return

        total_metrics: Dict[str, float] = {"title": 0.0, "company_name": 0.0, "salary_text": 0.0, "salary_type": 0.0, "total": 0.0}
        count: int = 0

        for sample_path in samples[:limit]:
            with open(sample_path, "r", encoding="utf-8") as f:
                truth_data: Dict[str, Any] = json.load(f)
            
            # 尋找對應的 HTML 檔案
            html_path: Path = sample_path.with_suffix(".html")
            if not html_path.exists():
                continue

            with open(html_path, "r", encoding="utf-8") as f:
                html_content: str = f.read()

            print(f" [+] 評核中: {sample_path.name}")
            
            start_t: float = time.perf_counter()
            # 呼叫 AI 進行語義提取
            extracted: Dict[str, Any] = await self.client.extract_job_from_html(html_content)
            latency: float = time.perf_counter() - start_t

            scores: Dict[str, float] = self._calculate_score(truth_data, extracted)
            for k, v in scores.items():
                if k in total_metrics:
                    total_metrics[k] += v
            
            count += 1
            print(f"     ➔ 準確度: {scores['total']:.1%}, 耗時: {latency:.2f}s")

        if count > 0:
            avg_metrics: Dict[str, float] = {k: v / count for k, v in total_metrics.items()}
            print("\n📊 測試彙整報告")
            for k, v in avg_metrics.items():
                print(f" {k:15}: {v:.2%}")
            
            # 持久化報告
            ts: int = int(time.time())
            report: Dict[str, Any] = {
                "timestamp": ts,
                "model": self.client.model,
                "count": count,
                "metrics": avg_metrics
            }
            report_path: Path = self.results_dir / f"report_{ts}.json"
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            print(f"\n✅ 基準測試完成，報告已存至 {report_path}")
        else:
            print("⚠️ 找不到有效的 (JSON+HTML) 樣本對。")

if __name__ == "__main__":
    bench = OllamaBenchmarker()
    asyncio.run(bench.run_benchmark())
