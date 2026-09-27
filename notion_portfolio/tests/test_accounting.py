import unittest
from decimal import Decimal as D

from notion_portfolio.accounting import Trade, calculate, parse_trades


def trade(id, kind, quantity, price, fee=0, day="2024-01-01", broker="Example", name="TEST Example"):
    return Trade(id, name, broker, kind, day, D(str(quantity)), D(str(price)), D(str(fee)))


class AccountingTests(unittest.TestCase):
    def test_fifo_partial_and_cross_year_fees(self):
        result = calculate([trade("a", "買入", 100, 10, 10),
                            trade("b", "買入", 100, 20, 20, "2024-02-01"),
                            trade("c", "賣出", 150, 30, 30, "2025-01-01")])
        sale = result["sales"][0]
        self.assertEqual(sale["basis"], D(2000))
        self.assertEqual(sale["buy_fees"], D(20))
        self.assertEqual(sale["profit"], D(2450))
        self.assertEqual(result["years"]["2025"]["profit"], D(2450))
        self.assertNotIn("2024", result["years"])
        self.assertEqual(result["holdings"][0]["quantity"], D(50))
        self.assertEqual(result["holdings"][0]["basis"], D(1000))
        self.assertEqual(result["holdings"][0]["buy_fees"], D(10))

    def test_brokers_do_not_share_inventory(self):
        with self.assertRaisesRegex(ValueError, "exceeds"):
            calculate([trade("a", "買入", 100, 10, broker="A"),
                       trade("b", "賣出", 100, 20, day="2024-02-01", broker="B")])

    def test_oversell_and_late_purchase_rejected(self):
        with self.assertRaisesRegex(ValueError, "exceeds"):
            calculate([trade("a", "賣出", 100, 10), trade("b", "買入", 100, 10, day="2024-02-01")])

    def test_same_day_without_times_rejected(self):
        with self.assertRaisesRegex(ValueError, "explicit"):
            calculate([trade("a", "買入", 10, 10), trade("b", "賣出", 10, 20)])

    def test_timed_trades_and_taipei_year(self):
        result = calculate([trade("a", "買入", 10, 10, day="2024-12-31T15:00:00Z"),
                            trade("b", "賣出", 10, 20, day="2024-12-31T17:00:00Z")])
        self.assertIn("2025", result["years"])
        self.assertEqual(result["holdings"], [])

    def test_equal_timestamps_rejected(self):
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            calculate([trade("a", "買入", 10, 10, day="2024-01-01T12:00:00+08:00"),
                       trade("b", "賣出", 10, 20, day="2024-01-01T12:00:00+08:00")])

    def test_fractional_fee_conservation(self):
        result = calculate([trade("a", "買入", 3, 10, 1)] +
                           [trade(str(i), "賣出", 1, 10, day=f"2024-02-0{i}") for i in range(1, 4)])
        self.assertEqual(sum(s["buy_fees"] for s in result["sales"]), D(1))
        self.assertEqual(result["years"]["2024"]["profit"], D(-1))

    def test_permutation_and_same_day_tie_are_stable(self):
        rows = [trade("a", "買入", 10, 10), trade("b", "買入", 10, 20),
                trade("c", "賣出", 15, 30, day="2024-02-01")]
        self.assertEqual(calculate(rows), calculate(list(reversed(rows))))
        self.assertEqual(calculate(rows)["sales"][0]["basis"], D(200))

    def test_historical_edit_recalculates_later_sales(self):
        sale = trade("b", "賣出", 10, 20, day="2024-02-01")
        old = calculate([trade("a", "買入", 10, 10), sale])
        new = calculate([trade("a", "買入", 10, 15), sale])
        self.assertEqual(old["sales"][0]["profit"] - new["sales"][0]["profit"], D(50))

    def test_malformed_row_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid source"):
            parse_trades([{"id": "bad", "properties": {}}])

    def test_empty_ledger(self):
        self.assertEqual(calculate([]), {"sales": [], "years": {}, "holdings": []})


if __name__ == "__main__":
    unittest.main()
