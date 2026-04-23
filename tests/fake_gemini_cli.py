#!/usr/bin/env python3
import json
import os
import sys
import time


mode = os.getenv("FAKE_GEMINI_MODE", "valid")
if mode == "slow":
    time.sleep(float(os.getenv("FAKE_GEMINI_SLEEP", "2")))
if mode == "capacity":
    print("429 quota exhausted", file=sys.stderr)
    raise SystemExit(1)
if mode == "invalid_json":
    print("not-json")
    raise SystemExit(0)

args = sys.argv
prompt = ""
if "-p" in args:
    try:
        prompt = args[args.index("-p") + 1]
    except Exception:
        prompt = ""

if "Historical MOEX backtest" in prompt:
    payload = {
        "days": [
            {
                "date": "2026-04-15",
                "summary": "fake backtest decision",
                "actions": [
                    {"secid": "SBER", "action": "buy", "confidence": 0.7, "reason": "fake smoke"}
                ],
            }
        ]
    }
elif "Respond ONLY raw JSON" in prompt:
    action = os.getenv("FAKE_GEMINI_ACTION", "buy")
    secid = os.getenv("FAKE_GEMINI_SECID", "SBER")
    quantity = os.getenv("FAKE_GEMINI_QUANTITY")
    decision = {"secid": secid, "action": action, "reason": "fake smoke"}
    if quantity:
        decision["quantity"] = int(quantity)
    payload = {
        "summary": "fake trader decision",
        "actions": [decision],
    }
elif "Sentiment" in prompt or "sentiment" in prompt:
    payload = {
        "items": [
            {"secid": "SBER", "score": 0.1, "summary": "fake neutral-positive"}
        ]
    }
elif "trading league auditor" in prompt or "TRADERS_JSON" in prompt:
    payload = {
        "traders": {
            "Chaos_Bill": {
                "work": "fake work",
                "resume": "fake resume",
                "tuning": "fake tuning",
            }
        }
    }
else:
    payload = {"summary": "fake ok", "actions": []}

print(json.dumps(payload, ensure_ascii=False))
