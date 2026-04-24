import json
import os
import requests
from datetime import datetime
from hybrid_rag import EmbeddingClient, QDRANT_URL, API_KEY_QDRANT

# COLLECTION NAME FOR ALPHA DEALS
COLLECTION_NAME = "alpha_memory"

def prepare_few_shot_text(deal):
    """Превращает данные сделки в текст для эмбеддинга и обучения."""
    return f"""
    SUCCESSFUL TRADE CASE:
    Asset: {deal['secid']}
    Action: Closed with profit {deal['pnl']:.2f} RUB
    Market Context at entry: {json.dumps(deal['market_context'], ensure_ascii=False)}
    Recommendation: Similar conditions historically led to profit. Consider high-confidence entry.
    """

def upload_to_qdrant(deals):
    print(f"[{datetime.now().isoformat()}] Uploading {len(deals)} alpha cases to Qdrant...")
    embedder = EmbeddingClient()
    
    points = []
    for i, deal in enumerate(deals):
        text = prepare_few_shot_text(deal)
        vector = embedder.embed(text)
        
        points.append({
            "id": int(datetime.now().timestamp() * 1000) + i,
            "vector": vector,
            "payload": {
                "text": text,
                "trader": deal['trader'],
                "secid": deal['secid'],
                "pnl": deal['pnl'],
                "timestamp": deal['time'],
                "kind": "alpha_few_shot"
            }
        })

    # Загружаем в Qdrant
    try:
        # 1. Убеждаемся что коллекция существует (упрощенно)
        # 2. Грузим точки
        url = f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points"
        resp = requests.put(url, json={"points": points}, headers={"api-key": API_KEY_QDRANT}, timeout=30)
        if resp.status_code == 200:
            print(f"Successfully uploaded {len(points)} points to Qdrant.")
        else:
            print(f"Qdrant upload failed: {resp.text}")
    except Exception as e:
        print(f"Failed to communicate with Qdrant: {e}")

if __name__ == "__main__":
    temp_file = "/tmp/alpha_deals_temp.json"
    if os.path.exists(temp_file):
        with open(temp_file, "r") as f:
            deals = json.load(f)
        upload_to_qdrant(deals)
    else:
        print("No temp deals file found. Run alpha_extractor.py first.")
EOF
