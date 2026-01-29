
import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.getcwd())
load_dotenv()

def inspect_companies():
    db_user = os.getenv("DB_USER", "root")
    db_password = os.getenv("DB_PASSWORD", "root")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "3306")
    db_name = os.getenv("DB_NAME", "crawler_db")
    
    db_url = f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    engine = create_engine(db_url)

    with engine.connect() as conn:
        print("--- Testing Low Capital (< 100,000) ---")
        query = text("""
            SELECT platform, source_id, name, capital, address 
            FROM tb_companies 
            WHERE capital REGEXP '^[0-9]+$' AND CAST(capital AS UNSIGNED) < 100000
        """)
        result = conn.execute(query)
        for row in result:
            print(f"Platform: {row.platform}, ID: {row.source_id}, Name: {row.name}, Capital: {row.capital}")

        print("\n--- Testing Non-Numeric Capital (e.g., -private-equity) ---")
        query = text("""
            SELECT platform, source_id, name, capital 
            FROM tb_companies 
            WHERE capital IS NOT NULL AND capital NOT REGEXP '^[0-9]+$' AND capital != ''
        """)
        result = conn.execute(query)
        for row in result:
            print(f"Platform: {row.platform}, ID: {row.source_id}, Name: {row.name}, Capital: {row.capital}")

        print("\n--- Testing Bad Description (JSON or NULL) ---")
        query = text("""
            SELECT platform, source_id, name, description 
            FROM tb_companies 
            WHERE description IS NULL OR description LIKE '%{%' 
            LIMIT 5
        """)
        result = conn.execute(query)
        for row in result:
            desc_preview = (row.description[:50] + '...') if row.description else "NULL"
            print(f"Platform: {row.platform}, ID: {row.source_id}, Name: {row.name}, Desc: {desc_preview}")

if __name__ == "__main__":
    inspect_companies()
