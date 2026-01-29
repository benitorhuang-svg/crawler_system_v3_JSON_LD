"""
專案名稱：crawler_system_v3_JSON_LD
測試模組：test_salary.py
描述：針對 SalaryParser 進行各種極端薪資文本的解析驗證。
"""
import pytest
from core.utils.parsers import SalaryParser, SalaryType

def test_salary_parser_basic():
    # 測試基本數值提取
    res = SalaryParser.parse("月薪 40,000 - 50,000 元")
    assert res["min"] == 40000
    assert res["max"] == 50000
    assert res["type"] == SalaryType.MONTHLY

def test_salary_parser_wan():
    # 測試「萬」單位
    res = SalaryParser.parse("年薪 100萬 - 120 萬")
    assert res["min"] == 1000000
    assert res["max"] == 1200000
    assert res["type"] == SalaryType.YEARLY

def test_salary_parser_yi():
    # 測試「億」單位
    res = SalaryParser.parse("月薪 1.5 億")
    assert res["min"] == 150000000
    assert res["type"] == SalaryType.MONTHLY

def test_salary_parser_negotiable():
    # 測試面議
    res = SalaryParser.parse("面議")
    assert res["min"] is None
    assert res["text"] == "面議"

def test_salary_type_enum():
    # 驗證 SalaryType 枚舉是否正確導入
    assert SalaryType.MONTHLY == "月薪"
    assert SalaryType.YEARLY == "年薪"

if __name__ == "__main__":
    pytest.main([__file__])
