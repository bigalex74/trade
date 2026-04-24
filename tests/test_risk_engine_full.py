import sys
import os
import unittest
from decimal import Decimal

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from risk_engine import _base_candidate, RiskSettings

class TestRiskEngineFull(unittest.TestCase):
    def setUp(self):
        self.settings = RiskSettings(
            max_actions_per_trader_day=5,
            max_symbol_exposure_pct=Decimal("0.25"),
            min_order_value=Decimal("100.0"),
            atr_risk_pct=Decimal("0.01")
        )
        self.state = {
            "equity": Decimal("10000.0"),
            "cash": Decimal("5000.0"),
            "available_cash": Decimal("5000.0"),
            "gross_exposure": Decimal("2000.0"),
            "position_values": {"SBER": Decimal("0.0")},
            "positions": {},
            "pending_count": 0,
            "day_action_count": 0,
            "cooldown_active": False,
            "pending_sell_qty": {}
        }
        self.prices = {"SBER": Decimal("300.0"), "GAZP": Decimal("150.0")}
        self.market_features = {
            "SBER": {"atr_pct": Decimal("2.0"), "sent_score": Decimal("0.0")},
            "GAZP": {"atr_pct": Decimal("2.0"), "sent_score": Decimal("0.0")}
        }

    def test_buy_valid(self):
        action = {"secid": "SBER", "action": "buy", "quantity": 10}
        candidate, reason = _base_candidate(action, self.state, self.prices, self.market_features, self.settings, Decimal("1.0"))
        self.assertIsNone(reason)
        self.assertEqual(candidate["order_type"], "buy")

    def test_exposure_limit(self):
        # Превышаем лимит на символ (2500)
        self.state["position_values"]["SBER"] = Decimal("2450.0")
        action = {"secid": "SBER", "action": "buy", "quantity": 1}
        candidate, reason = _base_candidate(action, self.state, self.prices, self.market_features, self.settings, Decimal("1.0"))
        self.assertEqual(reason, "order_value_below_min_or_no_risk_room")

    def test_sell_without_position(self):
        action = {"secid": "GAZP", "action": "sell"}
        candidate, reason = _base_candidate(action, self.state, self.prices, self.market_features, self.settings, Decimal("1.0"))
        self.assertEqual(reason, "no_available_position_to_sell")

if __name__ == "__main__":
    unittest.main()
