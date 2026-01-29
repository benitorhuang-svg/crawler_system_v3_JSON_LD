#!/usr/bin/env python3
"""
修復腳本：針對 1111 平台 source_id=71694463 的反幻覺錯誤
該公司實際上「員工人數 暫不公開」，但數據庫中錯誤地存儲了「5」
"""
import asyncio
import sys
import os

sys.path.insert(0, os.getcwd())

from core.infra.database import Database
import structlog

logger = structlog.get_logger(__name__)

async def fix_1111_employee_count():
    """修正 1111 平台的員工數反幻覺錯誤"""
    db = Database()
    
    try:
        # 查詢當前數據
        print("=" * 60)
        print("DIAGNOSE: 查詢當前數據")
        print("=" * 60)
        
        async with db.safe_cursor() as cursor:
            await cursor.execute("""
                SELECT source_id, platform, name, employee_count, address, data_source_layer, updated_at 
                FROM tb_companies 
                WHERE source_id = '71694463' AND platform LIKE '%1111%'
            """)
            result = await cursor.fetchone()
            
            if result:
                source_id, platform, name, employee_count, address, data_source_layer, updated_at = result
                print(f"✓ 找到記錄：")
                print(f"  Platform: {platform}")
                print(f"  Source ID: {source_id}")
                print(f"  Name: {name}")
                print(f"  Employee Count (Current): {employee_count}")
                print(f"  Address: {address}")
                print(f"  Data Source Layer: {data_source_layer}")
                print(f"  Updated At: {updated_at}")
                
                # 修正
                print("\n" + "=" * 60)
                print("CORRECTION: 修正 employee_count = NULL")
                print("=" * 60)
                
                # 根據 SDD 規範 2.3.1：寧可空白，不可錯誤
                # 該公司在 1111 網站上明確標註「員工人數 暫不公開」
                # 因此應設為 NULL 而非數字值
                
                await cursor.execute("""
                    UPDATE tb_companies 
                    SET employee_count = NULL, updated_at = NOW() 
                    WHERE source_id = '71694463' AND platform LIKE '%1111%'
                """)
                
                # 驗證修正
                print("\nVERIFY: 重新查詢驗證修正結果")
                print("-" * 60)
                
                await cursor.execute("""
                    SELECT source_id, platform, name, employee_count, updated_at 
                    FROM tb_companies 
                    WHERE source_id = '71694463' AND platform LIKE '%1111%'
                """)
                
                updated_result = await cursor.fetchone()
                if updated_result:
                    src_id, plat, comp_name, new_emp_count, new_updated_at = updated_result
                    print(f"✓ 修正成功！")
                    print(f"  Source ID: {src_id}")
                    print(f"  Name: {comp_name}")
                    print(f"  Employee Count (New): {new_emp_count}")
                    print(f"  Updated At: {new_updated_at}")
                    
                    if new_emp_count is None:
                        print("\n✅ 驗證通過：employee_count 已正確設為 NULL")
                    else:
                        print(f"\n❌ 驗證失敗：employee_count 仍為 {new_emp_count}")
                else:
                    print("❌ 查詢不到修正後的記錄")
            else:
                print("❌ 查詢不到該記錄，請檢查 source_id 或 platform 是否正確")
                print("\n執行診斷查詢...")
                await cursor.execute("""
                    SELECT platform, source_id, name, employee_count 
                    FROM tb_companies 
                    WHERE source_id LIKE '%71694463%'
                """)
                rows = await cursor.fetchall()
                if rows:
                    print(f"✓ 找到 {len(rows)} 條相關記錄：")
                    for row in rows:
                        print(f"  - {row}")
                else:
                    print("✗ 未找到任何相關記錄")
                    
    except Exception as e:
        logger.error("fix_script_error", error=str(e))
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await db.close_pool()
        print("\n" + "=" * 60)
        print("修復完成")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(fix_1111_employee_count())
