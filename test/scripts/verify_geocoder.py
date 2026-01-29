"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：verify_geocoder.py
功能描述：地理編碼器性能驗證工具，測試地址清理、速率限制與快取效果。
主要入口：uv run python test/scripts/verify_geocoder.py
"""
import asyncio
import time
from typing import List, Tuple, Optional, Any
import structlog
from core.enrichment.geocoder import Geocoder
from core.infra.logging_config import configure_logging

# 初始化日誌
logger = structlog.get_logger(__name__)

async def test_geocoder_perf() -> None:
    """
    執行地理編碼器性能測試。
    """
    configure_logging()
    geocoder = Geocoder()
    
    test_addresses: List[str] = [
        "台灣台北市信義區信義路五段7號8樓",
        "中華民國新北市中和區員山路579號3棟3樓",
        "台北市大安區忠孝東路四段1號之1 (信義區公所旁)",
        "桃園市蘆竹區南崁路一段2號 10F-1",
        "新竹市東區光復路二段101號 [科學園區內]",
        "台北市中和區員山路579號 / 台北市信義區信義路五段7號 (多地址測試)"
    ]
    
    print(f"🚀 [第一階段] 測試地址清理與速率限制...")
    start_seq: float = time.perf_counter()
    for addr in test_addresses:
        clean: str = geocoder._clean_address(addr)
        print(f"  清理中：[{addr}] -> [{clean}]")
        lat, lon, disp = await geocoder.geocode(addr)
        print(f"  結果：{lat}, {lon} ({disp[:30] if disp else '無'})")
    end_seq: float = time.perf_counter()
    print(f"✅ 完成耗時：{end_seq - start_seq:.2f}s\n")

    print(f"🚀 [第二階段] 測試快取效果 (同時執行)...")
    # 使用相同的地址
    start_cache: float = time.perf_counter()
    tasks: List[Any] = [geocoder.geocode(addr) for addr in test_addresses]
    results: List[Tuple[Optional[float], Optional[float], Optional[str]]] = await asyncio.gather(*tasks)
    end_cache: float = time.perf_counter()
    print(f"✅ 快取測試：{end_cache - start_cache:.2f}s (預期小於 0.5s，因快取命中)")
    
    for i, (lat, lon, _) in enumerate(results):
        if lat:
            print(f"  快取命中 {i+1}：{lat}, {lon}")
        else:
            print(f"  快取命中 {i+1}：失敗 (API 問題或快取未命中)")

if __name__ == "__main__":
    asyncio.run(test_geocoder_perf())
