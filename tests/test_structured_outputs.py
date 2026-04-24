import sys
import os
import unittest
import json
from unittest.mock import MagicMock, patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gemini_cli_runner

class TestStructuredOutputs(unittest.TestCase):
    @patch('gemini_cli_runner.subprocess.run')
    @patch('gemini_cli_runner.acquire_gemini_slot')
    @patch('gemini_cli_runner.fcntl.flock')
    @patch('ai_cost_guard.preflight')
    @patch('ai_cost_guard.model_unhealthy_reason')
    @patch('ai_cost_guard.log_call')
    def test_schema_argument_passed(self, mock_log, mock_health, mock_pre, mock_flock, mock_slot, mock_run):
        # Гарантируем проход всех проверок
        mock_pre.return_value = MagicMock(allowed=True)
        mock_health.return_value = None # Модель ВСЕГДА здорова для теста
        
        mock_handle = MagicMock(); mock_handle.fileno.return_value = 99
        mock_slot.return_value = (0, mock_handle)
        
        # Имитируем успешный запуск с возвратом JSON
        mock_run.return_value = MagicMock(returncode=0, stdout='{"actions": []}', stderr='')
        
        test_schema = {"type": "object", "properties": {"actions": {"type": "array"}}}
        
        # Вызываем функцию
        _, _ = gemini_cli_runner.call_ai_json_with_fallback(
            "test-prompt", 
            models=["gemini-3.1-pro-preview"],
            response_schema=test_schema
        )
        
        # Проверяем вызов subprocess.run
        self.assertTrue(mock_run.called, "subprocess.run should have been called")
        args = mock_run.call_args[0][0]
        self.assertIn("--schema", args)
        schema_val = args[args.index("--schema") + 1]
        self.assertEqual(json.loads(schema_val), test_schema)

if __name__ == "__main__":
    unittest.main()
