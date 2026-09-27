"""Pure accounting; no network calls, credentials, or portfolio data."""
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

ZERO = Decimal(0)
CENT = Decimal("0.01")
TZ = ZoneInfo("Asia/Taipei")


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def text_value(prop):
    return "".join(p.get("plain_text", p.get("text", {}).get("content", ""))
                   for p in prop.get(prop.get("type", "rich_text"), []))


@dataclass(frozen=True)
class Trade:
    id: str
    name: str
    broker: str
    kind: str
    date: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    created: str = ""

    @property
    def code(self):
        return self.name.split()[0]

    @property
    def timestamp(self):
        value = datetime.fromisoformat(self.date.replace("Z", "+00:00"))
        return value.replace(tzinfo=TZ) if value.tzinfo is None else value.astimezone(TZ)

    @property
    def day(self):
        return self.timestamp.date().isoformat()

    @property
    def key(self):
        return self.broker, self.code


def parse_trades(pages):
    trades = []
    for page in pages:
        try:
            p = page["properties"]
            trade = Trade(
                id=page["id"], name=text_value(p["Name"]).strip(),
                broker=p["券商"]["select"]["name"], kind=p["交易"]["select"]["name"],
                date=p["時間"]["date"]["start"],
                quantity=Decimal(str(p["股數"]["number"])),
                price=Decimal(str(p["價格"]["number"])),
                fee=Decimal(str(p["手續費"]["number"])), created=page.get("created_time", ""),
            )
            valid = (trade.name and trade.broker and trade.kind in ("買入", "賣出")
                     and all(v.is_finite() for v in (trade.quantity, trade.price, trade.fee))
                     and trade.quantity > 0 and trade.quantity == trade.quantity.to_integral_value()
                     and trade.price >= 0 and trade.fee >= 0 and not p["時間"]["date"].get("end"))
            if not valid:
                raise ValueError("invalid trade")
            trade.timestamp  # Validate dates before any mutations.
        except Exception as exc:
            raise ValueError(f"Invalid source row {page.get('id', '(unknown)')}; check required fields") from exc
        trades.append(trade)
    if len({t.id for t in trades}) != len(trades):
        raise ValueError("Duplicate source page IDs")
    return trades


def calculate(trades):
    """FIFO within broker + security; input order does not affect the result.

    Same timestamp, same side: creation time then page ID breaks ties.
    Same-day mixed buy/sell without times is rejected instead of inventing order.
    """
    days = defaultdict(list)
    for trade in trades:
        days[(*trade.key, trade.day)].append(trade)
    for group in days.values():
        if len({t.kind for t in group}) > 1:
            if any("T" not in t.date for t in group):
                raise ValueError(f"Same-day buy/sell needs explicit transaction times: {group[0].id}")
            stamps = defaultdict(set)
            for t in group:
                stamps[t.timestamp].add(t.kind)
            if any(len(kinds) > 1 for kinds in stamps.values()):
                raise ValueError(f"Buy/sell order is ambiguous at the same timestamp: {group[0].id}")
    inventory = defaultdict(deque)
    sales = []
    for trade in sorted(trades, key=lambda t: (t.timestamp, t.created, t.id)):
        if trade.kind == "買入":
            inventory[trade.key].append({"trade": trade, "quantity": trade.quantity, "fee": trade.fee})
            continue
        remaining, basis, buy_fees = trade.quantity, ZERO, ZERO
        allocations = []
        while remaining and inventory[trade.key]:
            lot = inventory[trade.key][0]
            used = min(remaining, lot["quantity"])
            fee = lot["fee"] if used == lot["quantity"] else money(lot["fee"] * used / lot["quantity"])
            amount = used * lot["trade"].price
            allocations.append({"trade": lot["trade"], "quantity": used, "basis": amount, "fee": fee})
            basis += amount
            buy_fees += fee
            remaining -= used
            lot["quantity"] -= used
            lot["fee"] -= fee
            if not lot["quantity"]:
                inventory[trade.key].popleft()
        if remaining:
            raise ValueError(f"Sale exceeds recorded inventory: {trade.id}; add missing purchases or corporate actions")
        sale = {"trade": trade, "quantity": trade.quantity, "basis": money(basis),
                "buy_fees": money(buy_fees), "proceeds": money(trade.quantity * trade.price),
                "sell_fees": money(trade.fee), "allocations": allocations}
        sale["profit"] = sale["proceeds"] - sale["basis"] - sale["buy_fees"] - sale["sell_fees"]
        sales.append(sale)
    years = {}
    for sale in sales:
        year = sale["trade"].day[:4]
        annual = years.setdefault(year, dict.fromkeys(("basis", "buy_fees", "proceeds", "sell_fees", "profit"), ZERO)
                                 | {"count": 0, "wins": 0, "losses": 0})
        for key in ("basis", "buy_fees", "proceeds", "sell_fees", "profit"):
            annual[key] += sale[key]
        annual["count"] += 1
        annual["wins"] += sale["profit"] > 0
        annual["losses"] += sale["profit"] < 0
    holdings = []
    for (broker, code), lots in sorted(inventory.items()):
        if not lots:
            continue
        quantity = sum((lot["quantity"] for lot in lots), ZERO)
        basis = sum((lot["quantity"] * lot["trade"].price for lot in lots), ZERO)
        fees = sum((lot["fee"] for lot in lots), ZERO)
        holdings.append({"broker": broker, "code": code, "name": lots[-1]["trade"].name,
                         "quantity": quantity, "basis": money(basis), "buy_fees": money(fees),
                         "lots": list(lots), "first_date": lots[0]["trade"].date})
    return {"sales": sales, "years": years, "holdings": holdings}
