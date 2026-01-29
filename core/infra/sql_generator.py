"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：sql_generator.py
功能描述：SQL 生成工具，負責將 Pydantic 模型對映為 MySQL 建表及插入語句。
主要入口：由 Database 基礎設施模組調用，確保 Schema 與資料庫同步。
"""
import enum
import json
from typing import Type, Any, Dict, List, Optional
from pydantic import BaseModel
from pydantic.fields import FieldInfo

class SQLGenerator:
    """
    SQL 語法自動生成器，實作「規格即原始碼 (SDD)」概念。
    
    將 Pydantic 模型定義視為唯一真理來源 (SSOT)，動態產生 MySQL DDL 與 DML。
    """

    DEFAULT_VARCHAR_LEN: int = 255
    
    # 欄位名稱對映至特定 SQL 類型的覆寫配置
    TYPE_OVERRIDES: Dict[str, str] = {
        "url": "TEXT",
        "job_url": "TEXT",
        "company_url": "TEXT",
        "company_web": "TEXT",
        "description": "TEXT",
        "address": "TEXT",
        "skills": "TEXT",
        "raw_json": "JSON",
        "platform": "VARCHAR(50)",
        "salary_currency": "VARCHAR(10)",
        "salary_type": "VARCHAR(20)",
        "job_type": "VARCHAR(50)",
        "industry": "VARCHAR(100)",
        "capital": "VARCHAR(100)",
        "employee_count": "VARCHAR(100)",
        "layer_3_id": "VARCHAR(100)",
        "layer_3_name": "VARCHAR(100)",
        "category_id": "VARCHAR(100)",
        "job_source_id": "VARCHAR(100)",
        "source_id": "VARCHAR(100)",
        "company_source_id": "VARCHAR(100)",
        "education_text": "VARCHAR(100)",
        "work_hours": "VARCHAR(100)",
        "last_error": "TEXT",
        "posted_at": "DATETIME",
        "valid_through": "DATETIME",
        "updated_at": "DATETIME",
        "created_at": "DATETIME",
        "layer_category_name": "VARCHAR(100)",
    }

    @staticmethod
    def _get_mysql_type(field_name: str, python_type: Any, field_info: FieldInfo) -> str:
        """根據 Python 型別與欄位語義決定 MySQL 物理儲存型別。"""
        
        # 1. 檢查優先覆寫表
        if field_name in SQLGenerator.TYPE_OVERRIDES:
            return SQLGenerator.TYPE_OVERRIDES[field_name]

        # 2. 處理 Enum 列舉型別
        if isinstance(python_type, type) and issubclass(python_type, enum.Enum):
            options: List[str] = [f"'{e.value}'" for e in python_type]
            return f"ENUM({', '.join(options)})"

        # 3. 處理基礎型別對映
        type_str: str = str(python_type).lower()
        
        if "int" in type_str:
            return "INT"
        if "float" in type_str:
            return "DOUBLE"
        if "datetime" in type_str:
            return "DATETIME"
        if "date" in type_str:
            return "DATE"
        if "bool" in type_str:
            return "BOOLEAN"
        
        # 預設回退至 VARCHAR
        return f"VARCHAR({SQLGenerator.DEFAULT_VARCHAR_LEN})"

    @staticmethod
    def generate_create_table_sql(
        model: Type[BaseModel], 
        table_name: str, 
        table_comment: str, 
        primary_key: str = "id", 
        extra_constraints: Optional[List[str]] = None
    ) -> str:
        """
        生成 CREATE TABLE IF NOT EXISTS 語句。
        """
        columns: List[str] = []
        fks: List[str] = []
        
        # 若模型未定義指定的主鍵，則自動注入自增 ID
        if primary_key not in model.model_fields:
            columns.append(f"    {primary_key} INT AUTO_INCREMENT PRIMARY KEY COMMENT '系統自增主鍵'")

        for name, field in model.model_fields.items():
            mysql_type: str = SQLGenerator._get_mysql_type(name, field.annotation, field)
            
            # 判斷是否允許 NULL
            is_nullable: bool = not field.is_required() or (field.default is None and field.default is not ...)
            null_clause: str = "DEFAULT NULL" if is_nullable else "NOT NULL"
            
            # 提取 Pydantic 描述作為 SQL 註釋
            comment: str = field.description or ""
            comment_clause: str = f"COMMENT '{comment}'" if comment else ""
            
            # 定時戳記欄位特殊處理
            if "DATETIME" in mysql_type and "updated_at" in name:
                null_clause = "DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
            elif "DATETIME" in mysql_type and "created_at" in name:
                null_clause = "DEFAULT CURRENT_TIMESTAMP"
                
            columns.append(f"    {name} {mysql_type} {null_clause} {comment_clause}")

            # 提取 外鍵相關資訊 (用於 phpMyAdmin 點擊跳轉)
            if field.json_schema_extra and "fk" in field.json_schema_extra:
                fk_spec = field.json_schema_extra["fk"] # 格式: "table_name(column_name)"
                fks.append(f"    FOREIGN KEY ({name}) REFERENCES {fk_spec}")

        # 附加外鍵約束
        if fks:
            columns.extend(fks)

        # 附加額外約束條件 (如 UNIQUE KEY)
        if extra_constraints:
            for constraint in extra_constraints:
                columns.append(f"    {constraint}")
                
        body: str = ",\n".join(columns)
        return (
            f"CREATE TABLE IF NOT EXISTS {table_name} (\n"
            f"{body}\n"
            f") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='{table_comment}';"
        )

    @staticmethod
    def get_column_names(model: Type[BaseModel]) -> List[str]:
        """獲取模型中定義的欄位名稱列表。"""
        return list(model.model_fields.keys())

    @staticmethod
    def to_sql_params(model_instance: BaseModel, exclude_cols: Optional[List[str]] = None) -> List[Any]:
        """將 Pydantic 實例數據轉換為 SQL 參數列表，自動序列化複雜物件。"""
        params: List[Any] = []
        for name, _ in model_instance.model_fields.items():
            if exclude_cols and name in exclude_cols:
                continue
            val: Any = getattr(model_instance, name)
            if isinstance(val, enum.Enum):
                params.append(val.value)
            elif isinstance(val, (dict, list)):
                params.append(json.dumps(val, ensure_ascii=False))
            else:
                params.append(val)
        return params

    @staticmethod
    def generate_upsert_sql(model: Type[BaseModel], table_name: str, unique_keys: List[str]) -> str:
        """
        生成 INSERT ... ON DUPLICATE KEY UPDATE 語句 (相容 MySQL 8.0+ 語法)。
        """
        # 排除由資料庫自動管理的系統欄位 (SSD Sec 11)
        insert_cols: List[str] = [c for c in SQLGenerator.get_column_names(model) if c not in ("updated_at", "created_at")]
        placeholders: str = ", ".join(["%s"] * len(insert_cols))
        col_str: str = ", ".join(insert_cols)
        
        cols = SQLGenerator.get_column_names(model) # 原始模型欄位用於更新檢查
        
        # 過濾不應在更新時變動的欄位 (主鍵與唯一鍵)
        update_cols: List[str] = [c for c in cols if c not in unique_keys and c != "idx" and c != "updated_at" and c != "created_at"]
        
        # 決定哪些欄位需要 IFNULL 保護 (避免 NULL 覆蓋已有數據)
        # 對於資本額與員工人數，我們允許覆蓋以清除雜訊
        ifnull_cols = {"description", "company_web", "company_url"}
        
        clauses = []
        for c in update_cols:
            if c in ifnull_cols:
                clauses.append(f"{table_name}.{c} = IFNULL(new_values.{c}, {table_name}.{c})")
            else:
                clauses.append(f"{table_name}.{c} = new_values.{c}")
        
        update_clause: str = ", ".join(clauses)
        
        # 自動處理更新時間戳記
        if "updated_at" in cols:
            update_clause += f", {table_name}.updated_at = CURRENT_TIMESTAMP"
            
        sql: str = (
            f"INSERT INTO {table_name} ({col_str}) VALUES ({placeholders}) "
            f"AS new_values ON DUPLICATE KEY UPDATE {update_clause};"
        )
        return sql

