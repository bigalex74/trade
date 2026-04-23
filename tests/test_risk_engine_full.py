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
            max_symbol_exposure_pct=0.25,
            min_order_value=100.0,
            atr_risk_pct=0.01
        )
        self.state = {
            "equity": 10000.0,
            "cash": 5000.0,
            "available_cash": 5000.0,
            "gross_exposure": 2000.0,
            "position_values": {"SBER": 0.0},
            "positions": {},
            "pending_count": 0,
            "day_action_count": 0,
            "cooldown_active": False,
            "pending_sell_qty": {}
        }
        # Цены для всех используемых тикеров
        self.prices = {"SBER": 300.0, "GAZP": 150.0}
        self.market_features = {
            "SBER": {"atr_pct": 2.0, "sent_score": 0.0},
            "GAZP": {"atr_pct": 2.0, "sent_score": 0.0}
        }

    def test_buy_valid(self):
        action = {"secid": "SBER", "action": "buy", "quantity": 10}
        candidate, reason = _base_candidate(action, self.state, self.prices, self.market_features, self.settings, 1.0)
        self.assertIsNone(reason)
        self.assertEqual(candidate["action"], "buy")

    def test_exposure_limit(self):
        # Почти исчерпан лимит на символ (лимит 2500, текущая поз 2450)
        self.state["position_values"]["SBER"] = 2450.0
        action = {"secid": "SBER", "action": "buy", "quantity": 1}
        candidate, reason = _base_candidate(action, self.state, self.prices, self.market_features, self.settings, 1.0)
        # Ожидаем отказ так как остатка бюджета (50) не хватит на мин ордер (100)
        self.assertEqual(reason, "order_value_below_min_or_no_risk_room")

    def test_sell_without_position(self):
        # Теперь цена GAZP есть, но позиции нет
        action = {"secid": "GAZP", "action": "sell"}
        candidate, reason = _base_candidate(action, self.state, self.prices, self.market_features, self.settings, 1.0)
        self.assertEqual(reason, "no_available_position_to_sell")

if __name__ == "__main__":
    unittest.main()
