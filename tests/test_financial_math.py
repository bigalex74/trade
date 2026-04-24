import unittest
from decimal import Decimal

class TestFinancialMath(unittest.TestCase):
    def test_float_imprecision(self):
        # Классический пример ошибки float: 0.1 + 0.2 != 0.3
        val = 0.1 + 0.2
        self.assertNotEqual(val, 0.3)
        print(f"Float 0.1 + 0.2 = {val}")

    def test_decimal_precision(self):
        # Decimal должен считать точно
        val = Decimal('0.1') + Decimal('0.2')
        self.assertEqual(val, Decimal('0.3'))
        print(f"Decimal '0.1' + '0.2' = {val}")

if __name__ == '__main__':
    unittest.main()
