import json
import pytest
from pathlib import Path
from core.adapters.adapter_104 import Adapter104
from core.infra import SourcePlatform

ROOT_DIR = Path(__file__).parents[3]
FIXTURE_DIR = ROOT_DIR / "test" / "fixtures" / "data"

def test_104_coordinates_extraction():
    adapter = Adapter104()
    
    # Load sample
    path = FIXTURE_DIR / "native_geo_sample.json"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # The JobPosting is the second element usually, but in our synthetic sample it's the first
    ld = data[0]
    
    lat = adapter.get_latitude(ld)
    lon = adapter.get_longitude(ld)
    
    assert lat == 25.075
    assert lon == 121.572
    
    # Verify map_to_job works (without coordinate attributes which moved to JobLocationPydantic)
    job = adapter.map_to_job(ld, url=ld["url"])
    assert job is not None
    assert job.title is not None
    print(f"✅ Successfully extracted coordinates via adapter: {lat}, {lon}")

if __name__ == "__main__":
    # Simple runner
    try:
        test_104_coordinates_extraction()
        print("Test PASSED")
    except Exception as e:
        print(f"Test FAILED: {e}")
        import traceback
        traceback.print_exc()
