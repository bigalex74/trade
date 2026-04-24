import unittest
from decimal import Decimal

# Мы будем тестировать логику срабатывания, так как SQL требует живую базу.
# Проверим саму идею порогов.

def check_anomaly(price_change, vol_ratio):
    # Повторяем логику из market_radar.py
    is_price_anomaly = abs(price_change) > 1.5
    is_volume_anomaly = vol_ratio > 3.0
    return is_price_anomaly, is_volume_anomaly

class TestMarketRadar(unittest.TestCase):
    def test_price_spike(self):
        p, v = check_anomaly(2.1, 1.0)
        self.assertTrue(p)
        self.assertFalse(v)
        
    def test_volume_spike(self):
        p, v = check_anomaly(0.5, 5.5)
        self.assertFalse(p)
        self.assertTrue(v)
        
    def test_no_anomaly(self):
        p, v = check_anomaly(1.2, 2.5)
        self.assertFalse(p)
        self.assertFalse(v)

if __name__ == '__main__':
    unittest.main()
