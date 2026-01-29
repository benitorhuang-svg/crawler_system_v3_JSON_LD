
import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

def reset_db():
    db_user = os.getenv("DB_USER", "root")
    db_password = os.getenv("DB_PASSWORD", "root")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "3306")
    db_name = os.getenv("DB_NAME", "crawler_db")
    
    db_url = f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    engine = create_engine(db_url)

    try:
        with engine.connect() as conn:
            print("Disabling foreign keys...")
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            
            tables = ["tb_jobs", "tb_companies", "tb_job_locations"]
            for t in tables:
                print(f"Truncating {t}...")
                conn.execute(text(f"TRUNCATE TABLE {t}"))
                
            print("Enabling foreign keys...")
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
            conn.commit()
    except Exception as e:
        if "1049" in str(e): # Unknown database
             print(f"Database {db_name} does not exist. Skipping truncation.")
        else:
             raise e
    
    print("Database reset complete.")

if __name__ == "__main__":
    reset_db()
