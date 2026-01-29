import asyncio
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.getcwd())

from core.infra.database import Database

async def run_checks():
    print("Initializing Database...")
    db = Database()
    try:
        async with db.safe_cursor() as cursor:
            print("--- CHECK A: Lat/Lon Completeness ---")
            await cursor.execute("SELECT count(*) FROM tb_job_locations WHERE latitude IS NULL OR longitude IS NULL")
            res_a = await cursor.fetchone()
            count_a = res_a[0]
            print(f"Null Lat/Lon Count: {count_a}")
            if count_a > 0:
                print("FAIL: Found null coordinates.")
            else:
                print("PASS")

            print("\n--- CHECK B: Address Quality (tb_jobs & tb_companies) ---")
            import re
            # Regex to find garbage: no="...", { or }, or ", or :, or [
            # Also pure digits
            garbage_pattern = re.compile(r'no="|{|}|"|:|\[')
            digit_pattern = re.compile(r'^\d+$')

            async def check_table_addresses(table_name):
                print(f"Checking {table_name}...")
                await cursor.execute(f"SELECT source_id, address FROM {table_name} WHERE address IS NOT NULL")
                rows = await cursor.fetchall()
                bad_count = 0
                examples = []
                for source_id, address in rows:
                    if garbage_pattern.search(address) or digit_pattern.match(address):
                        bad_count += 1
                        if len(examples) < 5:
                            examples.append((source_id, address))
                return bad_count, examples

            count_b1, examples_b1 = await check_table_addresses("tb_jobs")
            print(f"Bad Address Count (tb_jobs): {count_b1}")
            
            count_b2, examples_b2 = await check_table_addresses("tb_companies")
            print(f"Bad Address Count (tb_companies): {count_b2}")

            if count_b1 > 0 or count_b2 > 0:
                print("FAIL: Found bad addresses.")
                if examples_b1:
                    print("  tb_jobs examples:")
                    for sid, addr in examples_b1:
                        print(f"    - {sid}: {addr}")
                if examples_b2:
                    print("  tb_companies examples:")
                    for sid, addr in examples_b2:
                        print(f"    - {sid}: {addr}")
            else:
                print("PASS")

            print("\n--- CHECK C: Company Association ---")
            await cursor.execute("SELECT count(*) FROM tb_jobs WHERE company_source_id IS NULL OR company_source_id = ''")
            res_c = await cursor.fetchone()
            count_c = res_c[0]
            print(f"Null Company ID Count: {count_c}")
            if count_c > 0:
                print("FAIL: Jobs without company ID found.")
            else:
                print("PASS")

            print("\n--- CHECK E: Company Details ---")
            # Capital < 100000
            await cursor.execute("SELECT platform, source_id, name, capital FROM tb_companies WHERE capital IS NOT NULL AND CAST(capital AS UNSIGNED) < 100000 AND capital REGEXP '^[0-9]+$'")
            res_e1 = await cursor.fetchall()
            print(f"Low Capital Count (Potential Hallucination): {len(res_e1)}")
            for row in res_e1:
                print(f"  - {row}")

            # Employees < 2
            await cursor.execute("SELECT platform, source_id, name, employee_count FROM tb_companies WHERE employee_count IS NOT NULL AND CAST(employee_count AS UNSIGNED) < 2 AND employee_count REGEXP '^[0-9]+$'")
            res_e2 = await cursor.fetchall()
            print(f"Low Employees Count (Potential Hallucination): {len(res_e2)}")
            for row in res_e2:
                print(f"  - {row}")

    except Exception as e:
        print(f"Error running checks: {e}")
    finally:
        await db.close_pool()

if __name__ == "__main__":
    asyncio.run(run_checks())
