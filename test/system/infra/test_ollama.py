import httpx
import json
import pytest
import asyncio

@pytest.mark.asyncio
async def test_gemma3():
    # Inside docker, use 'ollama' host
    url = "http://ollama:11434/api/generate"
    payload = {
        "model": "gemma3:4b",
        "prompt": "Return only the coordinates for Taipei 101 as a JSON object: {\"lat\": 25.0339, \"lng\": 121.5644}",
        "stream": False,
        "format": "json"
    }
    
    print(f"Testing Ollama at {url} with model gemma3:4b...")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, timeout=30)
            print(f"Status Code: {r.status_code}")
            if r.status_code == 200:
                print("Success! Response:")
                print(json.dumps(r.json(), indent=2, ensure_ascii=False))
            else:
                print(f"Error: {r.text}")
    except Exception as e:
        print(f"Failed to connect: {e}")

if __name__ == "__main__":
    asyncio.run(test_gemma3())
