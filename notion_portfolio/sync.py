#!/usr/bin/env python3
"""Recalculate a Notion trade ledger. Default is a read-only dry run."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import uuid

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.notion import NotionApi
from notion_portfolio.accounting import calculate, money, parse_trades, text_value

VERSION = "2025-09-03"
PREFIX = "notion-portfolio:v1:"


class Client(NotionApi):
    """Reuse the shared client; add bounded retries, pacing and schema updates."""
    def __init__(self, token):
        super().__init__(token, version=VERSION)
        self.last_request = 0.0

    def call(self, operation, *, create=False):
        for attempt in range(5):
            time.sleep(max(0, .36 - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                response = operation()
            except requests.RequestException:
                # Never blindly repeat an ambiguous create: the next run re-queries IDs.
                if create or attempt == 4:
                    raise RuntimeError("Notion network failure; rerun sync to reconcile") from None
                time.sleep(2 ** attempt)
                continue
            if response.ok:
                return response.json()
            if response.status_code == 429 or (response.status_code >= 500 and not create):
                time.sleep(max(float(response.headers.get("Retry-After", 0)), 2 ** attempt))
                continue
            # API bodies may contain personal values. Keep public CI output minimal.
            raise RuntimeError(f"Notion HTTP {response.status_code}; request {response.headers.get('x-request-id', 'unknown')}")
        raise RuntimeError("Notion retry limit reached")

    def schema(self, source_id):
        return self.call(lambda: super(Client, self).get_data_source(source_id))

    def query_all(self, source_id):
        rows, cursor = [], None
        while True:
            body = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            data = self.call(lambda: super(Client, self).query_data_source(source_id, body))
            rows.extend(data["results"])
            if not data["has_more"]:
                return rows
            if not data.get("next_cursor") or data["next_cursor"] == cursor:
                raise RuntimeError("Invalid Notion pagination cursor")
            cursor = data["next_cursor"]

    def update_schema(self, source_id, properties):
        return self.call(lambda: requests.patch(
            f"https://api.notion.com/v1/data_sources/{source_id}",
            headers={"Authorization": f"Bearer {self.token}", "Notion-Version": self.version},
            json={"properties": properties}, timeout=30))

    def create(self, source_id, properties):
        return self.call(lambda: super(Client, self).create_page_in_data_source(source_id, properties), create=True)

    def update(self, page_id, properties):
        return self.call(lambda: super(Client, self).patch_page(page_id, {"properties": properties}))


def rich(value):
    value = str(value)
    chunks = [value[i:i + 1800] for i in range(0, len(value), 1800)]
    if len(chunks) > 100:
        raise ValueError("Allocation detail exceeds Notion rich-text limit")
    return {"rich_text": [{"text": {"content": s}} for s in chunks]}


def title(value):
    return {"title": [{"text": {"content": str(value)}}]}


def number(value):
    return {"number": float(value)}


def select(value):
    return {"select": {"name": value}}


def date(value):
    return {"date": {"start": value}}


def num_schema(format="number"):
    return {"number": {"format": format}}


PROFIT_FORMULA = 'round((prop("賣出金額") - prop("買進成本") - prop("買進費用（含稅）") - prop("賣出費用（含稅）")) * 100) / 100'


def common_schema():
    return {"同步鍵": {"rich_text": {}}, "有效": {"checkbox": {}}, "最後更新": {"date": {}}}


def profit_schema(source_id):
    return common_schema() | {
        "類型": {"select": {"options": [{"name": "賣出明細", "color": "blue"}, {"name": "年度彙總", "color": "purple"}]}},
        "股票代號": {"rich_text": {}}, "券商": {"select": {}}, "賣出日期": {"date": {}},
        "年度": {"rich_text": {}}, "賣出股數": num_schema(), "賣出價格": num_schema(),
        "買進成本": num_schema(), "買進費用（含稅）": num_schema(), "賣出金額": num_schema(),
        "賣出費用（含稅）": num_schema(), "淨損益": {"formula": {"expression": PROFIT_FORMULA}},
        "成本報酬率": num_schema("percent"),
        "盈虧": {"select": {"options": [{"name": "▲ 獲利", "color": "red"}, {"name": "▼ 虧損", "color": "green"}, {"name": "— 損益兩平", "color": "gray"}]}},
        "賣出筆數": num_schema(), "獲利筆數": num_schema(), "虧損筆數": num_schema(),
        "原始賣出": {"relation": {"data_source_id": source_id, "single_property": {}}},
        "成本配對明細": {"rich_text": {}},
    }


def holding_schema():
    return common_schema() | {
        "股票代號": {"rich_text": {}}, "券商": {"select": {}}, "持有股數": num_schema(),
        "買進成本": num_schema(), "買進費用（含稅）": num_schema(),
        "持有總成本": {"formula": {"expression": 'prop("買進成本") + prop("買進費用（含稅）")'}},
        "每股成本（含費用）": {"formula": {"expression": 'if(prop("持有股數") == 0, 0, (prop("買進成本") + prop("買進費用（含稅）")) / prop("持有股數"))'}},
        "最早買進日期": {"date": {}}, "剩餘批數": num_schema(), "剩餘批次明細": {"rich_text": {}},
    }


def ensure_schema(client, source_id, desired):
    actual = client.schema(source_id)["properties"]
    if actual.get("Name", {}).get("type") != "title":
        raise ValueError("Destination must have a Name title property")
    missing = {}
    for key, spec in desired.items():
        expected_type = next(iter(spec))
        if key not in actual:
            missing[key] = spec
        elif actual[key]["type"] != expected_type:
            raise ValueError(f"Destination property type mismatch: {key}")
        elif expected_type == "formula" and actual[key]["formula"]["expression"] != spec["formula"]["expression"]:
            missing[key] = spec
    ordinary = {k: v for k, v in missing.items() if "formula" not in v}
    if ordinary:
        client.update_schema(source_id, ordinary)
    # Referenced properties must exist before Notion validates formula types.
    for key, spec in missing.items():
        if "formula" in spec:
            client.update_schema(source_id, {key: spec})


def allocation_text(allocations):
    lines = []
    for a in allocations:
        t = a["trade"]
        lines.append(f'{t.day}｜{a["quantity"]} 股 × {t.price}｜成本 {money(a["basis"])}｜分攤費用 {money(a["fee"])}\nhttps://www.notion.so/{t.id.replace("-", "")}')
    return "\n\n".join(lines)


def result_properties(item):
    cost = item["basis"] + item["buy_fees"]
    return {
        "買進成本": number(item["basis"]), "買進費用（含稅）": number(item["buy_fees"]),
        "賣出金額": number(item["proceeds"]), "賣出費用（含稅）": number(item["sell_fees"]),
        "盈虧": select("▲ 獲利" if item["profit"] > 0 else "▼ 虧損" if item["profit"] < 0 else "— 損益兩平"),
        "成本報酬率": number(item["profit"] / cost) if cost else {"number": None},
    }


def desired_rows(result):
    profits, holdings = {}, {}
    for sale in result["sales"]:
        t = sale["trade"]
        profits[PREFIX + "sale:" + t.id] = result_properties(sale) | {
            "Name": title(f"{t.name}｜{t.day}"), "類型": select("賣出明細"),
            "股票代號": rich(t.code), "券商": select(t.broker), "賣出日期": date(t.date),
            "年度": rich(t.day[:4]), "賣出股數": number(t.quantity), "賣出價格": number(t.price),
            "賣出筆數": number(1), "獲利筆數": number(int(sale["profit"] > 0)),
            "虧損筆數": number(int(sale["profit"] < 0)), "原始賣出": {"relation": [{"id": t.id}]},
            "成本配對明細": rich(allocation_text(sale["allocations"])),
        }
    for year, annual in sorted(result["years"].items()):
        profits[PREFIX + "year:" + year] = result_properties(annual) | {
            "Name": title(f"{year} 年收益"), "類型": select("年度彙總"), "年度": rich(year),
            "賣出筆數": number(annual["count"]), "獲利筆數": number(annual["wins"]),
            "虧損筆數": number(annual["losses"]),
            "成本配對明細": rich("以賣出日期所屬年度計算；包含買賣已填費用，不重複計稅。成本報酬率是淨損益 ÷ 已實現含費用成本，並非帳戶年度報酬率。"),
        }
    for h in result["holdings"]:
        allocations = [{"trade": l["trade"], "quantity": l["quantity"],
                        "basis": l["quantity"] * l["trade"].price, "fee": l["fee"]} for l in h["lots"]]
        holdings[PREFIX + "holding:" + h["broker"] + ":" + h["code"]] = {
            "Name": title(h["name"]), "股票代號": rich(h["code"]), "券商": select(h["broker"]),
            "持有股數": number(h["quantity"]), "買進成本": number(h["basis"]),
            "買進費用（含稅）": number(h["buy_fees"]), "最早買進日期": date(h["first_date"]),
            "剩餘批數": number(len(h["lots"])), "剩餘批次明細": rich(allocation_text(allocations)),
        }
    return profits, holdings


def value(prop):
    kind = prop.get("type") or next(iter(prop))
    v = prop[kind]
    if kind in ("title", "rich_text"):
        return "".join(p.get("plain_text", p.get("text", {}).get("content", "")) for p in v)
    if kind == "select":
        return v["name"] if v else None
    if kind == "date":
        if not v:
            return None
        start = v["start"]
        return datetime.fromisoformat(start.replace("Z", "+00:00")) if "T" in start else start
    if kind == "relation":
        return sorted(p["id"].replace("-", "") for p in v)
    return v


def index_rows(existing):
    managed = {}
    for page in existing:
        key = text_value(page["properties"].get("同步鍵", {"type": "rich_text", "rich_text": []}))
        if not key.startswith(PREFIX):
            continue
        if key in managed:
            raise ValueError("Duplicate managed synchronization keys; reconcile before writing")
        managed[key] = page
    return managed


def reconcile(client, source_id, desired, existing):
    managed = index_rows(existing)
    counts = Counter(created=0, updated=0, deactivated=0, unchanged=0)
    now = datetime.now(timezone.utc).isoformat()
    for key, properties in desired.items():
        properties = properties | {"同步鍵": rich(key), "有效": {"checkbox": True}}
        page = managed.get(key)
        changes = {k: v for k, v in properties.items()
                   if not page or k not in page["properties"] or value(page["properties"][k]) != value(v)}
        if not changes:
            counts["unchanged"] += 1
            continue
        changes["最後更新"] = date(now)
        if page:
            client.update(page["id"], changes)
            counts["updated"] += 1
        else:
            client.create(source_id, properties | {"最後更新": date(now)})
            counts["created"] += 1
    # Retain obsolete derived records for inspection; never trash source or user rows.
    for key, page in managed.items():
        if key not in desired and page["properties"].get("有效", {}).get("checkbox"):
            client.update(page["id"], {"有效": {"checkbox": False}, "最後更新": date(now)})
            counts["deactivated"] += 1
    return dict(counts)


def verify_rows(desired, pages, *, profit=False):
    managed = index_rows(pages)
    active = {k: p for k, p in managed.items() if p["properties"].get("有效", {}).get("checkbox")}
    if set(active) != set(desired):
        raise RuntimeError("Post-sync verification: active keys differ")
    for key, properties in desired.items():
        actual = active[key]["properties"]
        if any(k not in actual or value(actual[k]) != value(v) for k, v in properties.items()):
            raise RuntimeError("Post-sync verification: saved values differ")
        if profit:
            expected = (properties["賣出金額"]["number"] - properties["買進成本"]["number"]
                        - properties["買進費用（含稅）"]["number"] - properties["賣出費用（含稅）"]["number"])
            got = actual.get("淨損益", {}).get("formula", {}).get("number")
        else:
            expected = properties["買進成本"]["number"] + properties["買進費用（含稅）"]["number"]
            got = actual.get("持有總成本", {}).get("formula", {}).get("number")
        if got is None or abs(got - expected) > .00001:
            raise RuntimeError("Post-sync verification: Notion formula result differs")


def source_signature(pages):
    return sorted((p["id"], p["last_edited_time"]) for p in pages)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write schema and derived records")
    parser.add_argument("--report", type=Path, help="write private financial summary to a local file")
    args = parser.parse_args()
    token = os.environ.get("NOTION_SECRET")
    if not token:
        raise ValueError("Missing NOTION_SECRET")
    ids = {key: str(uuid.UUID(os.environ[key])) for key in
           ("NOTION_TRADES_DATA_SOURCE_ID", "NOTION_PROFIT_DATA_SOURCE_ID", "NOTION_HOLDINGS_DATA_SOURCE_ID")}
    if len(set(ids.values())) != 3:
        raise ValueError("Source and destination data sources must be distinct")
    source, profit, holding = (ids[k] for k in ids)
    client = Client(token)
    pages = client.query_all(source)
    if not pages:
        raise ValueError("Source is empty; refusing to deactivate all derived records")
    result = calculate(parse_trades(pages))
    profit_rows, holding_rows = desired_rows(result)
    # Preflight both destinations before creating any schema or page.
    previous_profit, previous_holding = client.query_all(profit), client.query_all(holding)
    index_rows(previous_profit)
    index_rows(previous_holding)
    if args.report:
        summary = {"years": result["years"], "sale_count": len(result["sales"]),
                   "holdings": [{k: v for k, v in h.items() if k != "lots"} for h in result["holdings"]]}
        fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as out:
            json.dump(summary, out, ensure_ascii=False, indent=2, default=str)
    if args.apply:
        if source_signature(pages) != source_signature(client.query_all(source)):
            raise RuntimeError("Source changed during calculation; rerun with a stable source")
        ensure_schema(client, profit, profit_schema(source))
        ensure_schema(client, holding, holding_schema())
        counts = {"profit": reconcile(client, profit, profit_rows, previous_profit),
                  "holdings": reconcile(client, holding, holding_rows, previous_holding)}
        verify_rows(profit_rows, client.query_all(profit), profit=True)
        verify_rows(holding_rows, client.query_all(holding))
        print(json.dumps(counts | {"verified": True}))
    else:
        print("Dry run validated; no changes written. Use --apply to synchronize.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Row IDs aid correction; never print HTTP response bodies or financial data.
        message = str(error)
        if os.environ.get("GITHUB_ACTIONS"):
            import re
            message = re.sub(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", "[private row ID]", message)
        print(f"Sync failed: {message}", file=sys.stderr)
        sys.exit(1)
