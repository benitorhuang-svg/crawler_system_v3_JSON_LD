"""
專案名稱：crawler_system_v3_JSON_LD
模組名稱：geocoder.py
功能描述：地理編碼器，提供地址到經緯度座標的轉換功能，整合 Redis 緩存與頻率限制。
主要入口：由 core.services.crawl_service 或非同步任務調用。
"""
import httpx
import structlog
import asyncio
import json
import re
from typing import Tuple, Optional, Any, Dict, List, Set
from core.infra import RedisClient

logger = structlog.get_logger(__name__)

class Geocoder:
    """
    地理編碼器服務。
    
    使用 OpenStreetMap (OSM) Nominatim API 將地址轉換為經緯度座標。
    具備以下特性：
    - Redis 緩存以減少重複請求。
    - 嚴格的全局併發控制與頻率限制（遵循 OSM 每秒 1 請求規範）。
    - 台灣地址自動標準化清洗，提升匹配成功率。
    """
    _client: Optional[httpx.AsyncClient] = None

    def __init__(self) -> None:
        """初始化地理編碼器，設置 API 地址與緩存過期時間。"""
        self.base_url: str = "https://nominatim.openstreetmap.org/search"
        self.headers: Dict[str, str] = {
            "User-Agent": "AntigravityJobCrawler/1.0 (contact: support@antigravity.ai)",
            "Referer": "https://github.com/benitorhuang-svg/crawler_system_v3_JSON_LD"
        }
        self.redis: Any = RedisClient().get_client()
        self.cache_ttl: int = 604800  # 緩存效期：7 天

    async def _get_client(self) -> httpx.AsyncClient:
        """取得或初始化異步 HTTP 客戶端。"""
        if Geocoder._client is None or Geocoder._client.is_closed:
            Geocoder._client = httpx.AsyncClient(headers=self.headers, timeout=12.0)
        return Geocoder._client

    def _clean_address(self, address: str) -> str:
        """
        將台灣地址標準化，以提高地理編碼的成功率。
        """
        if not address: return ""
        
        # 0. 將全形字元轉換為半形
        trans_map: Dict[int, int] = str.maketrans(
            '１２３４５６７８９０（）［］／、﹝﹞【】', 
            '1234567890()[]/,()[]'
        )
        address = address.translate(trans_map)
        
        # 1. 處理含有多個地址的情況，選取第一個
        parts: List[str] = re.split(r'[/,、]', address) 
        if len(parts) > 1:
            address = parts[0].strip()

        # 2. 移除台灣相關前綴
        address = re.sub(r'^(台灣|中華民國|臺灣|Taiwan|R\.O\.C|台灣省|臺灣省)', '', address).strip()
        address = address.lstrip(',， ')
        
        # 3. 移除括號及其內容
        address = re.sub(r'[\(\[].*?[\)\]]', '', address).strip()
        
        # 4. 剔除詳細樓層資訊
        patterns: List[str] = [
            r'\d+[樓Ff].*',
            r'B\d+.*',
            r'地下\d+樓.*',
            r'[第]?[A-Z0-9]+[室室].*',
            r'\d+棟.*',
            r'(?<=號)\s*[A-Z0-9].*' 
        ]
        
        for p in patterns:
            address = re.sub(p, '', address).strip()
            
        # 5. 修正重複的縣市名稱 (例如：台北市台北市)
        for city in ["台北市", "新北市", "桃園市", "台中市", "台南市", "高雄市", 
                     "基隆市", "新竹市", "嘉義市", "新竹縣", "苗栗縣", "彰化縣", 
                     "南投縣", "雲林縣", "嘉義縣", "屏東縣", "宜蘭縣", "花蓮縣", 
                     "台東縣", "澎湖縣", "金門縣", "連江縣"]:
            if address.startswith(city + city):
                address = address.replace(city + city, city, 1)

        # 6. 修正後綴殘留
        address = address.rstrip('- ').strip()
        
        return address

    async def geocode(self, address: str, city: Optional[str] = None, district: Optional[str] = None) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """
        將地址字串轉換為座標資訊，支援結構化回退。
        
        Returns:
            Tuple[Optional[float], Optional[float], Optional[str]]: (緯度, 經度, OSM 格式化地址)。
        """
        if not address:
            return None, None, None
        
        # 1. 地址標準化預處理
        clean_addr: str = self._clean_address(address)
        if not clean_addr:
            return None, None, None
            
        logger.debug("geocoding_attempt", original=address, cleaned=clean_addr)
        
        # 2. 檢查 Redis 緩存
        cache_key: str = f"geocoding:v3:{clean_addr}"
        if self.redis:
            try:
                cached: Optional[bytes] = self.redis.get(cache_key)
                if cached:
                    data: Dict[str, Any] = json.loads(cached)
                    return data.get("lat"), data.get("lon"), data.get("display_name")
            except Exception as e:
                logger.warning("geocoding_cache_error", error=str(e))

        try:
            # 3.1 優先嘗試完整清洗後的地址
            lat, lon, disp = await self._do_request(clean_addr)
            if lat: return lat, lon, disp
            
            # 3.1.5 回退策略: 嘗試移除門牌號碼，僅保留路名 (Street Level)
            # 針對 "台南市中西區環河街62號" -> "台南市中西區環河街"
            street_pattern = re.compile(r"(.*?[路街巷大道段])")
            match = street_pattern.search(clean_addr)
            if match:
                street_addr = match.group(1).strip()
                if street_addr and street_addr != clean_addr:
                    logger.debug("geocoding_fallback_street", original=clean_addr, fallback=street_addr)
                    lat, lon, disp = await self._do_request(street_addr)
                    if lat: return lat, lon, disp
            
            # 3.2 回退策略 1: 縣市 + 區域 (針對 Yourator 等地址不全平台)
            if city or district:
                fallback_addr = f"{city or ''}{district or ''}".strip()
                if fallback_addr and fallback_addr != clean_addr:
                    logger.debug("geocoding_fallback_city_district", addr=fallback_addr)
                    lat, lon, disp = await self._do_request(fallback_addr)
                    if lat: return lat, lon, disp
            
            # 3.3 回退策略 2: 僅縣市
            if city:
                logger.debug("geocoding_fallback_city", city=city)
                lat, lon, disp = await self._do_request(city)
                if lat: return lat, lon, disp

        except Exception as e:
            logger.error("geocoding_exception", address=clean_addr, error=str(e))
        finally:
            # 確保釋放锁之前至少間隔 1.1 秒
            await asyncio.sleep(1.1) 
            
        return None, None, None

    async def _do_request(self, query: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """執行底層 Nominatim 請求。"""
        if not query: return None, None, None
        
        # 3. 執行 API 請求（分散式 1 QPS 限制）
        throttle_key = "geocoding:throttle"
        while self.redis:
            if self.redis.set(throttle_key, "locked", ex=1, nx=True):
                break
            await asyncio.sleep(0.5)

        try:
            client: httpx.AsyncClient = await self._get_client()
            # 增加 Taiwan 標籤以提升精準度
            search_query = f"{query}, Taiwan" if "Taiwan" not in query else query
            params: Dict[str, Any] = {
                "q": search_query,
                "format": "json",
                "limit": 1,
                "addressdetails": 1
            }
            
            resp: httpx.Response = await client.get(self.base_url, params=params)
            
            if resp.status_code == 200:
                data: List[Dict[str, Any]] = resp.json()
                if data:
                    res: Dict[str, Any] = data[0]
                    lat: float = float(res["lat"])
                    lon: float = float(res["lon"])
                    display_name: str = res.get("display_name", "")
                    
                    # 4. 寫入快取 (使用 query 作為 Key)
                    cache_key: str = f"geocoding:v3:{query}"
                    if self.redis:
                        try:
                            self.redis.setex(
                                cache_key, 
                                self.cache_ttl, 
                                json.dumps({"lat": lat, "lon": lon, "display_name": display_name})
                            )
                        except Exception as e:
                            logger.warning("geocoding_cache_write_failed", error=str(e))
                            
                    logger.info("geocoding_success", address=query, lat=lat, lon=lon)
                    return lat, lon, display_name
                else:
                    logger.debug("geocoding_no_results", address=query)
            
            elif resp.status_code == 429:
                logger.warning("geocoding_rate_limited", msg="Too many requests to Nominatim")
            else:
                logger.warning("geocoding_api_error", status=resp.status_code, text=resp.text[:100])
                
        except Exception as e:
            logger.error("geocoding_api_exception", query=query, error=str(e))
        return None, None, None

