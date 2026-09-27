import unittest
from unittest.mock import Mock, patch

from notion_portfolio.accounting import calculate
from notion_portfolio.sync import Client, PREFIX, desired_rows, ensure_schema, index_rows, reconcile, rich, title, verify_rows
from notion_portfolio.tests.test_accounting import trade


class FakeClient:
    def __init__(self):
        self.rows = []
        self.writes = 0

    def create(self, source_id, properties):
        self.rows.append({"id": str(len(self.rows)), "properties": properties})
        self.writes += 1

    def update(self, id, properties):
        next(r for r in self.rows if r["id"] == id)["properties"].update(properties)
        self.writes += 1


class SyncTests(unittest.TestCase):
    def test_idempotence_and_reactivation(self):
        client = FakeClient()
        key = PREFIX + "sale:example"
        desired = {key: {"Name": title("Example"), "年度": rich("2025")}}
        self.assertEqual(reconcile(client, "ds", desired, client.rows)["created"], 1)
        self.assertEqual(reconcile(client, "ds", desired, client.rows)["unchanged"], 1)
        self.assertEqual(client.writes, 1)
        self.assertEqual(reconcile(client, "ds", {}, client.rows)["deactivated"], 1)
        self.assertEqual(reconcile(client, "ds", desired, client.rows)["updated"], 1)
        self.assertEqual(len(client.rows), 1)

    def test_unmanaged_rows_untouched(self):
        client = FakeClient()
        client.rows = [{"id": "manual", "properties": {"Name": title("My note")}}]
        reconcile(client, "ds", {}, client.rows)
        self.assertEqual(client.writes, 0)

    def test_duplicate_keys_fail_before_writes(self):
        row = {"id": "a", "properties": {"同步鍵": rich(PREFIX + "sale:a")}}
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            index_rows([row, row])

    def test_schema_creates_numbers_before_formulas(self):
        client = Mock()
        client.schema.return_value = {"properties": {"Name": {"type": "title"}}}
        ensure_schema(client, "ds", {"Result": {"formula": {"expression": 'prop("Input")'}}, "Input": {"number": {}}})
        self.assertEqual(client.update_schema.call_args_list[0].args[1], {"Input": {"number": {}}})
        self.assertIn("Result", client.update_schema.call_args_list[1].args[1])

    def test_verification_detects_formula_mismatch(self):
        key = PREFIX + "holding:example"
        properties = {"買進成本": {"number": 10}, "買進費用（含稅）": {"number": 1}}
        row = {"id": "a", "properties": properties | {"同步鍵": rich(key), "有效": {"checkbox": True},
               "持有總成本": {"type": "formula", "formula": {"type": "number", "number": 10}}}}
        with self.assertRaisesRegex(RuntimeError, "formula result"):
            verify_rows({key: properties}, [row])
        row["properties"]["持有總成本"]["formula"]["number"] = 11
        verify_rows({key: properties}, [row])

    def test_year_and_sale_have_distinct_types_and_keys(self):
        result = calculate([trade("a", "買入", 10, 10, 1),
                            trade("b", "賣出", 5, 20, 1, "2025-01-01")])
        profits, holdings = desired_rows(result)
        self.assertEqual(len(profits), 2)
        self.assertEqual(profits[PREFIX + "year:2025"]["類型"]["select"]["name"], "年度彙總")
        self.assertEqual(len(holdings), 1)

    def test_zero_cost_return_is_blank(self):
        result = calculate([trade("a", "買入", 10, 0), trade("b", "賣出", 10, 20, day="2025-01-01")])
        profits, _ = desired_rows(result)
        self.assertIsNone(profits[PREFIX + "sale:b"]["成本報酬率"]["number"])

    def test_pagination_reads_all_rows(self):
        client = Client("test")
        client.call = Mock(side_effect=[{"results": [1], "has_more": True, "next_cursor": "c"},
                                       {"results": [2], "has_more": False}])
        self.assertEqual(client.query_all("source"), [1, 2])

    @patch("notion_portfolio.sync.time.sleep")
    def test_rate_limit_retry(self, sleep):
        client = Client("test")
        limited = Mock(ok=False, status_code=429, headers={"Retry-After": "1"})
        success = Mock(ok=True)
        success.json.return_value = {"ok": True}
        operation = Mock(side_effect=[limited, success])
        self.assertEqual(client.call(operation), {"ok": True})
        self.assertEqual(operation.call_count, 2)

    @patch("notion_portfolio.sync.time.sleep")
    def test_ambiguous_create_is_not_retried(self, sleep):
        client = Client("test")
        operation = Mock(return_value=Mock(ok=False, status_code=500, headers={}))
        with self.assertRaises(RuntimeError):
            client.call(operation, create=True)
        self.assertEqual(operation.call_count, 1)


if __name__ == "__main__":
    unittest.main()
