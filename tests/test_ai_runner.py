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

    def test_parse_json_response(self):
        cli_out = json.dumps({"response": "```json\n{\"decision\": \"hold\"}\n```"})
        parsed = gemini_cli_runner.parse_json_response(cli_out)
        self.assertEqual(parsed["decision"], "hold")

    @patch('gemini_cli_runner.subprocess.run')
    @patch('gemini_cli_runner.acquire_gemini_slot')
    @patch('ai_cost_guard.preflight')
    @patch('ai_cost_guard.model_unhealthy_reason')
    @patch('ai_cost_guard.log_call')
    @patch('gemini_cli_runner.fcntl.flock') # Мокаем flock чтобы не требовал fileno
    def test_call_gemini_with_fallback_success(self, mock_flock, mock_log, mock_health, mock_pre, mock_slot, mock_run):
        mock_pre.return_value = MagicMock(allowed=True)
        mock_health.return_value = None
        
        # Создаем мок для файла, который ведет себя как дескриптор
        mock_handle = MagicMock()
        mock_handle.fileno.return_value = 99
        mock_slot.return_value = (0, mock_handle)
        
        mock_run.return_value = MagicMock(returncode=0, stdout='{"test": "ok"}', stderr='')
        
        result, model_id = gemini_cli_runner.call_gemini_with_fallback("test-prompt", models=["test-model"])
        self.assertEqual(result["test"], "ok")
        self.assertEqual(model_id, "test-model")

if __name__ == "__main__":
    unittest.main()
