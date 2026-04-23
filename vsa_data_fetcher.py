
import os
import json
from crypto_research_context import load_market_context, compact_context_payload

def main():
    try:
        context = load_market_context()
        if "BTC/USDT" in context:
            btc_data = compact_context_payload(context["BTC/USDT"])
            print(json.dumps(btc_data, indent=2))
        else:
            print("BTC/USDT not found in context")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
