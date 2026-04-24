import sys
import os
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai_daily_report

class TestDailyReportLogic(unittest.TestCase):
    def test_fallback_lesson_positive(self):
        res = ai_daily_report.fallback_lesson("Profit_Trader", 5.5, [])
        self.assertIn("высокую эффективность", res["tuning"])

    def test_fallback_lesson_negative(self):
        res = ai_daily_report.fallback_lesson("Loss_Trader", -3.2, [])
        self.assertIn("Снизить размер позиции", res["tuning"])

    @patch('ai_daily_report.generate_batch_lessons')
    @patch('ai_daily_report.generate_individual_lessons')
    @patch('ai_daily_report.generate_daily_chart')
    @patch('ai_daily_report.get_db_connection')
    @patch('ai_daily_report.query_kb')
    @patch('market_research_context.load_market_context')
    @patch('market_research_context.build_price_snapshot')
    def test_generate_report_cascading(self, mock_build_price, mock_load_market, mock_kb, mock_db, mock_chart, mock_indiv, mock_batch):
        # Имитируем сбой батча
        mock_batch.return_value = {}
        mock_indiv.return_value = {"work": "indiv_ok", "resume": "ok", "tuning": "ok"}
        mock_chart.return_value = MagicMock() # Пустой мок для графика
        
        mock_conn = MagicMock()
        mock_db.return_value = mock_conn
        mock_cur = mock_conn.cursor.return_value
        mock_cur.fetchall.side_effect = [
            [("Test_Trader", 1000.0)],
            [],
            [],
            [(10000.0,)]
        ]
        
        os.environ["AI_TEST_MODE"] = "1"
        ai_daily_report.generate_report()
        
        # Подтверждаем переход на индивидуальный разбор
        self.assertTrue(mock_indiv.called)

if __name__ == "__main__":
    unittest.main()
