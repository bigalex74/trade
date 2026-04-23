import sys
import os
import unittest
import json
from unittest.mock import MagicMock, patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gemini_cli_runner

class TestAiRunner(unittest.TestCase):
    def test_strip_code_fence(self):
        raw = "```json\n{\"action\": \"buy\"}\n```"
        clean = gemini_cli_runner._strip_code_fence(raw)
        self.assertEqual(clean.strip(), "{\"action\": \"buy\"}")

    def test_parse_json_response_resilient(self):
        # Тест на извлечение JSON из текста с мусором
        dirty_out = "Here is the result: {\"decision\": \"hold\", \"score\": 0.8} Hope it helps!"
        parsed = gemini_cli_runner.parse_json_response(dirty_out)
        self.assertEqual(parsed["decision"], "hold")
        self.assertEqual(parsed["score"], 0.8)
        
        # Тест на извлечение из markdown блока
        md_out = "Sure thing: ```json\n{\"action\": \"sell\"}\n```"
        parsed_md = gemini_cli_runner.parse_json_response(md_out)
        self.assertEqual(parsed_md["action"], "sell")

    @patch('gemini_cli_runner.subprocess.run')
    @patch('gemini_cli_runner.acquire_gemini_slot')
    @patch('ai_cost_guard.preflight')
    @patch('ai_cost_guard.model_unhealthy_reason')
    @patch('ai_cost_guard.log_call')
    @patch('gemini_cli_runner.fcntl.flock')
    def test_call_gemini_with_fallback_retry(self, mock_flock, mock_log, mock_health, mock_pre, mock_slot, mock_run):
        mock_pre.return_value = MagicMock(allowed=True)
        mock_health.return_value = None
        mock_handle = MagicMock(); mock_handle.fileno.return_value = 99
        mock_slot.return_value = (0, mock_handle)
        
        # Имитируем: первый вызов возвращает битый JSON, второй (retry) - нормальный
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='Broken { JSON', stderr=''),
            MagicMock(returncode=0, stdout='{"status": "ok"}', stderr='')
        ]
        
        result, model_id = gemini_cli_runner.call_gemini_with_fallback("test-prompt", models=["test-model"])
        self.assertEqual(result["status"], "ok")
        # Проверяем что было 2 вызова (первый и ретрай)
        self.assertEqual(mock_run.call_count, 2)

if __name__ == "__main__":
    unittest.main()
