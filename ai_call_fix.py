def call_ai_with_fallback(prompt, models_rank):
    for model in models_rank:
        model_id = model['id']
        cmd = ["gemini", "-p", prompt, "--model", model_id, "--output-format", "json", "--approval-mode", "yolo", "--allowed-mcp-server-names", "lightrag-kb,lightrag-algo"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
            if "QUOTA_EXHAUSTED" in res.stderr:
                send_telegram(f"⚠️ Лимит {model_id} исчерпан. Переключаюсь.")
                continue
            if res.returncode != 0: 
                print(f"Error for {model_id}: {res.stderr}")
                continue
            
            # Robust JSON parsing
            out_text = res.stdout
            try:
                # First, try to parse as-is
                out_json = json.loads(out_text)
                response_text = out_json.get("response", "")
            except json.JSONDecodeError:
                # If it fails, maybe it's just the response text
                response_text = out_text
            
            if "```json" in response_text:
                json_part = response_text.split("```json")[1].split("```")[0]
                return json.loads(json_part)
            else:
                return json.loads(response_text) # Assumes the response is a pure JSON string
                
        except Exception as e:
            print(f"General exception for {model_id}: {e}")
            continue
    return None