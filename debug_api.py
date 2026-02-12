"""Debug the /rag/query endpoint directly."""
import asyncio
import requests
import json

async def test_api():
    url = "http://localhost:8000/rag/query"
    payload = {
        "question": "What does utils.py do?",
        "repo_path": "D:\\Practice\\python\\Synapse\\test_repo",
        "top_k": 5,
        "expand_depth": 2
    }
    
    print(f"Sending to {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(url, json=payload)
        print(f"Status: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Answer preview: {data['answer'][:200]}...")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_api())
