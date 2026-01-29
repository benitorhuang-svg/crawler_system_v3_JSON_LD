"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：test_adversarial.py
功能描述：對抗性測試，驗證驗證器是否能正確攔截由 AI 生成的合規但具備破壞性的樣本。
主要入口：pytest test/unit/test_adversarial.py
"""
import pytest
import json
from pathlib import Path
from core.schemas.validator import SchemaValidator

@pytest.mark.asyncio
async def test_adversarial_samples_validation() -> None:
    """
    驗證對抗性樣本應被系統正確拒絕。
    確保契約穩定性，防止 AI 生成的異常數據污染資料庫。
    """
    validator = SchemaValidator()
    # 導向中央測試樣本目錄
    root_dir = Path(__file__).parents[2]
    adv_dir = root_dir / "test" / "fixtures" / "data" / "adversarial"
    
    if not adv_dir.exists():
        pytest.skip(f"對抗性樣本目錄 {adv_dir} 不存在。")

    samples = list(adv_dir.glob("adv_*.json"))
    if not samples:
        pytest.skip("未發現對抗性樣本。")

    for sample_path in samples:
        print(f"\n測試對抗性樣本: {sample_path.name}")
        with open(sample_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # 對抗性樣本預期會驗證失敗
        is_valid = await validator._do_validate(data, validator.job_schema, "JobAdversarial")
        assert is_valid is False, f"對抗性樣本 {sample_path.name} 意外通過了驗證！"
        print(f" [+] 已正確拒絕: {sample_path.name}")

if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__]))
