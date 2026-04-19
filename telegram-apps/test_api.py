import requests
import os

BASE_URL = "http://127.0.0.1:8000"

def test_api_suite():
    print("--- Starting Regression Test Suite ---")
    created_id = None
    
    try:
        # 1. List
        res = requests.get(f"{BASE_URL}/api/prompts")
        assert res.status_code == 200
        
        # 2. Create
        res = requests.post(f"{BASE_URL}/api/prompts", json={"name": "RegTest", "prompt": "Content"})
        assert res.status_code == 200
        
        prompts = requests.get(f"{BASE_URL}/api/prompts").json()
        new_p = next((x for x in prompts if x['name'] == "RegTest"), None)
        created_id = new_p['id']
        print(f"Created prompt ID: {created_id}")

        # 3. Update
        res = requests.put(f"{BASE_URL}/api/prompts/{created_id}", json={"name": "RegTestUpdated", "prompt": "NewContent"})
        assert res.status_code == 200
        
        # 4. History
        res = requests.get(f"{BASE_URL}/api/prompts/{created_id}/history")
        assert res.status_code == 200
        
        # 5. Delete
        res = requests.delete(f"{BASE_URL}/api/prompts/{created_id}")
        assert res.status_code == 200
        created_id = None # Clear local ref
        print("Test suite passed: Data cleaned up.")

    except Exception as e:
        print(f"!!! TEST FAILED: {e}")
        # Попытка очистки при ошибке
        if created_id:
            requests.delete(f"{BASE_URL}/api/prompts/{created_id}")
        exit(1)

if __name__ == "__main__":
    test_api_suite()
