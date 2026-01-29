"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：schemas.py
功能描述：系統單一真理來源 (SSOT) 規格模組，定義所有 Pydantic 數據模型、枚舉與資料驗證邏輯。
相關規格：[.rule/SDD_SDLC_SPEC.md](file:///home/soldier/crawler_system_v3_JSON_LD/.rule/SDD_SDLC_SPEC.md)
主要入口：由系統各層級 (Infra, Services, Adapters) 匯入使用。
"""
from __future__ import annotations
import enum
from datetime import date, datetime
from typing import Optional, List, Any
from pydantic import BaseModel, ConfigDict, Field

class SourcePlatform(str, enum.Enum):
    """資料來源平台枚舉，定義系統支援的所有徵才網站。"""
    PLATFORM_104 = "platform_104"
    PLATFORM_1111 = "platform_1111"
    PLATFORM_CAKERESUME = "platform_cakeresume"
    PLATFORM_YES123 = "platform_yes123"
    PLATFORM_YOURATOR = "platform_yourator"
    PLATFORM_UNKNOWN = "platform_unknown"

class SalaryType(str, enum.Enum):
    """薪資給付類型枚舉，對齊各平台的常見給付頻率。"""
    MONTHLY = "月薪"
    HOURLY = "時薪"
    YEARLY = "年薪"
    DAILY = "日薪"
    BY_CASE = "由案件決定"
    NEGOTIABLE = "面議"

# 1. 種子階段：分類資訊模型
class CategoryPydantic(BaseModel):
    """職缺分類數據模型，對應資料表 tb_categories。"""
    model_config = ConfigDict(from_attributes=True)
    platform: SourcePlatform = Field(description="平台來源")
    layer_1_id: Optional[str] = Field(default=None, description="第一層類別代碼 (例如：IT)")
    layer_1_name: Optional[str] = Field(default=None, description="第一層類別名稱")
    layer_2_id: Optional[str] = Field(default=None, description="第二層類別代碼 (例如：軟體開發)")
    layer_2_name: Optional[str] = Field(default=None, description="第二層類別名稱")
    layer_3_id: str = Field(description="第三層類別代碼 (各平台抓取之最小粒度 ID)")
    layer_3_name: str = Field(description="第三層類別名稱")
    # 斷點續爬
    updated_at: Optional[datetime] = Field(default=None, description="最後更新時間")

# 2. 發現階段：分類-職缺關聯模型
class JobCategoryJunctionPydantic(BaseModel):
    """職缺與分類之多對多關聯模型，對應資料表 tb_categories_jobs。"""
    model_config = ConfigDict(from_attributes=True)
    platform: SourcePlatform = Field(description="平台來源")
    category_id: str = Field(description="對應 tb_categories.layer_3_id", json_schema_extra={"fk": "tb_categories(layer_3_id)"})
    job_source_id: str = Field(description="對應 tb_jobs.source_id", json_schema_extra={"fk": "tb_jobs(source_id)"})
    job_url: str = Field(description="發現該職缺時使用的 URL")
    created_at: Optional[datetime] = Field(default=None, description="關聯建立時間")

# 3. 提取階段：公司資訊模型
class CompanyPydantic(BaseModel):
    """公司詳情數據模型，對應資料表 tb_companies。"""
    model_config = ConfigDict(from_attributes=True)
    platform: SourcePlatform = Field(description="平台來源")
    source_id: str = Field(description="平台內部公司唯一 ID")
    name: str = Field(description="公司官方名稱")
    company_url: Optional[str] = Field(default=None, description="公司於該平台的介紹頁 URL")
    company_web: Optional[str] = Field(default=None, description="公司官方網站連結")
    address: Optional[str] = Field(default=None, description="公司登記或辦公地址")
    capital: Optional[str] = Field(default=None, description="實收資本額字串")
    employee_count: Optional[str] = Field(default=None, description="員工人數規模")
    description: Optional[str] = Field(default=None, description="公司簡介與描述")
    data_source_layer: Optional[str] = Field(default="L1", description="數據來源層級 (L1: JSON-LD / L2: Other)")
    updated_at: Optional[datetime] = Field(default=None, description="最後更新時間")

# 4. 提取階段：職缺資訊模型
class JobPydantic(BaseModel):
    """職缺詳情數據模型 (SSOT)，對應資料表 tb_jobs。"""
    model_config = ConfigDict(from_attributes=True)
    platform: SourcePlatform = Field(description="平台來源")
    url: str = Field(description="標準化後的職缺原始 URL")
    source_id: Optional[str] = Field(default=None, description="平台內部職缺唯一 ID")
    company_source_id: Optional[str] = Field(default=None, description="對應 tb_companies.source_id", json_schema_extra={"fk": "tb_companies(source_id)"})
    title: Optional[str] = Field(default=None, description="職缺職稱")
    description: Optional[str] = Field(default=None, description="清洗過後的 HTML/Text 職缺內容")
    industry: Optional[str] = Field(default=None, description="產業分類")
    layer_category_name: Optional[str] = Field(default=None, description="系統分類名稱 (層級 3)")
    job_type: Optional[str] = Field(default=None, description="僱用類型 (全職/兼職/實習)")
    work_hours: Optional[str] = Field(default=None, description="上班時段與時數")
    
    # 薪資欄位組
    salary_currency: Optional[str] = Field(default="TWD", description="薪資貨幣代碼")
    salary_type: Optional[SalaryType] = Field(default=None, description="給付週期")
    salary_text: Optional[str] = Field(default=None, description="原始薪資描述文案")
    salary_min: Optional[int] = Field(default=None, description="數值化最低薪資")
    salary_max: Optional[int] = Field(default=None, description="數值化最高薪資")

    # 地點欄位組
    address_country: Optional[str] = Field(default="TW", description="工作國家代碼")
    address: Optional[str] = Field(default=None, description="完整工作地址")
    region: Optional[str] = Field(default=None, description="一級行政區 (縣市)")
    district: Optional[str] = Field(default=None, description="二級行政區 (鄉鎮市區)")

    # 應徵要求與資格
    experience_min_years: Optional[int] = Field(default=0, description="最低需求年資 (0 表示不拘)")
    education_text: Optional[str] = Field(default="不拘", description="學歷要求描述")

    # 系統元數據
    posted_at: Optional[date] = Field(default=None, description="平台發布日期")
    valid_through: Optional[date] = Field(default=None, description="應徵截止日期")
    raw_json: Optional[str] = Field(default=None, description="抓取到的原始資料內容 (JSON 字串)")
    data_source_layer: Optional[str] = Field(default="L1", description="數據解析來源層級")
    updated_at: Optional[datetime] = Field(default=None, description="系統最後更新時間")

# 5. 監控與運核模型
class PlatformHealthPydantic(BaseModel):
    """平台運行監控模型，對應資料表 tb_platform_health。"""
    model_config = ConfigDict(from_attributes=True)
    platform: SourcePlatform = Field(description="監控平台對象")
    total_requests: int = Field(default=0, description="累計總請求次數")
    success_requests: int = Field(default=0, description="HTTP 成功次數")
    failed_requests: int = Field(default=0, description="HTTP 失敗次數")
    extraction_success: int = Field(default=0, description="欄位解析成功次數")
    extraction_failure: int = Field(default=0, description="欄位解析失敗次數")
    avg_latency_ms: int = Field(default=0, description="平均反應延遲 (ms)")
    last_error: Optional[str] = Field(None, description="最後一次遭遇之錯誤摘要")
    updated_at: Optional[datetime] = Field(default_factory=datetime.now, description="紀錄更新時間")

class JobLocationPydantic(BaseModel):
    """職缺地理座標模型，對應資料表 tb_job_locations。"""
    platform: str = Field(..., description="平台枚舉值字串")
    job_source_id: str = Field(..., description="職缺來源唯一 ID", json_schema_extra={"fk": "tb_jobs(source_id)"})
    latitude: Optional[float] = Field(None, description="WGS84 緯度")
    longitude: Optional[float] = Field(None, description="WGS84 經度")
    formatted_address: Optional[str] = Field(None, description="地理編碼標準化後地址")
    provider: Optional[str] = Field("OSM", description="地理資訊提供者 (NATIVE/OSM/GOOGLE)")
    updated_at: Optional[datetime] = Field(default_factory=datetime.now)

class JobSkillExtractedPydantic(BaseModel):
    """職缺技能提取模型，對應資料表 tb_job_skills_extracted。"""
    platform: str = Field(..., description="平台枚舉值字串")
    job_source_id: str = Field(..., description="職缺來源唯一 ID", json_schema_extra={"fk": "tb_jobs(source_id)"})
    skill_name: str = Field(..., description="提取出的技能/關鍵字名稱")
    skill_type: Optional[str] = Field(None, description="技能類型標籤")
    confidence_score: Optional[float] = Field(1.0, description="提取置信度評分 (0.0-1.0)")
    updated_at: Optional[datetime] = Field(default_factory=datetime.now)

# 模型定義結束
