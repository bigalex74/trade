import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_start_translation_payload():
    # Тест структуры полезной нагрузки для n8n
    payload = {
        "file_id": "f123",
        "file_name": "test.docx",
        "bp_file_id": "p1",
        "pp_file_id": "p2",
        "glossary_id": "g1",
        "create_glossary": False
    }
    # Мы не можем реально достучаться до n8n в тестах, 
    # но можем проверить, что API принимает запрос корректно
    response = client.post("/api/start-translation", json=payload)
    # Ожидаем 200 (успех) или 502 (ошибка n8n, но запрос прошел валидацию)
    assert response.status_code in [200, 502], f"Expected 200 or 502, got {response.status_code}"
