"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：bench_throttling.py
功能描述：頻率限制器 (Throttler) 效能基準測試與隔離性驗證。
主要入口：python test/scripts/bench_throttling.py
"""
import asyncio
import time
import structlog
from typing import Optional

from core.services.throttler import Throttler
from core.infra import configure_logging

# 初始化配置
configure_logging()
logger = structlog.get_logger(__name__)

async def test_platform_isolation() -> None:
    """
    驗證不同平台間的頻率限制是否相互隔離。
    
    流程：觸發平台 A 冷卻 -> 嘗試獲取 A 權杖 (預期等待) -> 同時獲取 B 權杖 (預期立刻獲得)。
    """
    throttler = Throttler()
    
    p1: str = "platform_104"
    p2: str = "platform_1111"
    
    print(f"\n--- 測試平台隔離性: {p1} vs {p2} ---")
    
    # 1. 觸發 P1 進入強制冷卻
    print(f"正在觸發 {p1} 之 10 秒硬性冷卻...")
    await throttler.trigger_cooling(p1, duration=10)
    
    # 2. 嘗試獲取 P1 槽位 (應超時或失敗)
    print(f"檢查 {p1} 狀態 (應在冷卻中)...")
    start: float = time.perf_counter()
    p1_ok: bool = await throttler.wait_for_slot(p1, timeout=2.0)
    print(f"{p1} 結果: {'OK' if p1_ok else '受限/冷卻中'} (耗時 {time.perf_counter()-start:.2f}s)")
    
    # 3. 嘗試獲取 P2 槽位 (應不受影響)
    print(f"檢查 {p2} 狀態 (應不受 cold down 影響)...")
    start = time.perf_counter()
    p2_ok: bool = await throttler.wait_for_slot(p2, rate=1.0, timeout=2.0)
    print(f"{p2} 結果: {'OK' if p2_ok else '受限'} (耗時 {time.perf_counter()-start:.2f}s)")

    if not p1_ok and p2_ok:
        print("\n✅ 驗證成功：平台間隔離正常，P1 的冷卻不影響 P2。")
    else:
        print("\n❌ 驗證失敗：隔離性不足。")

if __name__ == "__main__":
    try:
        asyncio.run(test_platform_isolation())
    except KeyboardInterrupt:
        pass
