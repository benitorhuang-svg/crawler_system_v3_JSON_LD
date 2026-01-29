"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：verify_fixes.py
功能描述：SDD 特修功能驗證工具，測試薪資解析優化、公司名稱正則回退以及 Schema 校驗器對未知平台的魯棒性。
主要入口：python test/scripts/verify_fixes.py
"""
import asyncio
import structlog
from typing import Dict, Any, Optional

from core.adapters.adapter_104 import Adapter104
from core.schemas.validator import SchemaValidator
from core.infra import SourcePlatform, configure_logging

# 初始化日誌
configure_logging()
logger = structlog.get_logger(__name__)

async def verify_fixes() -> None:
    """
    執行系統關鍵修復點的單元驗證。
    
    驗證項目：
    1. 薪資異常字串 (如 "high") 的清洗。
    2. 薪資格式化 (千分位逗號移除)。
    3. 公司名稱提取之 Regex 回退機制。
    4. Validator 對 unknown 平台的容錯性。
    """
    validator = SchemaValidator()
    adapter = Adapter104()
    
    print("\n--- [SDD] 修復點功能驗證啟動 ---")
    
    # 1. 測試薪資異常清洗 ("high" -> None)
    salary_ld: Dict[str, Any] = {"baseSalary": {"value": {"minValue": "high", "unitText": "MONTH"}}}
    parsed_salary = adapter.get_salary(salary_ld)
    print(f" [+] 薪資清洗 (high): {parsed_salary['min']} (預期：None)")
    
    # 2. 測試薪資格式化 ("50,000" -> 50000)
    salary_ld_2: Dict[str, Any] = {"baseSalary": {"value": {"minValue": "50,000", "unitText": "MONTH"}}}
    parsed_salary_2 = adapter.get_salary(salary_ld_2)
    print(f" [+] 薪資格式化 (50,000): {parsed_salary_2['min']} (預期：50000)")

    # 3. 測試公司名稱正則回退 (Fallback via Title)
    company_ld: Dict[str, Any] = {
        "@type": "JobPosting",
        "title": "Software Engineer ｜ Awesome Comp",
        "hiringOrganization": {"@type": "Organization"}
    }
    comp_name = adapter.get_company_name(company_ld)
    print(f" [+] 公司名稱回退提取：{comp_name} (預期：Awesome Comp)")

    # 4. 驗證 platform_unknown 的校驗容錯
    job_data: Dict[str, Any] = {
        "platform": "platform_unknown",
        "url": "https://example.com/job",
        "title": "Unknown Job"
    }
    # validate_job 預期會回傳 True (若必要欄位皆備) 或 False (若 JSON-LD 指令無效)
    is_valid = await validator.validate_job(job_data)
    print(f" [+] 未知平台驗證結果：{is_valid} (預期：True)")
    
    print("\n--- [SDD] 修復點驗證完畢 ---")

if __name__ == "__main__":
    try:
        asyncio.run(verify_fixes())
    except KeyboardInterrupt:
        pass
