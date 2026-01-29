"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：verify_trigger_samples.py
功能描述：任務發送校驗工具，手動向 Celery/RabbitMQ 發送跨平台的職缺類別探索任務，用於端對端整合測試。
主要入口：python test/scripts/verify_trigger_samples.py
"""
from typing import List, Tuple
from core.celery_app import app
from core.infra import SourcePlatform

# 定義要觸發的測試樣本：(平台枚舉值, 類別 ID, Celery 任務路徑)
# 注意：任務路徑應與 core/celery_app.py 中的 task_routes 或是核心註冊路徑一致
samples: List[Tuple[str, str, str]] = [
    (SourcePlatform.PLATFORM_104.value, '2001001001', 'core.tasks.discover_category.104'),
    (SourcePlatform.PLATFORM_1111.value, '100101', 'core.tasks.discover_category.1111'),
    (SourcePlatform.PLATFORM_CAKERESUME.value, 'bio-medical_aide', 'core.tasks.discover_category.cakeresume'),
    (SourcePlatform.PLATFORM_YES123.value, '2_1001_0001_0000', 'core.tasks.discover_category.yes123'),
    (SourcePlatform.PLATFORM_YOURATOR.value, '1', 'core.tasks.discover_category.yourator'),
]

def trigger_samples() -> None:
    """
    發送一系列樣本任務至 Celery 代理程式。
    """
    print("\n🚀 正在向 Celery / RabbitMQ 發送樣本探索任務...")
    
    for platform, cat_id, task_name in samples:
        print(f" [+] 平台：{platform:<20} | 類別 ID：{cat_id:<15} | 任務：{task_name}")
        # 發送非同步任務，限制最大抓取數為 10 筆以進行小規模驗證
        app.send_task(task_name, args=[platform, cat_id, 10]) 

    print("\n✅ 所有測試任務已成功發送至隊列。")

if __name__ == "__main__":
    trigger_samples()
