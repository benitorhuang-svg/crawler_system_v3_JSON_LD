"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：skill_extractor.py
功能描述：技能提取器，負責從職缺描述中識別技術關鍵字，結合正則匹配與 AI 識別。
主要入口：由 core.services.crawl_service 或非同步任務調用。
"""
import re
import structlog
from typing import List, Tuple, Set, Optional, Any, Dict
from core.infra import JobSkillExtractedPydantic

logger = structlog.get_logger(__name__)

# 基礎技能詞庫 (SSOT)
SKILL_MAP: Dict[str, List[str]] = {
    "Programming": [
        "Python", "Java", "Javascript", "Node.js", "Ruby", "Golang", "Go", "C++", "C#", "PHP", 
        "Rust", "Swift", "Kotlin", "Typescript", "Dart", "SQL", "HTML", "CSS"
    ],
    "Framework": [
        "Django", "Flask", "Spring", "React", "Vue", "Angular", "Express", "Laravel", "Rails", 
        "FastAPI", "Next.js", "Nuxt.js", "Flutter", "Tailwind"
    ],
    "Tool/Infra": [
        "Docker", "Kubernetes", "K8s", "AWS", "GCP", "Azure", "Git", "Jenkins", "CI/CD", 
        "Redis", "Elasticsearch", "PostgreSQL", "MySQL", "MongoDB", "RabbitMQ", "Kafka"
    ],
    "AI/Data": [
        "PyTorch", "TensorFlow", "Scikit-Learn", "Numpy", "Pandas", "LLM", "OpenAI", 
        "NLP", "Computer Vision"
    ],
    "SoftSkill": [
        "Communication", "專案管理", "溝通", "Excel", "PPT", "Word"
    ]
}

class SkillExtractor:
    """
    技能提取服務，實現多階段識別策略。
    
    1. 靜態正則匹配：針對已知熱門技能進行高效過濾。
    2. AI AI 抽樣發現：利用 LLM 識別職位中隱藏的新技術。
    """
    def __init__(self) -> None:
        """初始化提取器，預編譯詞庫正則表達式。"""
        self.patterns: List[Tuple[str, str, re.Pattern]] = []
        for s_type, skills in SKILL_MAP.items():
            for skill in skills:
                # 使用字邊界確保匹配準確性
                pattern: re.Pattern = re.compile(rf'\b{re.escape(skill)}\b', re.IGNORECASE)
                self.patterns.append((skill, s_type, pattern))

    def extract(self, text: str, platform: str, job_id: str) -> List[JobSkillExtractedPydantic]:
        """
        執行基於正則的靜態提取。
        
        Args:
            text: 職缺描述。
            platform: 來源平台。
            job_id: 職缺來源 ID。
            
        Returns:
            List[JobSkillExtractedPydantic]: 識別出的技能物件清單。
        """
        if not text:
            return []
        
        found_lower: Set[str] = set()
        results: List[JobSkillExtractedPydantic] = []
        
        for skill_name, s_type, pattern in self.patterns:
            if pattern.search(text):
                low_name: str = skill_name.lower()
                if low_name not in found_lower:
                    results.append(JobSkillExtractedPydantic(
                        platform=platform,
                        job_source_id=job_id,
                        skill_name=skill_name,
                        skill_type=s_type,
                        confidence_score=1.0
                    ))
                    found_lower.add(low_name)
        
        return results

    async def discover_with_ollama(self, text: str, platform: str, job_id: str) -> List[JobSkillExtractedPydantic]:
        """
        呼叫本地 AI 模型進行探索性技能提取。
        
        Args:
            text: 職缺描述。
            platform: 來源平台。
            job_id: 職缺來源 ID。
            
        Returns:
            List[JobSkillExtractedPydantic]: AI 發現的新型技能。
        """
        # 延遲導入以避免循環依賴
        from .ollama_client import OllamaClient
        
        client: OllamaClient = OllamaClient()
        raw_skills: List[Dict[str, str]] = await client.extract_skills(text)
        
        results: List[JobSkillExtractedPydantic] = []
        for s in raw_skills:
            name: str = s.get("name", "Unknown")
            if not name or name == "Unknown":
                continue
                
            results.append(JobSkillExtractedPydantic(
                platform=platform,
                job_source_id=job_id,
                skill_name=name,
                skill_type=s.get("type", "General"),
                confidence_score=0.85
            ))
        return results

