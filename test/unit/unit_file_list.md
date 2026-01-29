# 單元測試目錄進出管理登記簿

本目錄存放針對系統獨立組件邏輯的單元測試。

## 檔案清單

| 檔案名稱 | 功能說明 |
| :--- | :--- |
| `test_adversarial.py` | 對抗性測試：驗證系統阻擋異常/惡意 JSON 的能力。 |

##子目錄檔案清單

### 1. Adapters (適配器)
| 檔案名稱 | 功能說明 |
| :--- | :--- |
| `adapters/test_adapter_logic.py` | 測試 104, 1111, CakeResume 等平台 Adapter 的映射與 ID 提取邏輯。 |

### 2. Enrichment (資料富化)
| 檔案名稱 | 功能說明 |
| :--- | :--- |
| `enrichment/test_address.py` | 測試台灣地址正規化（如號、樓、括號處理）。 |
| `enrichment/test_ai_healing.py` | 測試 LLM 缺失欄位修補邏輯。 |
| `enrichment/test_geo.py` | 測試地址去重與國家/地區識別。 |

### 3. Extractors (提取器)
| 檔案名稱 | 功能說明 |
| :--- | :--- |
| `extractors/test_jsonld.py` | 測試從 HTML 中提取 JSON-LD 的核心功能。 |

### 4. Parsers (解析器)
| 檔案名稱 | 功能說明 |
| :--- | :--- |
| `parsers/test_coords.py` | 測試平台特定（如 104）的地理座標提取邏輯。 |
