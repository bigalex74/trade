import sys
import os
import unittest
from datetime import datetime, date

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import weekly_quant_audit

class TestPeriodicLogic(unittest.TestCase):
    def test_drawdown_calculation_logic(self):
        # Имитируем значения эквити за 5 дней
        # 10000 -> 11000 (peak) -> 9000 (drawdown) -> 12000 (new peak) -> 11000
        values = [10000.0, 11000.0, 9000.0, 12000.0, 11000.0]
        
        peak = values[0]
        max_dd = 0
        for v in values:
            if v > peak: peak = v
            dd = (peak - v) / peak * 100
            if dd > max_dd: max_dd = dd
            
        # (11000 - 9000) / 11000 * 100 = 18.1818...
        self.assertAlmostEqual(max_dd, 18.18, places=2)

    def test_format_weekly_report_structure(self):
        data = {
            "period_start": "2026-04-18",
            "period_end": "2026-04-24",
            "traders": {
                "Scalper_Kesha": {"profit_pct": 5.2, "profit_abs": 520, "max_drawdown": 1.2, "days_active": 5},
                "Value_Monya": {"profit_pct": -2.1, "profit_abs": -210, "max_drawdown": 3.5, "days_active": 5}
            }
        }
        report = weekly_quant_audit._format_weekly_report(data)
        self.assertIn("КВАНТОВЫЙ АУДИТ", report)
        self.assertIn("Scalper_Kesha", report)
        self.assertIn("Value_Monya", report)
        self.assertIn("🟢", report)
        self.assertIn("🔴", report)

if __name__ == "__main__":
    unittest.main()
