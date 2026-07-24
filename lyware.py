#!/usr/bin/env python3
"""
LYWARE — logic module (v4, importable)
======================================
DB layer + logic layer. No printing / no input(); the GUI and tests import this.

v4 adds: an inventory approval gate (shipping/in-person -> Pending Approval ->
Accept -> In Stock), multi-item sale orders (header/detail, atomized but grouped),
account hide/unhide (no deletion), business-expense recording, and a change_log
that records every data mutation.
"""

import os
import sqlite3
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "lyware.db")
SCHEMA_PATH = os.path.join(_HERE, "schema.sql")
Q = Decimal("0.0001")

ACCOUNT_CAPS = {
    "Cash":          {"internal_fx", "transfer_out", "transfer_in", "recharge_card", "cash_out_fx"},
    "Digital Funds": {"internal_fx", "transfer_out", "transfer_in", "recharge_card", "cash_out_fx"},
    "Card":          {"recharge_target", "spend_fx"},
}


class CapabilityError(Exception): pass
class InsufficientFX(Exception): pass
class InsufficientLYD(Exception): pass
class StateError(Exception): pass
class DuplicateCatalogItem(Exception): pass


# ---------------------------------------------------------------------------
# DB layer
# ---------------------------------------------------------------------------
def connect(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:                                   # WAL survives crashes better and never blocks readers
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        pass
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=DB_PATH, schema_path=SCHEMA_PATH):
    if os.path.exists(db_path):
        os.remove(db_path)
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"{schema_path} not found.")
    with open(schema_path, "r", encoding="utf-8") as fh:
        ddl = fh.read()
    conn = connect(db_path)
    conn.executescript(ddl)
    conn.commit()
    return conn


def open_or_create_db(db_path=DB_PATH, schema_path=SCHEMA_PATH):
    conn = connect(db_path)
    present = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='accounts'").fetchone()
    if not present:
        if not os.path.exists(schema_path):
            raise FileNotFoundError(f"{schema_path} not found.")
        with open(schema_path, "r", encoding="utf-8") as fh:
            conn.executescript(fh.read())
        conn.commit()
    _migrate(conn)
    return conn


def _migrate(conn):
    """Additive, idempotent column migrations for existing databases."""
    def has_col(table, col):
        return any(r["name"] == col for r in conn.execute(f"PRAGMA table_info({table})"))
    if not has_col("international_shipping", "date_picked_up"):
        conn.execute("ALTER TABLE international_shipping ADD COLUMN date_picked_up TEXT")
    if not has_col("catalog_items", "is_hidden"):
        conn.execute("ALTER TABLE catalog_items ADD COLUMN is_hidden INTEGER NOT NULL DEFAULT 0")
    if not has_col("catalog_items", "variant"):
        conn.execute("ALTER TABLE catalog_items ADD COLUMN variant TEXT NOT NULL DEFAULT 'A'")
        # one-time: give any pre-existing same-named items distinct labels A, B, C, ...
        fam = {}
        for r in conn.execute("SELECT catid, display_name FROM catalog_items ORDER BY catid"):
            fam.setdefault((r["display_name"] or "").strip().lower(), []).append(r["catid"])
        for members in fam.values():
            if len(members) > 1:
                for idx, cid in enumerate(members):
                    label = chr(ord("A") + idx) if idx < 26 else f"A{idx - 25}"
                    conn.execute("UPDATE catalog_items SET variant=? WHERE catid=?", (label, cid))
    if not has_col("inventory_items", "closure_recovery"):
        conn.execute("ALTER TABLE inventory_items ADD COLUMN closure_recovery NUMERIC NOT NULL DEFAULT 0")
    if not has_col("inventory_items", "closure_note"):
        conn.execute("ALTER TABLE inventory_items ADD COLUMN closure_note TEXT")
    if not has_col("inventory_items", "closure_date"):
        conn.execute("ALTER TABLE inventory_items ADD COLUMN closure_date TEXT")
    if not has_col("inventory_items", "condition"):
        conn.execute("ALTER TABLE inventory_items ADD COLUMN condition TEXT NOT NULL DEFAULT 'Used'")
    if not has_col("inventory_items", "cost_adjustment_trnsid"):
        conn.execute("ALTER TABLE inventory_items ADD COLUMN cost_adjustment_trnsid INTEGER "
                     "REFERENCES all_transactions(trnsid)")
    if not has_col("inventory_items", "condition_note"):
        conn.execute("ALTER TABLE inventory_items ADD COLUMN condition_note TEXT")
    if not has_col("all_listings", "listing_name"):
        conn.execute("ALTER TABLE all_listings ADD COLUMN listing_name TEXT")
    if not has_col("all_listings", "seller_link"):
        conn.execute("ALTER TABLE all_listings ADD COLUMN seller_link TEXT")
    if not has_col("all_listings", "is_archived"):
        conn.execute("ALTER TABLE all_listings ADD COLUMN is_archived INTEGER NOT NULL DEFAULT 0")
    conn.execute("CREATE TABLE IF NOT EXISTS market_rate_history ("
                 "mrid INTEGER PRIMARY KEY AUTOINCREMENT, rate REAL NOT NULL, "
                 "set_date TEXT NOT NULL, set_time TEXT NOT NULL)")
    # terminal exception statuses (recorded events, not mistakes — Phase 1 of the
    # user-error / exception stage). 'closed' stage keeps them out of pipeline counts.
    for status, desc in (
            ("Cancelled", "Order cancelled by seller / never shipped."),
            ("Written Off", "Scrapped — damaged or defective beyond use."),
            ("Returned to Seller", "Sent back to the seller."),
            ("Customer Returned", "Returned by the customer.")):
        conn.execute("INSERT OR IGNORE INTO inventory_statuses(status, stage, description) "
                     "VALUES(?, 'closed', ?)", (status, desc))
    for tp, cat, desc in (
            ("Refund_Received", "Expense", "Money back from a seller — offsets purchase expense."),
            ("Refund_Issued", "Revenue", "Money refunded to a customer — offsets sale revenue.")):
        conn.execute("INSERT OR IGNORE INTO transaction_types(type, category, affects_balance, "
                     "description) VALUES(?,?,1,?)", (tp, cat, desc))
    conn.commit()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def money(x): return Decimal(str(x)).quantize(Q, rounding=ROUND_HALF_UP)
def fl(d): return float(d)


def _positive(x, label="amount"):
    """Coerce to money and reject zero/negative — guards public money entry points so a
    negative figure can't silently flip a deposit into a withdrawal (or worse)."""
    a = money(x)
    if a <= 0:
        raise ValueError(f"{label} must be greater than zero")
    return a


def now():
    n = datetime.now()
    return n.strftime("%Y-%m-%d"), n.strftime("%H:%M:%S")


def _log(conn, action, entity, ref, detail=""):
    conn.execute("INSERT INTO change_log(action, entity, ref, detail) VALUES(?,?,?,?)",
                 (action, entity, str(ref), detail))


def account_type(conn, acctid):
    r = conn.execute("SELECT account_type FROM accounts WHERE acctid=?", (acctid,)).fetchone()
    if not r:
        raise ValueError(f"no account {acctid}")
    return r["account_type"]


def require_capability(conn, acctid, cap):
    at = account_type(conn, acctid)
    if cap not in ACCOUNT_CAPS.get(at, set()):
        raise CapabilityError(f"a '{at}' account is not allowed to: {cap}")


def _txn(conn, acctid, ttype, amount, currency, linked=None):
    d, t = now()
    cur = conn.execute(
        "INSERT INTO all_transactions(acctid,type,amount,currency,linked_transfer_id,date,time) "
        "VALUES(?,?,?,?,?,?,?)", (acctid, ttype, fl(amount), currency, linked, d, t))
    return cur.lastrowid


def _create_batch(conn, acctid, trnsid, currency, fx_amount, rate, source):
    d, _ = now()
    lyd_cost = money(fx_amount * rate)
    conn.execute(
        "INSERT INTO fx_batches(acctid,trnsid,currency,fx_amount,rate,lyd_cost,fx_remaining,source,date_acquired) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (acctid, trnsid, currency, fl(fx_amount), fl(rate), fl(lyd_cost), fl(fx_amount), source, d))
    return lyd_cost


def _fifo_consume(conn, acctid, currency, fx_total, trnsid):
    remaining, total_lyd = money(fx_total), Decimal("0")
    rows = conn.execute(
        "SELECT bachid, fx_remaining, rate FROM fx_batches "
        "WHERE acctid=? AND currency=? AND fx_remaining > 0 ORDER BY bachid ASC",
        (acctid, currency)).fetchall()
    for b in rows:
        if remaining <= 0:
            break
        avail, rate = money(b["fx_remaining"]), money(b["rate"])
        take = avail if avail < remaining else remaining
        lyd = money(take * rate)
        conn.execute(
            "INSERT INTO batch_allocations(trnsid,bachid,fx_consumed,rate_applied,lyd_allocated) "
            "VALUES(?,?,?,?,?)", (trnsid, b["bachid"], fl(take), fl(rate), fl(lyd)))
        conn.execute("UPDATE fx_batches SET fx_remaining=? WHERE bachid=?",
                     (fl(money(avail - take)), b["bachid"]))
        remaining = money(remaining - take)
        total_lyd += lyd
    if remaining > 0:
        raise InsufficientFX(f"short by {remaining} {currency} on account {acctid}")
    return money(total_lyd)


def _apportion(total_lyd, unit_prices):
    prices = [money(p) for p in unit_prices]
    grand = sum(prices, Decimal("0"))
    out, running = [], Decimal("0")
    for i, p in enumerate(prices):
        if i < len(prices) - 1:
            share = money(total_lyd * (p / grand)); out.append(share); running += share
        else:
            out.append(money(total_lyd - running))
    return out


def _spend_fx_or_lyd(conn, acctid, ttype, amount, currency):
    amount = money(amount)
    if currency == "LYD":
        if lyd_balance(conn, acctid) < amount:
            raise InsufficientLYD(f"account {acctid} cannot afford {amount} LYD")
        trnsid = _txn(conn, acctid, ttype, -amount, "LYD")
        return trnsid, amount
    trnsid = _txn(conn, acctid, ttype, -amount, currency)
    lyd_cost = _fifo_consume(conn, acctid, currency, amount, trnsid)
    return trnsid, lyd_cost


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
def add_account(conn, name, account_type_):
    if account_type_ not in ACCOUNT_CAPS:
        raise ValueError(f"unknown account type {account_type_}")
    cur = conn.execute("INSERT INTO accounts(account_name, account_type) VALUES(?,?)",
                       (name, account_type_))
    _log(conn, "INSERT", "account", cur.lastrowid, f"{name} ({account_type_})")
    conn.commit()
    return cur.lastrowid


def list_accounts(conn, account_type_=None, include_hidden=False):
    q, args = "SELECT * FROM accounts WHERE 1=1", []
    if account_type_:
        q += " AND account_type=?"; args.append(account_type_)
    if not include_hidden:
        q += " AND is_hidden=0"
    return conn.execute(q + " ORDER BY acctid", args).fetchall()


def hide_account(conn, acctid):
    conn.execute("UPDATE accounts SET is_hidden=1 WHERE acctid=?", (acctid,))
    _log(conn, "UPDATE", "account", acctid, "hidden")
    conn.commit()


def unhide_account(conn, acctid):
    conn.execute("UPDATE accounts SET is_hidden=0 WHERE acctid=?", (acctid,))
    _log(conn, "UPDATE", "account", acctid, "unhidden")
    conn.commit()


def deposit_lyd(conn, acctid, lyd_amount):
    amt = _positive(lyd_amount, "deposit")
    tid = _txn(conn, acctid, "Deposit", amt, "LYD")
    _log(conn, "INSERT", "transaction", tid, f"Deposit {amt} LYD -> acct {acctid}")
    conn.commit(); return tid


def withdraw_lyd(conn, acctid, lyd_amount):
    amt = _positive(lyd_amount, "withdrawal")
    if lyd_balance(conn, acctid) < amt:
        raise InsufficientLYD(f"account {acctid} has less than {amt} LYD")
    tid = _txn(conn, acctid, "Withdrawal", -amt, "LYD")
    _log(conn, "INSERT", "transaction", tid, f"Withdraw {amt} LYD <- acct {acctid}")
    conn.commit(); return tid


def convert_buy(conn, acctid, currency, fx_amount, rate):
    fx_amount, rate = _positive(fx_amount, "USD amount"), _positive(rate, "rate")
    require_capability(conn, acctid, "internal_fx")
    fx_amount, rate = money(fx_amount), money(rate)
    lyd_cost = money(fx_amount * rate)
    if lyd_balance(conn, acctid) < lyd_cost:
        raise InsufficientLYD(f"account {acctid} cannot afford {lyd_cost} LYD")
    trnsid = _txn(conn, acctid, "Conversion_Buy", -lyd_cost, "LYD")
    _create_batch(conn, acctid, trnsid, currency, fx_amount, rate, "Conversion")
    _log(conn, "INSERT", "conversion", trnsid, f"Buy {fx_amount} {currency} @ {rate} on acct {acctid}")
    conn.commit(); return trnsid


def recharge_card(conn, funding_acctid, card_acctid, currency, fx_amount, rate=None, lyd_paid=None):
    """Recharge a card with FX. Supply EITHER `rate` (LYD per unit) OR `lyd_paid` (the
    exact LYD the seller charged); when `lyd_paid` is given the rate is derived from it,
    so the recorded LYD cost matches what you actually paid (covers seller rounding /
    adjustments like 1104.9 vs 1105)."""
    require_capability(conn, funding_acctid, "recharge_card")
    require_capability(conn, card_acctid, "recharge_target")
    fx_amount = _positive(fx_amount, "USD amount")
    if lyd_paid is not None and str(lyd_paid).strip() != "":
        lyd_cost = _positive(lyd_paid, "LYD paid")
        rate = money(lyd_cost / fx_amount)
    else:
        if rate is None or str(rate).strip() == "":
            raise ValueError("enter either a rate or the LYD amount paid")
        rate = _positive(rate, "rate")
        lyd_cost = money(fx_amount * rate)
    if lyd_balance(conn, funding_acctid) < lyd_cost:
        raise InsufficientLYD(f"funding account {funding_acctid} cannot afford {lyd_cost} LYD")
    trnsid = _txn(conn, funding_acctid, "Recharge", -lyd_cost, "LYD")
    _create_batch(conn, card_acctid, trnsid, currency, fx_amount, rate, "Recharge")
    _log(conn, "INSERT", "recharge", trnsid,
         f"Recharge card {card_acctid} with {fx_amount} {currency} @ {rate} "
         f"(cost {lyd_cost} LYD, funded by {funding_acctid})")
    conn.commit(); return trnsid


def convert_sell(conn, acctid, currency, fx_amount, sell_rate):
    fx_amount, sell_rate = _positive(fx_amount, "USD amount"), _positive(sell_rate, "rate")
    require_capability(conn, acctid, "cash_out_fx")
    fx_amount, sell_rate = money(fx_amount), money(sell_rate)
    proceeds = money(fx_amount * sell_rate)
    try:
        trnsid = _txn(conn, acctid, "Conversion_Sell", proceeds, "LYD")
        cost_basis = _fifo_consume(conn, acctid, currency, fx_amount, trnsid)
        fx = money(proceeds - cost_basis)
        _txn(conn, acctid, "FX_Gain_Loss", fx, "LYD", linked=trnsid)
        _log(conn, "INSERT", "conversion", trnsid,
             f"Sell {fx_amount} {currency} @ {sell_rate}; FX g/l {fx} LYD")
        conn.commit(); return trnsid, proceeds, cost_basis, fx
    except Exception:
        conn.rollback(); raise


def transfer_lyd(conn, src_acctid, dst_acctid, amount, fee=0):
    require_capability(conn, src_acctid, "transfer_out")
    require_capability(conn, dst_acctid, "transfer_in")
    amount, fee = money(amount), money(fee)
    if fee < 0 or fee > amount:
        raise ValueError("fee must be between 0 and the transfer amount")
    if lyd_balance(conn, src_acctid) < amount:
        raise InsufficientLYD(f"source {src_acctid} has less than {amount} LYD")
    net = money(amount - fee)
    try:
        out_id = _txn(conn, src_acctid, "Transfer", -net, "LYD")
        in_id = _txn(conn, dst_acctid, "Transfer", net, "LYD", linked=out_id)
        conn.execute("UPDATE all_transactions SET linked_transfer_id=? WHERE trnsid=?", (in_id, out_id))
        if fee > 0:
            _txn(conn, src_acctid, "Transfer_Fee", -fee, "LYD", linked=out_id)
        _log(conn, "INSERT", "transfer", out_id,
             f"{amount} LYD {src_acctid}->{dst_acctid} (fee {fee})")
        conn.commit(); return out_id, in_id
    except Exception:
        conn.rollback(); raise


def record_business_expense(conn, acctid, amount, currency, category=None, description=None):
    amount = _positive(amount, "expense amount")
    at = account_type(conn, acctid)
    if at in ("Cash", "Digital Funds") and currency != "LYD":
        raise ValueError("Cash/Digital business expenses must be in LYD")
    if at == "Card" and currency == "LYD":
        raise ValueError("Card business expenses are in foreign currency")
    try:
        trnsid, lyd = _spend_fx_or_lyd(conn, acctid, "Business_Expense", amount, currency)
        d, _ = now()
        conn.execute("INSERT INTO business_expenses(trnsid,category,description,date) VALUES(?,?,?,?)",
                     (trnsid, category, description, d))
        _log(conn, "INSERT", "business_expense", trnsid,
             f"{category or 'expense'}: {money(amount)} {currency} (={lyd} LYD)")
        conn.commit(); return trnsid
    except Exception:
        conn.rollback(); raise


# ---------------------------------------------------------------------------
# Purchases
# ---------------------------------------------------------------------------
def record_purchase(conn, acctid, vendor, currency, items, lsid=None, delivery_method=None,
                    purchaser_name=None, shipping_cost=None, shipping_acct=None, shipping_currency=None):
    # each item may carry a catalogue link (catid); name defaults to the catalogue display name.
    norm = []
    for it in items:
        catid = it.get("catid")
        name = it.get("name")
        if not name and catid:
            ci = get_catalog_item(conn, catid)
            name = ci["item"]["display_name"] if ci else None
        if not name:
            raise ValueError("each purchase item needs a name or a catid")
        norm.append({"catid": catid, "name": name, "unit_price": it["unit_price"],
                     "serial": it.get("serial"),
                     "condition": (it.get("condition") or "Used"),
                     "condition_note": (it.get("condition_note") or None)})
    items = norm
    total = money(sum(money(i["unit_price"]) for i in items))
    # in-person items land straight in the approval queue; shipped items start the pipeline
    initial_status = "Pending Approval" if delivery_method == "In-Person" else "Awaiting Shipment"
    d, _ = now()
    try:
        if currency == "LYD" and lyd_balance(conn, acctid) < total:
            raise InsufficientLYD(f"account {acctid} cannot afford {total} LYD")
        trnsid = _txn(conn, acctid, "Purchase", -total, currency)
        if currency == "LYD":
            per_item, lyd_total = [money(i["unit_price"]) for i in items], total
        else:
            lyd_total = _fifo_consume(conn, acctid, currency, total, trnsid)
            per_item = _apportion(lyd_total, [i["unit_price"] for i in items])
        cur = conn.execute(
            "INSERT INTO purchase_orders(trnsid,vendor_name,purchaser_name,order_date,total_paid,currency,delivery_method,lsid) "
            "VALUES(?,?,?,?,?,?,?,?)", (trnsid, vendor, purchaser_name, d, fl(total), currency,
                                       delivery_method, lsid))
        poid = cur.lastrowid
        out_items = []
        for i, it in enumerate(items):
            cur = conn.execute(
                "INSERT INTO purchase_lines(poid,lsid,catid,item_name,unit_price_allocated,currency) "
                "VALUES(?,?,?,?,?,?)", (poid, lsid, it["catid"], it["name"],
                                       fl(money(it["unit_price"])), currency))
            polnid = cur.lastrowid
            cur = conn.execute(
                "INSERT INTO inventory_items(polnid,catid,serial_number,lyd_cost_basis,status,"
                "condition,condition_note) VALUES(?,?,?,?,?,?,?)",
                (polnid, it["catid"], it.get("serial"), fl(per_item[i]), initial_status,
                 it.get("condition") or "Used", it.get("condition_note")))
            out_items.append({"polnid": polnid, "lywrid": cur.lastrowid,
                              "name": it["name"], "lyd_cost_basis": per_item[i]})
        # M5: shipped items start grouped together in one shipment (splittable later)
        ship_lywrids = [oi["lywrid"] for oi in out_items]
        shipid = None
        if delivery_method in ("International", "Local") and ship_lywrids:
            stype = "International" if delivery_method == "International" else "Local"
            shipid = conn.execute("INSERT INTO shipments(shipment_type) VALUES(?)", (stype,)).lastrowid
            if stype == "International":
                conn.execute("INSERT INTO international_shipping(shipid) VALUES(?)", (shipid,))
            else:
                conn.execute("INSERT INTO local_shipping(shipid) VALUES(?)", (shipid,))
            for lid in ship_lywrids:
                conn.execute("INSERT INTO shipment_items(shipid,lywrid) VALUES(?,?)", (shipid, lid))
            # M9/M10: international shipping cost entered at purchase is paid immediately
            if stype == "International" and shipping_cost not in (None, "", 0, "0") \
                    and shipping_acct is not None:
                _apply_shipping_payment(conn, shipid, shipping_acct, shipping_cost,
                                        shipping_currency or currency)
        _log(conn, "INSERT", "purchase", poid,
             f"{len(items)} item(s) from {vendor}, {total} {currency}, {delivery_method}")
        conn.commit()
        return {"poid": poid, "trnsid": trnsid, "lyd_cost_total": lyd_total, "items": out_items,
                "shipid": shipid}
    except Exception:
        conn.rollback(); raise


# ---------------------------------------------------------------------------
# Inbound shipping state machine
# ---------------------------------------------------------------------------
def get_item_status(conn, lywrid):
    r = conn.execute("SELECT status FROM inventory_items WHERE lywrid=?", (lywrid,)).fetchone()
    if not r:
        raise ValueError(f"no inventory item {lywrid}")
    return r["status"]


def set_item_condition(conn, lywrid, condition, condition_note=None):
    """Set a unit's condition ('Used'/'Unused') and free-text note (e.g. 'Grade A', 'open box').
    Per-unit only — it never affects catalogue identity or report grouping."""
    condition = (condition or "Used").strip().title()
    if condition not in ("Used", "Unused"):
        raise ValueError("condition must be 'Used' or 'Unused'")
    if not conn.execute("SELECT 1 FROM inventory_items WHERE lywrid=?", (lywrid,)).fetchone():
        raise ValueError(f"no inventory item {lywrid}")
    conn.execute("UPDATE inventory_items SET condition=?, condition_note=? WHERE lywrid=?",
                 (condition, (condition_note or None), lywrid))
    _log(conn, "UPDATE", "inventory_item", lywrid, f"condition -> {condition} ({condition_note or '-'})")
    conn.commit()


def _shipment_peers(conn, lywrid, shipment_type, status):
    """The items sharing the most-recent shipment of `shipment_type` with `lywrid`,
    restricted to those currently in `status`. Returns (lywrids, shipid).
    Used to make every shipping transition act on the WHOLE group, not one item.
    Falls back to ([lywrid], None) when the item has no such shipment."""
    row = conn.execute(
        "SELECT s.shipid FROM shipment_items si JOIN shipments s ON si.shipid=s.shipid "
        "WHERE si.lywrid=? AND s.shipment_type=? ORDER BY s.shipid DESC LIMIT 1",
        (lywrid, shipment_type)).fetchone()
    if not row:
        return [lywrid], None
    shipid = row["shipid"]
    members = [r["lywrid"] for r in conn.execute(
        "SELECT lywrid FROM shipment_items WHERE shipid=?", (shipid,))]
    grp = [m for m in members if get_item_status(conn, m) == status]
    return (grp or [lywrid]), shipid


def _item_shipping_shares(conn, lywrid):
    """Per-item apportioned shipping cost across every shipment the item belongs to.
    Each shipment's recorded LYD cost is split evenly over the items in that shipment;
    international legs are summed separately from local legs. Returns (intl_lyd, local_lyd).
    This is the single source of truth for shipping cost — both the cost breakdown and
    the freeze-at-acceptance path use it, so they can never diverge.

    The split is penny-exact: shares are rounded per item, and the last item in each
    shipment absorbs the rounding remainder so the per-item shares sum to the shipment
    cost exactly (no sub-cent drift creeping into a frozen cost basis)."""
    intl = Decimal("0"); local = Decimal("0")
    for r in conn.execute(
            "SELECT s.shipid, s.shipment_type, COALESCE(s.lyd_shipping_cost,0) AS c "
            "FROM shipment_items si JOIN shipments s ON si.shipid=s.shipid WHERE si.lywrid=?", (lywrid,)):
        ids = [x["lywrid"] for x in conn.execute(
            "SELECT lywrid FROM shipment_items WHERE shipid=? ORDER BY lywrid", (r["shipid"],))]
        n = len(ids)
        if not n:
            continue
        cost = money(Decimal(str(r["c"])))
        even = money(cost / Decimal(n))
        # the last item (largest lywrid) carries the remainder so shares sum to `cost`
        share = (cost - even * (n - 1)) if lywrid == ids[-1] else even
        if r["shipment_type"] == "International":
            intl += share
        else:
            local += share
    return money(intl), money(local)


def _require_status(conn, lywrid, allowed):
    s = get_item_status(conn, lywrid)
    if s not in allowed:
        raise StateError(f"item {lywrid} is '{s}'; expected one of {sorted(allowed)}")
    return s


def _set_status(conn, lywrid, status):
    conn.execute("UPDATE inventory_items SET status=? WHERE lywrid=?", (status, lywrid))
    _log(conn, "STATUS", "inventory_item", lywrid, f"-> {status}")


def start_international_shipment(conn, target, tracking_number=None, freight_forwarder_name=None,
                                 flight_number=None, weight_kg=None):
    """Start (enter tracking and move to transit) an international shipment.
    `target` may be an existing shipid (int) or a list of lywrids (their shipment is
    found, or created if somehow missing)."""
    if isinstance(target, int):
        shipid = target
        items = [r["lywrid"] for r in conn.execute(
            "SELECT lywrid FROM shipment_items WHERE shipid=?", (shipid,))]
        for lid in items:
            _require_status(conn, lid, {"Awaiting Shipment"})
    else:
        lst = list(target)
        for lid in lst:                                   # validate before building anything
            _require_status(conn, lid, {"Awaiting Shipment"})
        row = conn.execute(
            "SELECT s.shipid FROM shipments s JOIN shipment_items si ON si.shipid=s.shipid "
            "WHERE s.shipment_type='International' AND si.lywrid=? LIMIT 1", (lst[0],)).fetchone()
        if row:
            shipid = row["shipid"]
        else:
            shipid = conn.execute("INSERT INTO shipments(shipment_type) VALUES('International')").lastrowid
            conn.execute("INSERT INTO international_shipping(shipid) VALUES(?)", (shipid,))
            for lid in lst:
                conn.execute("INSERT INTO shipment_items(shipid,lywrid) VALUES(?,?)", (shipid, lid))
        items = [r["lywrid"] for r in conn.execute(
            "SELECT lywrid FROM shipment_items WHERE shipid=?", (shipid,))]
        for lid in items:
            _require_status(conn, lid, {"Awaiting Shipment"})
    try:
        conn.execute(
            "UPDATE international_shipping SET tracking_number=COALESCE(?,tracking_number), "
            "freight_forwarder_name=COALESCE(?,freight_forwarder_name), "
            "flight_number=COALESCE(?,flight_number), weight_kg=COALESCE(?,weight_kg) WHERE shipid=?",
            (tracking_number, freight_forwarder_name, flight_number, weight_kg, shipid))
        for lid in items:
            _set_status(conn, lid, "International Transit")
        _log(conn, "UPDATE", "shipment", shipid, f"international started, {len(items)} item(s)")
        conn.commit(); return shipid
    except Exception:
        conn.rollback(); raise


def split_shipment(conn, shipid, lywrids):
    """M5: move some pre-transit items out of a shipment into a new shipment of the same type.
    Allowed only while the items are still 'Awaiting Shipment'. The recorded shipping cost is
    apportioned by item count so that EACH item keeps the same per-item share it had before the
    split (cost = total / item-count, preserved through to acceptance)."""
    stype = conn.execute("SELECT shipment_type FROM shipments WHERE shipid=?", (shipid,)).fetchone()
    if not stype:
        raise StateError("no such shipment")
    stype = stype["shipment_type"]
    for lid in lywrids:
        _require_status(conn, lid, {"Awaiting Shipment"})
        owns = conn.execute("SELECT 1 FROM shipment_items WHERE shipid=? AND lywrid=?",
                            (shipid, lid)).fetchone()
        if not owns:
            raise StateError(f"item {lid} is not in shipment {shipid}")
    orig_count = conn.execute("SELECT COUNT(*) AS n FROM shipment_items WHERE shipid=?",
                              (shipid,)).fetchone()["n"]
    moved = len(lywrids)
    if moved >= orig_count:
        raise StateError("a split must leave at least one item in the original shipment")
    sh = conn.execute("SELECT shipping_cost, shipping_cost_currency, lyd_shipping_cost, "
                      "shipping_paid_trnsid FROM shipments WHERE shipid=?", (shipid,)).fetchone()
    new_ship = conn.execute("INSERT INTO shipments(shipment_type) VALUES(?)", (stype,)).lastrowid
    if stype == "International":
        src = conn.execute("SELECT tracking_number, freight_forwarder_name, flight_number, weight_kg, "
                           "date_arrived_us_warehouse, date_arrived_libya_warehouse, date_picked_up "
                           "FROM international_shipping WHERE shipid=?", (shipid,)).fetchone()
        conn.execute("INSERT INTO international_shipping(shipid, tracking_number, freight_forwarder_name, "
                     "flight_number, weight_kg, date_arrived_us_warehouse, date_arrived_libya_warehouse, "
                     "date_picked_up) VALUES(?,?,?,?,?,?,?,?)",
                     (new_ship, src["tracking_number"], src["freight_forwarder_name"], src["flight_number"],
                      src["weight_kg"], src["date_arrived_us_warehouse"],
                      src["date_arrived_libya_warehouse"], src["date_picked_up"]))
    else:
        src = conn.execute("SELECT shipping_office_name, date_shipped, date_arrived_local_office "
                           "FROM local_shipping WHERE shipid=?", (shipid,)).fetchone()
        conn.execute("INSERT INTO local_shipping(shipid, shipping_office_name, date_shipped, "
                     "date_arrived_local_office) VALUES(?,?,?,?)",
                     (new_ship, src["shipping_office_name"] if src else None,
                      src["date_shipped"] if src else None,
                      src["date_arrived_local_office"] if src else None))
    for lid in lywrids:
        conn.execute("UPDATE shipment_items SET shipid=? WHERE shipid=? AND lywrid=?",
                     (new_ship, shipid, lid))
    # carve the shipping cost: new box gets share*moved, original keeps the exact remainder
    def _carve(value):
        if value is None:
            return None, None
        total = Decimal(str(value))
        new_part = money(total / Decimal(orig_count) * Decimal(moved))
        rem_part = money(total - new_part)        # exact complement conserves the total
        return new_part, rem_part
    new_lyd, rem_lyd = _carve(sh["lyd_shipping_cost"])
    new_fx, rem_fx = _carve(sh["shipping_cost"])
    if sh["lyd_shipping_cost"] is not None:
        conn.execute(
            "UPDATE shipments SET shipping_cost=?, shipping_cost_currency=?, lyd_shipping_cost=?, "
            "shipping_paid_trnsid=? WHERE shipid=?",
            (fl(new_fx) if new_fx is not None else None, sh["shipping_cost_currency"],
             fl(new_lyd), sh["shipping_paid_trnsid"], new_ship))
        conn.execute(
            "UPDATE shipments SET shipping_cost=?, lyd_shipping_cost=? WHERE shipid=?",
            (fl(rem_fx) if rem_fx is not None else None, fl(rem_lyd), shipid))
    _log(conn, "UPDATE", "shipment", new_ship,
         f"split {moved} item(s) from shipment {shipid}; cost share moved {new_lyd}")
    conn.commit(); return new_ship


def update_international_shipment(conn, shipid, **fields):
    allowed = {"tracking_number", "freight_forwarder_name", "flight_number", "weight_kg"}
    cols = {k: v for k, v in fields.items() if k in allowed}
    if cols:
        sets = ", ".join(f"{k}=?" for k in cols)
        conn.execute(f"UPDATE international_shipping SET {sets} WHERE shipid=?", (*cols.values(), shipid))
        conn.commit()


def mark_arrived_us_warehouse(conn, shipid, date):
    conn.execute("UPDATE international_shipping SET date_arrived_us_warehouse=? WHERE shipid=?", (date, shipid))
    _log(conn, "UPDATE", "shipment", shipid, f"arrived US warehouse {date}")
    conn.commit()


def mark_arrived_libya_warehouse(conn, shipid, date):
    conn.execute("UPDATE international_shipping SET date_arrived_libya_warehouse=? WHERE shipid=?", (date, shipid))
    for r in conn.execute("SELECT lywrid FROM shipment_items WHERE shipid=?", (shipid,)).fetchall():
        if get_item_status(conn, r["lywrid"]) == "International Transit":
            _set_status(conn, r["lywrid"], "At Libya Warehouse")
    _log(conn, "UPDATE", "shipment", shipid, f"arrived Libya warehouse {date}")
    conn.commit()


def start_local_shipment(conn, lywrids, shipping_office_name=None, date_shipped=None,
                         cost=None, paying_acctid=None, currency="LYD"):
    """Start a local leg for the WHOLE group, not just the highlighted item. Items are
    resolved to their full shipment group:
      - International -> local: every sibling currently 'At Libya Warehouse' moves together
        into one new Local shipment (they stay in the international shipment too, so the
        international cost share is retained).
      - Local-delivery purchase: the items already share a pre-transit Local shipment, which
        is reused.
    Any cost is charged immediately (every leg is paid up front), and the whole thing rolls
    back if the payment fails."""
    first = lywrids[0]
    st = get_item_status(conn, first)
    if st == "At Libya Warehouse":
        grp, _ = _shipment_peers(conn, first, "International", "At Libya Warehouse")
    elif st == "Awaiting Shipment":
        grp, _ = _shipment_peers(conn, first, "Local", "Awaiting Shipment")
    else:
        grp = list(lywrids)
    grp = list(dict.fromkeys(list(grp) + list(lywrids)))     # union, stable order
    for lid in grp:
        _require_status(conn, lid, {"At Libya Warehouse", "Awaiting Shipment"})
    try:
        existing = conn.execute(
            "SELECT s.shipid FROM shipments s JOIN shipment_items si ON si.shipid=s.shipid "
            "WHERE s.shipment_type='Local' AND si.lywrid=? LIMIT 1", (first,)).fetchone()
        if existing and get_item_status(conn, first) == "Awaiting Shipment":
            shipid = existing["shipid"]
            conn.execute("UPDATE local_shipping SET shipping_office_name=COALESCE(?,shipping_office_name), "
                         "date_shipped=COALESCE(?,date_shipped) WHERE shipid=?",
                         (shipping_office_name, date_shipped, shipid))
        else:
            shipid = conn.execute("INSERT INTO shipments(shipment_type) VALUES('Local')").lastrowid
            conn.execute("INSERT INTO local_shipping(shipid,shipping_office_name,date_shipped) VALUES(?,?,?)",
                         (shipid, shipping_office_name, date_shipped))
            for lid in grp:
                if not conn.execute("SELECT 1 FROM shipment_items WHERE shipid=? AND lywrid=?",
                                    (shipid, lid)).fetchone():
                    conn.execute("INSERT INTO shipment_items(shipid,lywrid) VALUES(?,?)", (shipid, lid))
        for lid in grp:
            _set_status(conn, lid, "Local Transit")
        if cost not in (None, "", 0, "0") and paying_acctid is not None:
            _apply_shipping_payment(conn, shipid, paying_acctid, cost, currency)
        _log(conn, "INSERT", "shipment", shipid, f"local, {len(grp)} item(s)")
        conn.commit(); return shipid
    except Exception:
        conn.rollback(); raise


def mark_arrived_local_office(conn, shipid, date):
    conn.execute("UPDATE local_shipping SET date_arrived_local_office=? WHERE shipid=?", (date, shipid))
    for r in conn.execute("SELECT lywrid FROM shipment_items WHERE shipid=?", (shipid,)).fetchall():
        if get_item_status(conn, r["lywrid"]) == "Local Transit":
            _set_status(conn, r["lywrid"], "At Local Office")
    _log(conn, "UPDATE", "shipment", shipid, f"arrived local office {date}")
    conn.commit()


def _apply_shipping_payment(conn, shipid, paying_acctid, cost, currency):
    """Charge a shipping leg immediately (no commit). ADDITIVE: if the leg already has a
    recorded cost (e.g. shipping paid at purchase), this adds to it rather than replacing it,
    so additional/subsequent costs on the same leg can be recorded. Returns the LYD charged."""
    trnsid, lyd_cost = _spend_fx_or_lyd(conn, paying_acctid, "Shipping_Expense", cost, currency)
    cur = conn.execute("SELECT shipping_cost, shipping_cost_currency, lyd_shipping_cost, "
                       "shipping_paid_trnsid FROM shipments WHERE shipid=?", (shipid,)).fetchone()
    had = cur["lyd_shipping_cost"] is not None
    prev_lyd = Decimal(str(cur["lyd_shipping_cost"])) if had else Decimal("0")
    new_lyd = money(prev_lyd + lyd_cost)
    if not had:                                   # first payment on this leg
        disp_cost, disp_cur = money(cost), currency
    elif cur["shipping_cost_currency"] == currency and cur["shipping_cost"] is not None:
        disp_cost, disp_cur = money(Decimal(str(cur["shipping_cost"])) + money(cost)), currency
    else:                                         # mixed currencies — LYD total is the source of truth
        disp_cost, disp_cur = None, None
    keep_trns = cur["shipping_paid_trnsid"] or trnsid
    conn.execute(
        "UPDATE shipments SET shipping_cost=?, shipping_cost_currency=?, lyd_shipping_cost=?, "
        "shipping_paid_trnsid=? WHERE shipid=?",
        (fl(disp_cost) if disp_cost is not None else None, disp_cur, fl(new_lyd), keep_trns, shipid))
    _log(conn, "INSERT", "shipping_payment", shipid,
         f"{money(cost)} {currency} (={lyd_cost} LYD){' [added]' if had else ''}")
    return lyd_cost


def pay_shipping(conn, shipid, paying_acctid, cost, currency):
    try:
        lyd = _apply_shipping_payment(conn, shipid, paying_acctid, cost, currency)
        conn.commit(); return lyd
    except Exception:
        conn.rollback(); raise


def receive_at_shop(conn, lywrid, date):
    """From the local office into the approval queue — promotes the WHOLE local group that
    arrived together (does NOT freeze cost yet)."""
    _require_status(conn, lywrid, {"At Local Office"})
    grp, shipid = _shipment_peers(conn, lywrid, "Local", "At Local Office")
    for lid in grp:
        _set_status(conn, lid, "Pending Approval")
    if shipid:
        conn.execute("UPDATE shipments SET date_arrived_shop=? WHERE shipid=?", (date, shipid))
    _log(conn, "STATUS", "shipment", shipid or lywrid, f"received at shop -> approval, {len(grp)} item(s)")
    conn.commit()


def pickup_to_shop(conn, lywrid, date):
    """Branch (c): personal pickup from the Libya warehouse into the approval queue —
    promotes the WHOLE international group that arrived together. Records the pickup date."""
    _require_status(conn, lywrid, {"At Libya Warehouse"})
    grp, shipid = _shipment_peers(conn, lywrid, "International", "At Libya Warehouse")
    for lid in grp:
        _set_status(conn, lid, "Pending Approval")
    if shipid:
        conn.execute("UPDATE international_shipping SET date_picked_up=COALESCE(date_picked_up,?) "
                     "WHERE shipid=?", (date, shipid))
    _log(conn, "STATUS", "shipment", shipid or lywrid, f"picked up -> approval, {len(grp)} item(s)")
    conn.commit()


# ---------------------------------------------------------------------------
# Approval gate -> inventory (freezes total cost here)
# ---------------------------------------------------------------------------
def _item_shipping_cost_lyd(conn, lywrid):
    intl, local = _item_shipping_shares(conn, lywrid)
    return money(intl + local)


def item_shipping_dates(conn, lywrid):
    """M3: the milestone dates for one item across its international and local legs."""
    d = {"us_warehouse": None, "libya_warehouse": None, "picked_up": None,
         "local_sent": None, "local_office": None}
    intl = conn.execute(
        "SELECT i.date_arrived_us_warehouse, i.date_arrived_libya_warehouse, i.date_picked_up "
        "FROM shipment_items si JOIN shipments s ON si.shipid=s.shipid "
        "JOIN international_shipping i ON i.shipid=s.shipid "
        "WHERE si.lywrid=? AND s.shipment_type='International' ORDER BY s.shipid DESC LIMIT 1",
        (lywrid,)).fetchone()
    if intl:
        d["us_warehouse"] = intl["date_arrived_us_warehouse"]
        d["libya_warehouse"] = intl["date_arrived_libya_warehouse"]
        d["picked_up"] = intl["date_picked_up"]
    loc = conn.execute(
        "SELECT l.date_shipped, l.date_arrived_local_office "
        "FROM shipment_items si JOIN shipments s ON si.shipid=s.shipid "
        "JOIN local_shipping l ON l.shipid=s.shipid "
        "WHERE si.lywrid=? AND s.shipment_type='Local' ORDER BY s.shipid DESC LIMIT 1",
        (lywrid,)).fetchone()
    if loc:
        d["local_sent"] = loc["date_shipped"]
        d["local_office"] = loc["date_arrived_local_office"]
    return d


def accept_into_inventory(conn, lywrid, date, cost_adjustment=0, cost_adjustment_note=None):
    """Pending Approval -> In Stock. Optionally records a per-item cost adjustment (M7),
    then freezes total_cost (basis + adjustment + shipping share)."""
    _require_status(conn, lywrid, {"Pending Approval"})
    adj = money(cost_adjustment or 0)
def accept_into_inventory(conn, lywrid, date, cost_adjustment=0, cost_adjustment_note=None,
                          adjustment_acctid=None, adjustment_currency="LYD", adjustment_rate=None):
    """Pending Approval -> In Stock, freezing total_cost (basis + adjustment + shipping).

    A cost adjustment now optionally moves real money. When `adjustment_acctid` is given:
      * a POSITIVE adjustment is an EXPENSE — `cost_adjustment` (in `adjustment_currency`) is
        spent from that account (FIFO for FX), and the item's cost rises by the LYD spent.
      * a NEGATIVE adjustment is a REFUND — the amount is credited back to that account; for
        an FX account it lands as a fresh batch valued at `adjustment_rate`, and the item's
        cost falls by the LYD value of the refund.
    When `adjustment_acctid` is None the adjustment is basis-only LYD (legacy behaviour), so
    existing callers and data are unaffected."""
    _require_status(conn, lywrid, {"Pending Approval"})
    adj = money(cost_adjustment or 0)
    conn.execute("SAVEPOINT acceptinv")
    try:
        adj_trnsid = None
        if adjustment_acctid and adj != 0:
            cur = (adjustment_currency or "LYD").upper()
            if adj > 0:                                  # EXPENSE: money out, cost up
                adj_trnsid, lyd_spent = _spend_fx_or_lyd(conn, adjustment_acctid,
                                                         "Business_Expense", abs(adj), cur)
                lyd_basis_delta = lyd_spent
            else:                                        # REFUND: money in, cost down
                amt = abs(adj)
                if cur == "LYD":
                    adj_trnsid = _credit_account(conn, adjustment_acctid, amt, "LYD",
                                                 "Refund_Received", None, "cost adjustment refund")
                    lyd_basis_delta = -amt
                else:
                    if adjustment_rate is None or str(adjustment_rate).strip() == "":
                        raise ValueError("a conversion rate is required to refund foreign currency")
                    rate = _positive(adjustment_rate, "rate")
                    adj_trnsid = _credit_account(conn, adjustment_acctid, amt, cur,
                                                 "Refund_Received", rate, "cost adjustment refund")
                    lyd_basis_delta = -money(amt * rate)
            conn.execute("UPDATE inventory_items SET cost_adjustment=?, cost_adjustment_note=?, "
                         "cost_adjustment_trnsid=? WHERE lywrid=?",
                         (fl(money(lyd_basis_delta)), cost_adjustment_note, adj_trnsid, lywrid))
        elif adj != 0 or cost_adjustment_note:           # legacy basis-only (LYD)
            conn.execute("UPDATE inventory_items SET cost_adjustment=?, cost_adjustment_note=? "
                         "WHERE lywrid=?", (fl(adj), cost_adjustment_note, lywrid))

        row = conn.execute("SELECT lyd_cost_basis, cost_adjustment FROM inventory_items WHERE lywrid=?",
                           (lywrid,)).fetchone()
        total = money(Decimal(str(row["lyd_cost_basis"])) + Decimal(str(row["cost_adjustment"]))
                      + _item_shipping_cost_lyd(conn, lywrid))
        if total < 0:
            raise ValueError(f"cost adjustment makes the total cost negative ({total} LYD); "
                             "use a smaller reduction.")
        conn.execute("UPDATE inventory_items SET total_cost=?, status='In Stock', date_entered_inventory=? "
                     "WHERE lywrid=?", (fl(total), date, lywrid))
        conn.execute("RELEASE acceptinv")
    except Exception:
        conn.execute("ROLLBACK TO acceptinv"); conn.execute("RELEASE acceptinv"); raise
    _log(conn, "STATUS", "inventory_item", lywrid, f"accepted into stock, total cost {total} LYD")
    conn.commit(); return total


def account_batches(conn, acctid, currency="USD"):
    """FX batches on an account with their rates and remaining — used to offer a refund at
    the exact rate of the batch a purchase was made with."""
    return [{"bachid": r["bachid"], "rate": money(r["rate"]),
             "fx_amount": money(r["fx_amount"]), "fx_remaining": money(r["fx_remaining"]),
             "source": r["source"]}
            for r in conn.execute(
            "SELECT bachid, rate, fx_amount, fx_remaining, source FROM fx_batches "
            "WHERE acctid=? AND currency=? ORDER BY bachid", (acctid, currency))]


def _adjustment_refund_consumed(conn, trnsid):
    """True if a cost-adjustment refund's batch has since been (partly) spent — meaning the
    accept can no longer be cleanly undone."""
    if not trnsid:
        return False
    spent = conn.execute(
        "SELECT COALESCE(SUM(ba.fx_consumed),0) AS s FROM batch_allocations ba "
        "JOIN fx_batches b ON ba.bachid=b.bachid WHERE b.trnsid=?", (trnsid,)).fetchone()["s"]
    return money(spent) > 0


def _undo_money_movement(conn, trnsid):
    """Mechanically reverse a single money transaction tied to an item adjustment: restore
    any FX it consumed, drop any (unconsumed) batch it created, and delete the row. Used
    when unwinding an accept; the product-linked guard in reverse_transaction doesn't apply
    here because we ARE undoing from the item."""
    if not trnsid:
        return
    for a in conn.execute("SELECT alocid, bachid, fx_consumed FROM batch_allocations WHERE trnsid=?",
                          (trnsid,)):
        b = conn.execute("SELECT fx_remaining FROM fx_batches WHERE bachid=?", (a["bachid"],)).fetchone()
        if b:
            conn.execute("UPDATE fx_batches SET fx_remaining=? WHERE bachid=?",
                         (fl(money(Decimal(str(b["fx_remaining"])) + Decimal(str(a["fx_consumed"])))),
                          a["bachid"]))
        conn.execute("DELETE FROM batch_allocations WHERE alocid=?", (a["alocid"],))
    for b in conn.execute("SELECT bachid FROM fx_batches WHERE trnsid=?", (trnsid,)):
        if _adjustment_refund_consumed(conn, trnsid):
            raise StateError("the refunded foreign currency from this cost adjustment has already "
                             "been spent; undo whatever used it before unwinding this.")
        conn.execute("DELETE FROM fx_batches WHERE bachid=?", (b["bachid"],))
    # drop the item's pointer before deleting the row so the FK doesn't complain
    conn.execute("UPDATE inventory_items SET cost_adjustment_trnsid=NULL WHERE cost_adjustment_trnsid=?",
                 (trnsid,))
    conn.execute("DELETE FROM all_transactions WHERE trnsid=?", (trnsid,))


def item_cost_breakdown(conn, lywrid):
    """M8/M10/M11: decompose a unit's cost into item + intl shipping + local shipping + additional
    (shipping shares apportioned across each shipment's items; intl legs summed)."""
    row = conn.execute("SELECT lyd_cost_basis, cost_adjustment, total_cost FROM inventory_items "
                       "WHERE lywrid=?", (lywrid,)).fetchone()
    item_cost = money(row["lyd_cost_basis"])
    additional = money(row["cost_adjustment"])
    intl, local = _item_shipping_shares(conn, lywrid)
    total = money(item_cost + intl + local + additional)
    return {"item_cost": item_cost, "intl_shipping": intl, "local_shipping": local,
            "additional": additional, "total": total,
            "frozen_total": money(row["total_cost"]) if row["total_cost"] is not None else None}


# ---------------------------------------------------------------------------
# Sale orders (multi-item: header + atomized detail)
# ---------------------------------------------------------------------------
def commit_sale_order(conn, items, buyer_name=None, currency="LYD", requires_shipping=False,
                      buyer_phone=None):
    """
    items = list of {lywrid, price, additional_cost?, note?}. All must be In Stock.
    Creates a sales_orders header + one sales row per item; items -> Sold Pending.
    """
    for it in items:
        _require_status(conn, it["lywrid"], {"In Stock"})
    d, _ = now()
    cur = conn.execute(
        "INSERT INTO sales_orders(buyer_name,buyer_phone,currency,requires_shipping,status,date_committed) "
        "VALUES(?,?,?,?,?,?)", (buyer_name, buyer_phone, currency, 1 if requires_shipping else 0,
                                "Order Placed", d))
    soid = cur.lastrowid
    for it in items:
        conn.execute(
            "INSERT INTO sales(sale_order_id,lywrid,sale_price,additional_sales_cost,additional_sales_cost_note) "
            "VALUES(?,?,?,?,?)", (soid, it["lywrid"], fl(money(it["price"])),
                                  fl(money(it.get("additional_cost", 0))), it.get("note")))
        _set_status(conn, it["lywrid"], "Sold Pending")
    _log(conn, "INSERT", "sale_order", soid,
         f"{len(items)} item(s), buyer={buyer_name}, shipping={requires_shipping}")
    conn.commit(); return soid


def ship_order_to_customer(conn, sale_order_id, postal_office_name, shipping_cost=0, currency="LYD",
                           date_shipped=None, paying_acctid=None):
    o = conn.execute("SELECT * FROM sales_orders WHERE sale_order_id=?", (sale_order_id,)).fetchone()
    if not o:
        raise ValueError(f"no sale order {sale_order_id}")
    if not o["requires_shipping"]:
        raise StateError("order is not flagged for shipping")
    if o["status"] != "Order Placed":
        raise StateError(f"order {sale_order_id} is '{o['status']}', expected 'Order Placed'")
    shipping_cost = money(shipping_cost)
    trnsid = None
    try:
        if shipping_cost > 0:
            if paying_acctid is None:
                raise ValueError("paying_acctid required when the shop bears the shipping cost")
            trnsid, _ = _spend_fx_or_lyd(conn, paying_acctid, "Shipping_Expense", shipping_cost, currency)
        conn.execute(
            "INSERT INTO customer_shipments(sale_order_id,postal_office_name,shipping_cost,"
            "shipping_cost_currency,shipping_paid_trnsid,date_shipped_to_customer) VALUES(?,?,?,?,?,?)",
            (sale_order_id, postal_office_name, fl(shipping_cost), currency, trnsid, date_shipped))
        conn.execute("UPDATE sales_orders SET status='Shipping' WHERE sale_order_id=?", (sale_order_id,))
        _log(conn, "UPDATE", "sale_order", sale_order_id, f"shipping to customer (cost {shipping_cost} {currency})")
        conn.commit()
    except Exception:
        conn.rollback(); raise


def mark_order_arrived_customer(conn, sale_order_id, date):
    conn.execute("UPDATE customer_shipments SET date_arrived_customer=? WHERE sale_order_id=?",
                 (date, sale_order_id))
    conn.execute("UPDATE sales_orders SET date_arrived_customer=? WHERE sale_order_id=?",
                 (date, sale_order_id))
    _log(conn, "UPDATE", "sale_order", sale_order_id, f"arrived customer {date}")
    conn.commit()


def finalize_sale_order(conn, sale_order_id, receiving_acctid, date_paid):
    o = conn.execute("SELECT * FROM sales_orders WHERE sale_order_id=?", (sale_order_id,)).fetchone()
    if not o:
        raise ValueError(f"no sale order {sale_order_id}")
    if o["paid_in_full"]:
        raise StateError(f"order {sale_order_id} already finalized")
    if o["requires_shipping"] and not o["date_arrived_customer"]:
        raise StateError(f"order {sale_order_id} cannot be finalized before delivery")
    rows = conn.execute("SELECT lywrid, sale_price FROM sales WHERE sale_order_id=?", (sale_order_id,)).fetchall()
    total = money(sum(money(r["sale_price"]) for r in rows))
    try:
        trnsid = _txn(conn, receiving_acctid, "Sale", total, o["currency"])
        conn.execute("UPDATE sales_orders SET trnsid=?, paid_in_full=1, status='Finalized', date_finalized=? "
                     "WHERE sale_order_id=?", (trnsid, date_paid, sale_order_id))
        for r in rows:
            _set_status(conn, r["lywrid"], "Sold")
        _log(conn, "UPDATE", "sale_order", sale_order_id, f"finalized; revenue {total} {o['currency']}")
        conn.commit(); return trnsid
    except Exception:
        conn.rollback(); raise


# ---------------------------------------------------------------------------
# Derived reads
# ---------------------------------------------------------------------------
def lyd_balance(conn, acctid):
    r = conn.execute(
        "SELECT COALESCE(SUM(t.amount),0) AS b FROM all_transactions t "
        "JOIN transaction_types tt ON t.type = tt.type "
        "WHERE t.acctid=? AND t.currency='LYD' AND tt.affects_balance=1", (acctid,)).fetchone()
    return money(r["b"])


def fx_balance(conn, acctid, currency="USD"):
    r = conn.execute("SELECT COALESCE(SUM(fx_remaining),0) AS b FROM fx_batches "
                     "WHERE acctid=? AND currency=?", (acctid, currency)).fetchone()
    return money(r["b"])


def batch_remaining(conn, bachid):
    r = conn.execute("SELECT fx_remaining FROM fx_batches WHERE bachid=?", (bachid,)).fetchone()
    return money(r["fx_remaining"]) if r else money(0)


def category_total(conn, category):
    r = conn.execute(
        "SELECT COALESCE(SUM(t.amount),0) AS s FROM all_transactions t "
        "JOIN transaction_types tt ON t.type = tt.type "
        "WHERE tt.category=? AND t.currency='LYD'", (category,)).fetchone()
    return money(r["s"])


def item_total_cost(conn, lywrid):
    r = conn.execute("SELECT total_cost FROM inventory_items WHERE lywrid=?", (lywrid,)).fetchone()
    return money(r["total_cost"]) if r and r["total_cost"] is not None else None


def order_profit(conn, sale_order_id):
    rows = conn.execute(
        "SELECT s.sale_price, s.additional_sales_cost, i.total_cost FROM sales s "
        "JOIN inventory_items i ON s.lywrid=i.lywrid WHERE s.sale_order_id=?", (sale_order_id,)).fetchall()
    revenue = sum((money(r["sale_price"]) for r in rows), Decimal("0"))
    cost = sum((money(r["total_cost"] or 0) for r in rows), Decimal("0"))
    add = sum((money(r["additional_sales_cost"]) for r in rows), Decimal("0"))
    ship = conn.execute("SELECT COALESCE(SUM(shipping_cost),0) AS c FROM customer_shipments "
                        "WHERE sale_order_id=?", (sale_order_id,)).fetchone()["c"]
    return money(revenue - cost - money(ship) - add)


# ---------------------------------------------------------------------------
# Home dashboard: each statistic's value as of a given day (replayed history)
# ---------------------------------------------------------------------------
def _stat_as_of(conn, key, ds):
    if key == "inventory":   # in stock = entered inventory on/before ds, not yet committed to a sale
        return conn.execute(
            "SELECT COUNT(*) AS c FROM inventory_items i WHERE i.date_entered_inventory IS NOT NULL "
            "AND i.date_entered_inventory<=? AND NOT EXISTS (SELECT 1 FROM sales s "
            "JOIN sales_orders so ON s.sale_order_id=so.sale_order_id "
            "WHERE s.lywrid=i.lywrid AND so.date_committed<=?)", (ds, ds)).fetchone()["c"]
    if key == "to_shop":     # purchased on/before ds, not yet accepted into inventory
        return conn.execute(
            "SELECT COUNT(*) AS c FROM inventory_items i JOIN purchase_lines pl ON i.polnid=pl.polnid "
            "JOIN purchase_orders po ON pl.poid=po.poid WHERE po.order_date<=? "
            "AND (i.date_entered_inventory IS NULL OR i.date_entered_inventory>?)", (ds, ds)).fetchone()["c"]
    if key == "sales":       # cumulative finalized sale items up to ds
        return conn.execute(
            "SELECT COUNT(*) AS c FROM sales s JOIN sales_orders so ON s.sale_order_id=so.sale_order_id "
            "WHERE so.date_finalized IS NOT NULL AND so.date_finalized<=?", (ds,)).fetchone()["c"]
    if key == "to_customer":  # shipped to customer on/before ds, not finalized as of ds
        return conn.execute(
            "SELECT COUNT(*) AS c FROM sales s JOIN sales_orders so ON s.sale_order_id=so.sale_order_id "
            "JOIN customer_shipments cs ON cs.sale_order_id=so.sale_order_id "
            "WHERE cs.date_shipped_to_customer<=? AND (so.date_finalized IS NULL OR so.date_finalized>?)",
            (ds, ds)).fetchone()["c"]
    if key == "revenue":     # cumulative LYD revenue up to ds
        return float(conn.execute(
            "SELECT COALESCE(SUM(t.amount),0) AS s FROM all_transactions t JOIN transaction_types tt "
            "ON t.type=tt.type WHERE tt.category='Revenue' AND t.currency='LYD' AND t.date<=?",
            (ds,)).fetchone()["s"])
    if key == "expenses":    # cumulative LYD expenses up to ds (shown positive)
        return float(conn.execute(
            "SELECT COALESCE(SUM(-t.amount),0) AS s FROM all_transactions t JOIN transaction_types tt "
            "ON t.type=tt.type WHERE tt.category='Expense' AND t.currency='LYD' AND t.date<=?",
            (ds,)).fetchone()["s"])
    return 0


def home_stat_series(conn, key, days=7):
    """Return [(date, value), ...] for the last `days` days ending today (rolling window)."""
    from datetime import date, timedelta
    today = date.today()
    return [(today - timedelta(days=i), _stat_as_of(conn, key, (today - timedelta(days=i)).isoformat()))
            for i in range(days - 1, -1, -1)]


# ---------------------------------------------------------------------------
# Listings (supertype all_listings + platform subtype)
# ---------------------------------------------------------------------------
def add_listing(conn, platform, link=None, price=None, currency=None, qty_items=None,
                seller_name=None, date_of_listing=None, reference=None, phone_number=None,
                listing_name=None, seller_link=None):
    """
    Create a listing: one all_listings row plus its platform-specific subtype row.
    `reference` maps to the eBay item number or the Amazon ASIN.
    Numeric fields may be passed as strings/None; they are coerced here.
    """
    if platform not in ("eBay", "Amazon", "Facebook", "In-Person"):
        raise ValueError(f"unknown platform {platform}")
    price = fl(money(price)) if price not in (None, "", "None") else None
    qty_items = int(qty_items) if str(qty_items).strip() not in ("", "None") else None
    cur = conn.execute(
        "INSERT INTO all_listings(platform,link,price,currency,qty_items,seller_name,date_of_listing,"
        "phone_number,listing_name,seller_link) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (platform, link or None, price, currency or None, qty_items, seller_name or None,
         date_of_listing or None, phone_number or None, listing_name or None, seller_link or None))
    lsid = cur.lastrowid
    if platform == "eBay":
        conn.execute("INSERT INTO ebay_listings(lsid,ebay_item_number,link,price,currency,seller_name) "
                     "VALUES(?,?,?,?,?,?)", (lsid, reference or None, link or None, price, currency, seller_name))
    elif platform == "Amazon":
        conn.execute("INSERT INTO amazon_listings(lsid,asin,link,price,currency) VALUES(?,?,?,?,?)",
                     (lsid, reference or None, link or None, price, currency))
    elif platform == "Facebook":
        conn.execute("INSERT INTO facebook_listings(lsid,link) VALUES(?,?)", (lsid, link or None))
    elif platform == "In-Person":
        conn.execute("INSERT INTO inperson_listings(lsid,seller_name) VALUES(?,?)", (lsid, seller_name or None))
    _log(conn, "INSERT", "listing", lsid, f"{platform} listing")
    conn.commit()
    return lsid


# ===========================================================================
# CATALOG / REPOSITORY  (v5)
# ---------------------------------------------------------------------------
# An item-type repository. catalog_items are TYPES/variants (not physical
# units); specs are open-ended (name, value) attributes drawn from an
# editable name-vocabulary with free-text values. A signature fingerprints
# (category, manufacturer, model, display_name + the full sorted attribute
# set) so two identical items cannot coexist.
# ===========================================================================
def _norm(s):
    """Canonicalise for fingerprinting: trim, collapse inner whitespace, casefold."""
    return " ".join((s or "").split()).casefold()


def catalog_signature(category, manufacturer, model_name, display_name, attributes):
    """Order-independent fingerprint of core fields + attribute set."""
    core = "|".join(_norm(x) for x in (category, manufacturer or "", model_name or "", display_name))
    attrs = ";".join(f"{_norm(n)}={_norm(v)}"
                     for n, v in sorted(attributes, key=lambda p: (_norm(p[0]), _norm(p[1]))))
    return hashlib.sha256((core + "||" + attrs).encode("utf-8")).hexdigest()


# ---- editable vocabularies -------------------------------------------------
def add_category(conn, name):
    name = (name or "").strip()
    if not name:
        raise ValueError("category name is required")
    conn.execute("INSERT OR IGNORE INTO categories(cat_name) VALUES(?)", (name,))
    conn.commit()
    return name


def add_manufacturer(conn, name):
    name = (name or "").strip()
    if not name:
        raise ValueError("manufacturer name is required")
    conn.execute("INSERT OR IGNORE INTO manufacturers(manu_name) VALUES(?)", (name,))
    conn.commit()
    return name


def add_attribute_name(conn, name):
    name = (name or "").strip()
    if not name:
        raise ValueError("attribute name is required")
    conn.execute("INSERT OR IGNORE INTO attribute_names(attr_name) VALUES(?)", (name,))
    conn.commit()
    return name


def list_categories(conn):
    return [r["cat_name"] for r in conn.execute("SELECT cat_name FROM categories ORDER BY cat_name")]


def list_manufacturers(conn):
    return [r["manu_name"] for r in conn.execute("SELECT manu_name FROM manufacturers ORDER BY manu_name")]


def list_attribute_names(conn):
    return [r["attr_name"] for r in conn.execute("SELECT attr_name FROM attribute_names ORDER BY attr_name")]


def _vocab_in_use(conn, kind, name):
    if kind == "category":
        return conn.execute("SELECT 1 FROM catalog_items WHERE category=? LIMIT 1", (name,)).fetchone() is not None
    if kind == "manufacturer":
        return conn.execute("SELECT 1 FROM catalog_items WHERE manufacturer=? LIMIT 1", (name,)).fetchone() is not None
    if kind == "attribute":
        return conn.execute("SELECT 1 FROM catalog_attributes WHERE attr_name=? LIMIT 1", (name,)).fetchone() is not None
    return False


def delete_vocab(conn, kind, name):
    """Remove an unused vocabulary entry (guarded: refuses if referenced)."""
    if _vocab_in_use(conn, kind, name):
        raise StateError(f"'{name}' is in use by catalog items and can't be removed.")
    table, col = {"category": ("categories", "cat_name"),
                  "manufacturer": ("manufacturers", "manu_name"),
                  "attribute": ("attribute_names", "attr_name")}[kind]
    conn.execute(f"DELETE FROM {table} WHERE {col}=?", (name,))
    conn.commit()


# ---- catalog items ---------------------------------------------------------
def _clean_attrs(attributes):
    """Drop blank rows; trim names/values. Returns list of (name, value)."""
    out = []
    for name, value in (attributes or []):
        name, value = (name or "").strip(), (value or "").strip()
        if name and value:
            out.append((name, value))
    return out


def _family_key(display_name):
    return (display_name or "").strip().lower()


def catalog_variants(conn, display_name, exclude_catid=None):
    """All catalogue items sharing this display name (the 'variant family'), each with its
    variant label and a short spec summary. Used to surface existing variants on entry."""
    rows = conn.execute(
        "SELECT catid, display_name, category, manufacturer, model_name, variant "
        "FROM catalog_items WHERE LOWER(TRIM(display_name))=? ORDER BY variant, catid",
        (_family_key(display_name),)).fetchall()
    out = []
    for r in rows:
        if exclude_catid is not None and r["catid"] == exclude_catid:
            continue
        attrs = [(a["attr_name"], a["attr_value"]) for a in conn.execute(
            "SELECT attr_name, attr_value FROM catalog_attributes WHERE catid=? "
            "ORDER BY sort_order, catattrid", (r["catid"],))]
        summary = ", ".join(f"{n}: {v}" for n, v in attrs) or "no attributes"
        out.append({"catid": r["catid"], "variant": r["variant"], "category": r["category"],
                    "manufacturer": r["manufacturer"], "model_name": r["model_name"],
                    "attributes": attrs, "spec_summary": summary})
    return out


def next_variant_label(conn, display_name, exclude_catid=None):
    """Suggest the next free variant label in a name family: A, B, C, ... then A1, A2, ..."""
    taken = {v["variant"].strip().upper() for v in catalog_variants(conn, display_name, exclude_catid)}
    for code in range(ord("A"), ord("Z") + 1):
        if chr(code) not in taken:
            return chr(code)
    i = 1
    while f"A{i}" in taken:
        i += 1
    return f"A{i}"


def _resolve_variant(conn, display_name, variant, exclude_catid=None):
    """Return a valid variant label: auto-assign the next free one when not supplied,
    else validate it isn't already used by another item of the same name."""
    if variant is None or str(variant).strip() == "":
        return next_variant_label(conn, display_name, exclude_catid)
    variant = str(variant).strip()
    taken = {v["variant"].strip().lower(): v["catid"]
             for v in catalog_variants(conn, display_name, exclude_catid)}
    if variant.lower() in taken:
        raise DuplicateCatalogItem(
            f"Variant '{variant}' is already used by another '{display_name.strip()}' "
            f"(#{taken[variant.lower()]}). Pick a different variant label.")
    return variant


def catalog_attributes_map(conn):
    """{catid: {attr_name_lower: value}} in one pass — feeds the report's attribute
    columns without a query per row. Names are lowercased for case-insensitive matching."""
    out = {}
    for r in conn.execute("SELECT catid, attr_name, attr_value FROM catalog_attributes"):
        out.setdefault(r["catid"], {})[(r["attr_name"] or "").strip().lower()] = r["attr_value"]
    return out


def variant_suffix_map(conn):
    """{catid: ' (variant)'} for items whose display name has 2+ variants; '' otherwise.
    One pass — used to disambiguate same-named items in the operational tables."""
    fam = {}
    for r in conn.execute("SELECT catid, display_name, variant FROM catalog_items"):
        fam.setdefault(_family_key(r["display_name"]), []).append((r["catid"], r["variant"]))
    out = {}
    for members in fam.values():
        multi = len(members) > 1
        for catid, variant in members:
            out[catid] = f" ({variant})" if multi else ""
    return out


def add_catalog_item(conn, category, display_name, manufacturer=None, model_name=None,
                     attributes=None, variant=None):
    """
    Create a catalog item (a product TYPE/variant). Category and display_name are
    required; manufacturer/model/attributes optional. Raises DuplicateCatalogItem
    if an item with the identical signature already exists. Vocabulary entries used
    here are auto-registered so the controlled sets grow naturally.
    """
    category = (category or "").strip()
    display_name = (display_name or "").strip()
    manufacturer = (manufacturer or "").strip() or None
    model_name = (model_name or "").strip() or None
    if not category:
        raise ValueError("category is required")
    if not display_name:
        raise ValueError("display name is required")
    attrs = _clean_attrs(attributes)
    sig = catalog_signature(category, manufacturer, model_name, display_name, attrs)
    dup = conn.execute("SELECT catid FROM catalog_items WHERE signature=?", (sig,)).fetchone()
    if dup:
        raise DuplicateCatalogItem(
            f"An identical item already exists in the catalog (#{dup['catid']}).")
    add_category(conn, category)
    if manufacturer:
        add_manufacturer(conn, manufacturer)
    for n, _ in attrs:
        add_attribute_name(conn, n)
    variant = _resolve_variant(conn, display_name, variant)
    cur = conn.execute(
        "INSERT INTO catalog_items(category,manufacturer,model_name,display_name,signature,variant) "
        "VALUES(?,?,?,?,?,?)", (category, manufacturer, model_name, display_name, sig, variant))
    catid = cur.lastrowid
    for i, (n, v) in enumerate(attrs):
        conn.execute("INSERT INTO catalog_attributes(catid,attr_name,attr_value,sort_order) "
                     "VALUES(?,?,?,?)", (catid, n, v, i))
    _log(conn, "INSERT", "catalog_item", catid, display_name)
    conn.commit()
    return catid


def update_catalog_item(conn, catid, category, display_name, manufacturer=None,
                        model_name=None, attributes=None, variant=None):
    """Replace a catalog item's core fields + attributes; re-checks the signature
    against OTHER items so an edit can't collide with an existing entry. `variant`
    is kept as-is when not supplied, else validated unique within the name family."""
    category = (category or "").strip()
    display_name = (display_name or "").strip()
    manufacturer = (manufacturer or "").strip() or None
    model_name = (model_name or "").strip() or None
    if not category or not display_name:
        raise ValueError("category and display name are required")
    attrs = _clean_attrs(attributes)
    sig = catalog_signature(category, manufacturer, model_name, display_name, attrs)
    clash = conn.execute("SELECT catid FROM catalog_items WHERE signature=? AND catid<>?",
                         (sig, catid)).fetchone()
    if clash:
        raise DuplicateCatalogItem(
            f"Those details match another catalog item (#{clash['catid']}).")
    add_category(conn, category)
    if manufacturer:
        add_manufacturer(conn, manufacturer)
    for n, _ in attrs:
        add_attribute_name(conn, n)
    if variant is None or str(variant).strip() == "":
        cur_var = conn.execute("SELECT variant FROM catalog_items WHERE catid=?", (catid,)).fetchone()
        cur_var = cur_var["variant"] if cur_var else "A"
        taken = {v["variant"].strip().lower()
                 for v in catalog_variants(conn, display_name, exclude_catid=catid)}
        new_variant = cur_var if cur_var.strip().lower() not in taken \
            else next_variant_label(conn, display_name, exclude_catid=catid)
    else:
        new_variant = _resolve_variant(conn, display_name, variant, exclude_catid=catid)
    conn.execute("UPDATE catalog_items SET category=?,manufacturer=?,model_name=?,display_name=?,"
                 "signature=?,variant=? WHERE catid=?",
                 (category, manufacturer, model_name, display_name, sig, new_variant, catid))
    conn.execute("DELETE FROM catalog_attributes WHERE catid=?", (catid,))
    for i, (n, v) in enumerate(attrs):
        conn.execute("INSERT INTO catalog_attributes(catid,attr_name,attr_value,sort_order) "
                     "VALUES(?,?,?,?)", (catid, n, v, i))
    # re-sync the one denormalized snapshot so the corrected name shows everywhere
    conn.execute("UPDATE purchase_lines SET item_name=? WHERE catid=?", (display_name, catid))
    _log(conn, "UPDATE", "catalog_item", catid, display_name)
    conn.commit()


def catalog_item_in_use(conn, catid):
    for tbl in ("listing_items", "purchase_lines", "inventory_items"):
        if conn.execute(f"SELECT 1 FROM {tbl} WHERE catid=? LIMIT 1", (catid,)).fetchone():
            return True
    return False


def get_catalog_item(conn, catid):
    """Return {'item': row, 'attributes': [(name, value), ...]} or None."""
    item = conn.execute("SELECT * FROM catalog_items WHERE catid=?", (catid,)).fetchone()
    if not item:
        return None
    attrs = conn.execute("SELECT attr_name, attr_value FROM catalog_attributes "
                         "WHERE catid=? ORDER BY sort_order, catattrid", (catid,)).fetchall()
    return {"item": item, "attributes": [(a["attr_name"], a["attr_value"]) for a in attrs]}


def catalog_label(conn, catid):
    """Human label: 'Display Name (Attr: val, Attr: val)'."""
    d = get_catalog_item(conn, catid)
    if not d:
        return f"#{catid}"
    base = d["item"]["display_name"]
    if d["attributes"]:
        base += " (" + ", ".join(f"{n}: {v}" for n, v in d["attributes"]) + ")"
    return base


def list_catalog_items(conn, limit=500):
    return conn.execute("SELECT * FROM catalog_items ORDER BY display_name LIMIT ?", (limit,)).fetchall()


def search_catalog(conn, query=None, category=None, limit=300, include_hidden=False):
    """Search catalog by free text across core fields and attribute names/values;
    optionally constrain to a category. Hidden items are excluded from pickers."""
    sql = ("SELECT DISTINCT ci.* FROM catalog_items ci "
           "LEFT JOIN catalog_attributes ca ON ca.catid=ci.catid WHERE 1=1 ")
    params = []
    if not include_hidden:
        sql += "AND ci.is_hidden=0 "
    if category:
        sql += "AND ci.category=? "
        params.append(category)
    if query:
        q = f"%{query.strip().lower()}%"
        sql += ("AND (lower(ci.display_name) LIKE ? OR lower(IFNULL(ci.model_name,'')) LIKE ? "
                "OR lower(IFNULL(ci.manufacturer,'')) LIKE ? OR lower(ci.category) LIKE ? "
                "OR lower(IFNULL(ca.attr_value,'')) LIKE ? OR lower(IFNULL(ca.attr_name,'')) LIKE ?) ")
        params += [q, q, q, q, q, q]
    sql += "ORDER BY ci.display_name LIMIT ?"
    params.append(limit)
    return conn.execute(sql, params).fetchall()


# ---- autocomplete sources --------------------------------------------------
def autocomplete_display_names(conn, prefix="", limit=20):
    rows = conn.execute(
        "SELECT DISTINCT display_name FROM catalog_items WHERE lower(display_name) LIKE ? "
        "ORDER BY display_name LIMIT ?", (f"%{(prefix or '').lower()}%", limit)).fetchall()
    return [r["display_name"] for r in rows]


def autocomplete_model_names(conn, prefix="", limit=20):
    rows = conn.execute(
        "SELECT DISTINCT model_name FROM catalog_items WHERE model_name IS NOT NULL "
        "AND lower(model_name) LIKE ? ORDER BY model_name LIMIT ?",
        (f"%{(prefix or '').lower()}%", limit)).fetchall()
    return [r["model_name"] for r in rows]


def attribute_value_suggestions(conn, attr_name, prefix="", limit=20):
    """Distinct prior values for a given attribute name (scoped autocomplete)."""
    rows = conn.execute(
        "SELECT DISTINCT attr_value FROM catalog_attributes WHERE attr_name=? "
        "AND lower(attr_value) LIKE ? ORDER BY attr_value LIMIT ?",
        (attr_name, f"%{(prefix or '').lower()}%", limit)).fetchall()
    return [r["attr_value"] for r in rows]


# ---- listing composition (junction) ---------------------------------------
def add_listing_items(conn, lsid, items):
    """items: list of (catid, quantity) or (catid, quantity, unit_price).
    One row per product; quantity holds the count; unit_price is the per-item listing price."""
    for it in items:
        catid, qty = it[0], int(it[1])
        unit_price = it[2] if len(it) > 2 else None
        if qty < 1:
            raise ValueError("quantity must be >= 1")
        up = fl(money(unit_price)) if unit_price not in (None, "", "None") else None
        conn.execute("INSERT INTO listing_items(lsid,catid,quantity,unit_price) VALUES(?,?,?,?)",
                     (lsid, catid, qty, up))
    _log(conn, "INSERT", "listing_items", lsid, f"{len(items)} line(s)")
    conn.commit()


def get_listing_items(conn, lsid):
    """Return listing lines joined to their catalogue display name, with per-item price."""
    return conn.execute(
        "SELECT li.lnitid, li.catid, li.quantity, li.unit_price, ci.display_name, ci.category "
        "FROM listing_items li JOIN catalog_items ci ON li.catid=ci.catid "
        "WHERE li.lsid=? ORDER BY li.lnitid", (lsid,)).fetchall()


def listing_total(conn, lsid):
    """Total listing value = sum(unit_price * quantity) over its lines (M1)."""
    total = Decimal("0")
    for r in conn.execute("SELECT quantity, unit_price FROM listing_items WHERE lsid=?", (lsid,)):
        if r["unit_price"] is not None:
            total += money(Decimal(str(r["unit_price"])) * Decimal(int(r["quantity"])))
    return money(total)


def listing_value_breakdown(conn, lsid):
    """Per-line value breakdown for a listing (M12): display, qty, unit price, line total."""
    out = []
    for r in get_listing_items(conn, lsid):
        up = money(r["unit_price"]) if r["unit_price"] is not None else None
        line = money((up or Decimal("0")) * Decimal(int(r["quantity"])))
        out.append({"display_name": r["display_name"], "quantity": r["quantity"],
                    "unit_price": up, "line_total": line})
    return out


# ---- persistent UI preferences ---------------------------------------------
def set_pref(conn, key, value):
    conn.execute(
        "INSERT INTO ui_prefs(pref_key,pref_value,updated_at) VALUES(?,?,CURRENT_TIMESTAMP) "
        "ON CONFLICT(pref_key) DO UPDATE SET pref_value=excluded.pref_value, "
        "updated_at=CURRENT_TIMESTAMP", (key, str(value)))
    conn.commit()


def get_pref(conn, key, default=None):
    r = conn.execute("SELECT pref_value FROM ui_prefs WHERE pref_key=?", (key,)).fetchone()
    return r["pref_value"] if r else default


def used_attribute_names(conn):
    """Distinct attribute names that actually appear on catalog items (for table columns)."""
    return [r["attr_name"] for r in conn.execute(
        "SELECT DISTINCT attr_name FROM catalog_attributes ORDER BY attr_name")]


# ---- catalogue attribute templates (QOL: quick-fill attribute sets) --------
# Stored as a JSON map {template_name: [attr_name, ...]} in ui_prefs. A template
# captures only the LIST and ORDER of attributes to pre-fill, never their values.
_TEMPLATE_KEY = "catalog_templates"


def list_catalog_templates(conn):
    """Return {name: [attr_name, ...]} of saved attribute templates."""
    try:
        data = json.loads(get_pref(conn, _TEMPLATE_KEY, "{}") or "{}")
        if isinstance(data, dict):
            return {str(k): [str(a) for a in v] for k, v in data.items()}
    except (ValueError, TypeError):
        pass
    return {}


def save_catalog_template(conn, name, attrs):
    """Create or overwrite a template. `attrs` is an ordered list of attribute names."""
    name = (name or "").strip()
    if not name:
        raise ValueError("a template name is required")
    seen, clean = set(), []
    for a in attrs:
        a = (a or "").strip()
        if a and a.lower() not in seen:      # de-dupe, preserve order
            seen.add(a.lower()); clean.append(a)
    if not clean:
        raise ValueError("a template needs at least one attribute")
    data = list_catalog_templates(conn)
    data[name] = clean
    set_pref(conn, _TEMPLATE_KEY, json.dumps(data, ensure_ascii=False))
    _log(conn, "UPDATE", "catalog_template", 0, f"saved template '{name}' ({len(clean)} attrs)")
    return name


def delete_catalog_template(conn, name):
    data = list_catalog_templates(conn)
    if name in data:
        del data[name]
        set_pref(conn, _TEMPLATE_KEY, json.dumps(data, ensure_ascii=False))
        _log(conn, "DELETE", "catalog_template", 0, f"deleted template '{name}'")


def shop_shipment_groups(conn):
    """M5/QOL4: shipments still in the inbound pipeline, with item count and status summary."""
    rows = conn.execute(
        "SELECT s.shipid, s.shipment_type, COUNT(si.lywrid) AS n "
        "FROM shipments s JOIN shipment_items si ON si.shipid=s.shipid "
        "JOIN inventory_items i ON i.lywrid=si.lywrid "
        "JOIN inventory_statuses st ON i.status=st.status "
        "WHERE st.stage='shipping' GROUP BY s.shipid ORDER BY s.shipid").fetchall()
    out = []
    for r in rows:
        statuses = [x["status"] for x in conn.execute(
            "SELECT DISTINCT i.status FROM shipment_items si JOIN inventory_items i ON i.lywrid=si.lywrid "
            "WHERE si.shipid=?", (r["shipid"],))]
        out.append({"shipid": r["shipid"], "type": r["shipment_type"], "count": r["n"],
                    "statuses": statuses})
    return out


def shipment_member_items(conn, shipid):
    """Items belonging to a shipment, with display name + status (for group expansion / splitting)."""
    return conn.execute(
        "SELECT i.lywrid, i.catid, pl.item_name, i.status FROM shipment_items si "
        "JOIN inventory_items i ON i.lywrid=si.lywrid "
        "JOIN purchase_lines pl ON i.polnid=pl.polnid WHERE si.shipid=? ORDER BY i.lywrid", (shipid,)).fetchall()


def order_items_detail(conn, sale_order_id):
    """M6: the atomized constituent units of a sale order, with cost + sale price."""
    return conn.execute(
        "SELECT s.slsid, s.lywrid, i.catid, pl.item_name, s.sale_price, i.total_cost "
        "FROM sales s JOIN inventory_items i ON s.lywrid=i.lywrid "
        "JOIN purchase_lines pl ON i.polnid=pl.polnid "
        "WHERE s.sale_order_id=? ORDER BY s.slsid", (sale_order_id,)).fetchall()


def item_detail(conn, catid):
    """Core + attributes for a catalog item as a flat dict for table display.
    Returns {'Category':..,'Manufacturer':..,'Model':..,<attr_name>:<value>,...} or {} if no catid."""
    if not catid:
        return {}
    it = conn.execute("SELECT category, manufacturer, model_name FROM catalog_items WHERE catid=?",
                      (catid,)).fetchone()
    if not it:
        return {}
    d = {"Category": it["category"], "Manufacturer": it["manufacturer"] or "",
         "Model": it["model_name"] or ""}
    for a in conn.execute("SELECT attr_name, attr_value FROM catalog_attributes WHERE catid=?", (catid,)):
        d[a["attr_name"]] = a["attr_value"]
    return d


# ===========================================================================
# ANALYTICS / REPORTS  (read-only aggregation; every function takes an optional
# filter dict so Reports and Home share one code path. Filter keys (all
# optional): date_from, date_to, platform, acctid, category, catid, status.
# Dates filter the row's recorded business date (not created_at). LYD is the
# normalized reporting currency; native USD is shown where it is the real
# amount (FX/card rows).)
# ===========================================================================
def _between(filt, col):
    """Return (sql_fragment, params) constraining `col` to the filter's date range."""
    frag, params = [], []
    f = filt or {}
    if f.get("date_from"):
        frag.append(f"{col}>=?"); params.append(f["date_from"])
    if f.get("date_to"):
        frag.append(f"{col}<=?"); params.append(f["date_to"])
    return (" AND ".join(frag), params)


def transactions_report(conn, filt=None):
    """Every ledger transaction (optionally date/account filtered), newest first."""
    f = filt or {}
    where, params = ["1=1"], []
    db, dp = _between(f, "t.date")
    if db:
        where.append(db); params += dp
    if f.get("acctid"):
        where.append("t.acctid=?"); params.append(f["acctid"])
    rows = conn.execute(
        "SELECT t.trnsid, t.date, t.time, a.account_name, t.type, tt.category, "
        "t.amount, t.currency FROM all_transactions t JOIN accounts a ON t.acctid=a.acctid "
        "JOIN transaction_types tt ON t.type=tt.type WHERE " + " AND ".join(where) +
        " ORDER BY t.date DESC, t.trnsid DESC", params).fetchall()
    return [dict(r) for r in rows]


def financial_summary(conn, filt=None):
    """Headline financials over the filtered window: revenue, expense-by-category,
    capital flows and net, all in LYD."""
    f = filt or {}
    where, params = ["t.currency='LYD'"], []
    db, dp = _between(f, "t.date")
    if db:
        where.append(db); params += dp
    if f.get("acctid"):
        where.append("t.acctid=?"); params.append(f["acctid"])
    w = " AND ".join(where)
    by_type = {r["type"]: money(r["s"]) for r in conn.execute(
        "SELECT t.type, COALESCE(SUM(t.amount),0) AS s FROM all_transactions t WHERE " + w +
        " GROUP BY t.type", params)}
    revenue = money(conn.execute(
        "SELECT COALESCE(SUM(t.amount),0) AS s FROM all_transactions t JOIN transaction_types tt "
        "ON t.type=tt.type WHERE " + w + " AND tt.category='Revenue'", params).fetchone()["s"])
    expense = money(-(conn.execute(
        "SELECT COALESCE(SUM(t.amount),0) AS s FROM all_transactions t JOIN transaction_types tt "
        "ON t.type=tt.type WHERE " + w + " AND tt.category='Expense'", params).fetchone()["s"]))
    exp_by_cat = {r["type"]: money(-r["s"]) for r in conn.execute(
        "SELECT t.type, COALESCE(SUM(t.amount),0) AS s FROM all_transactions t JOIN transaction_types tt "
        "ON t.type=tt.type WHERE " + w + " AND tt.category='Expense' GROUP BY t.type", params)}
    deposits = by_type.get("Deposit", money(0))
    withdrawals = money(-by_type.get("Withdrawal", money(0)))
    fx = by_type.get("FX_Gain_Loss", money(0))
    net = money(revenue - expense + fx)
    return {"revenue": revenue, "expense": expense, "expense_by_type": exp_by_cat,
            "fx_gain_loss": fx, "deposits": deposits, "withdrawals": withdrawals, "net": net}


def fx_report(conn, filt=None):
    """USD conversion events (card recharges / conversions) with the rate applied,
    so the LYD-per-USD market can be tracked over time."""
    f = filt or {}
    where, params = ["b.currency='USD'"], []
    db, dp = _between(f, "t.date")
    if db:
        where.append(db); params += dp
    if f.get("acctid"):
        where.append("b.acctid=?"); params.append(f["acctid"])
    rows = conn.execute(
        "SELECT t.date, a.account_name, b.currency, b.fx_amount, b.lyd_cost, b.rate, b.source "
        "FROM fx_batches b JOIN all_transactions t ON b.trnsid=t.trnsid "
        "JOIN accounts a ON b.acctid=a.acctid WHERE " + " AND ".join(where) +
        " ORDER BY t.date, b.bachid", params).fetchall()
    out = []
    for r in rows:
        out.append({"date": r["date"], "account": r["account_name"], "currency": r["currency"],
                    "usd": money(r["fx_amount"]), "lyd_cost": money(r["lyd_cost"]),
                    "rate": money(r["rate"]), "source": r["source"]})
    return out


def inventory_report(conn, filt=None):
    """Every inventory unit with its stage, status, frozen/working cost and key dates."""
    f = filt or {}
    where, params = ["1=1"], []
    if f.get("status"):
        where.append("i.status=?"); params.append(f["status"])
    if f.get("catid"):
        where.append("i.catid=?"); params.append(f["catid"])
    if f.get("category"):
        where.append("ci.category=?"); params.append(f["category"])
    rows = conn.execute(
        "SELECT i.lywrid, i.catid, pl.item_name, i.status, st.stage, i.total_cost, "
        "i.lyd_cost_basis, i.date_entered_inventory, po.order_date, po.delivery_method "
        "FROM inventory_items i JOIN purchase_lines pl ON i.polnid=pl.polnid "
        "JOIN purchase_orders po ON pl.poid=po.poid JOIN inventory_statuses st ON i.status=st.status "
        "LEFT JOIN catalog_items ci ON i.catid=ci.catid WHERE " + " AND ".join(where) +
        " ORDER BY i.lywrid DESC", params).fetchall()
    out = []
    for r in rows:
        bd = item_cost_breakdown(conn, r["lywrid"])
        out.append({"lywrid": r["lywrid"], "item": r["item_name"], "status": r["status"],
                    "stage": r["stage"], "cost": bd["total"], "frozen": r["total_cost"] is not None,
                    "purchased": r["order_date"], "entered": r["date_entered_inventory"],
                    "method": r["delivery_method"]})
    return out


def logistics_report(conn, filt=None):
    """Per-unit logistics timeline (purchase -> shipping milestones -> shop -> sold)."""
    f = filt or {}
    where, params = ["1=1"], []
    if f.get("catid"):
        where.append("i.catid=?"); params.append(f["catid"])
    if f.get("category"):
        where.append("ci.category=?"); params.append(f["category"])
    if f.get("status"):
        where.append("i.status=?"); params.append(f["status"])
    rows = conn.execute(
        "SELECT i.lywrid, pl.item_name, i.status, po.delivery_method, po.order_date "
        "FROM inventory_items i JOIN purchase_lines pl ON i.polnid=pl.polnid "
        "JOIN purchase_orders po ON pl.poid=po.poid "
        "LEFT JOIN catalog_items ci ON i.catid=ci.catid WHERE " + " AND ".join(where) +
        " ORDER BY i.lywrid DESC", params).fetchall()
    out = []
    for r in rows:
        d = item_shipping_dates(conn, r["lywrid"])
        out.append({"lywrid": r["lywrid"], "item": r["item_name"], "status": r["status"],
                    "method": r["delivery_method"], "purchased": r["order_date"],
                    "us_warehouse": d["us_warehouse"], "libya_warehouse": d["libya_warehouse"],
                    "local_sent": d["local_sent"], "local_office": d["local_office"],
                    "picked_up": d["picked_up"]})
    return out


def sales_report(conn, filt=None):
    """Per finalized/sold unit: sale price, frozen cost and realized profit."""
    f = filt or {}
    where, params = ["so.status IN ('Shipping','Finalized') OR i.status IN ('Sold','Sold Pending')"], []
    db, dp = _between(f, "so.date_committed")
    if db:
        where.append(db); params += dp
    if f.get("catid"):
        where.append("i.catid=?"); params.append(f["catid"])
    if f.get("category"):
        where.append("ci.category=?"); params.append(f["category"])
    rows = conn.execute(
        "SELECT s.slsid, so.sale_order_id, so.buyer_name, pl.item_name, s.sale_price, "
        "i.total_cost, s.additional_sales_cost, so.status, so.date_committed, so.date_finalized "
        "FROM sales s JOIN sales_orders so ON s.sale_order_id=so.sale_order_id "
        "JOIN inventory_items i ON s.lywrid=i.lywrid JOIN purchase_lines pl ON i.polnid=pl.polnid "
        "LEFT JOIN catalog_items ci ON i.catid=ci.catid WHERE (" + ") AND (".join(where) + ")"
        " ORDER BY so.sale_order_id DESC, s.slsid", params).fetchall()
    out = []
    for r in rows:
        cost = money(r["total_cost"]) if r["total_cost"] is not None else money(0)
        addl = money(r["additional_sales_cost"])
        profit = money(money(r["sale_price"]) - cost - addl)
        out.append({"order": r["sale_order_id"], "buyer": r["buyer_name"], "item": r["item_name"],
                    "sale_price": money(r["sale_price"]), "cost": cost, "additional": addl,
                    "profit": profit, "status": r["status"], "committed": r["date_committed"],
                    "finalized": r["date_finalized"]})
    return out


def set_listing_archived(conn, lsid, archived=True):
    """Archive (or restore) a listing. Archived listings stay on record but drop out of
    market-value maths — for competitor listings that sold, expired, or predate a rate shift."""
    if not conn.execute("SELECT 1 FROM all_listings WHERE lsid=?", (lsid,)).fetchone():
        raise ValueError(f"listing {lsid} not found")
    conn.execute("UPDATE all_listings SET is_archived=? WHERE lsid=?", (1 if archived else 0, lsid))
    _log(conn, "EDIT", "listing", lsid, "archived" if archived else "restored")
    conn.commit()


def _market_where(days, include_archived):
    """Shared WHERE fragments for the market-value queries. Listings with no date are kept
    (they can't be age-judged); dated ones must fall inside the recency window."""
    w = "" if include_archived else " AND COALESCE(al.is_archived,0)=0"
    if days:
        w += (" AND (al.date_of_listing IS NULL OR al.date_of_listing='' "
              "OR date(al.date_of_listing) >= date('now', ?))")
    return w


def market_value_map(conn, platforms=("Facebook", "In-Person"), currency="LYD", days=90,
                     include_archived=False):
    """{catid: {'n', 'avg', 'min', 'max'}} of local listing prices — one pass for the
    catalogue table's market-value column. Only active listings from the last `days`
    (undated ones included) count, so the figure tracks the current market."""
    ph = ",".join("?" * len(platforms))
    params = [*platforms, currency]
    where = _market_where(days, include_archived)
    if days:
        params.append(f"-{int(days)} days")
    rows = conn.execute(
        f"SELECT li.catid AS catid, COUNT(*) AS n, AVG(li.unit_price) AS avg, "
        f"MIN(li.unit_price) AS mn, MAX(li.unit_price) AS mx "
        f"FROM listing_items li JOIN all_listings al ON li.lsid=al.lsid "
        f"WHERE li.unit_price IS NOT NULL AND al.platform IN ({ph}) AND al.currency=?{where} "
        f"GROUP BY li.catid", params).fetchall()
    return {r["catid"]: {"n": r["n"], "avg": money(r["avg"]) if r["avg"] is not None else None,
                         "min": money(r["mn"]) if r["mn"] is not None else None,
                         "max": money(r["mx"]) if r["mx"] is not None else None} for r in rows}


def market_value(conn, catid, platforms=("Facebook", "In-Person"), currency="LYD", days=90,
                 include_archived=False):
    """Detailed local-market view for one catalogue item: count, min, average, median, max,
    and every contributing listing. Median is robust to the odd outlier in a thin market.
    Defaults to ACTIVE listings from the last `days` (days=None -> all time)."""
    ph = ",".join("?" * len(platforms))
    params = [catid, *platforms, currency]
    where = _market_where(days, include_archived)
    if days:
        params.append(f"-{int(days)} days")
    rows = conn.execute(
        f"SELECT al.lsid, al.platform, li.unit_price AS price, al.currency, al.seller_name, "
        f"al.date_of_listing, al.listing_name FROM listing_items li "
        f"JOIN all_listings al ON li.lsid=al.lsid "
        f"WHERE li.catid=? AND li.unit_price IS NOT NULL AND al.platform IN ({ph}) "
        f"AND al.currency=?{where} ORDER BY li.unit_price", params).fetchall()
    prices = sorted(money(r["price"]) for r in rows)
    n = len(prices)
    med = None
    if n:
        mid = n // 2
        med = prices[mid] if n % 2 else money((prices[mid - 1] + prices[mid]) / 2)
    listings = [{"lsid": r["lsid"], "platform": r["platform"], "price": money(r["price"]),
                 "currency": r["currency"], "seller": r["seller_name"],
                 "date": r["date_of_listing"], "name": r["listing_name"]} for r in rows]
    dates = sorted(r["date_of_listing"] for r in rows if r["date_of_listing"])
    return {"catid": catid, "currency": currency, "count": n, "days": days,
            "min": prices[0] if n else None, "max": prices[-1] if n else None,
            "avg": money(sum(prices) / n) if n else None, "median": med, "listings": listings,
            "date_from": dates[0] if dates else None, "date_to": dates[-1] if dates else None}


def market_value_trend(conn, catid, platforms=("Facebook", "In-Person"), currency="LYD",
                       months=12, include_archived=False):
    """[(YYYY-MM, median, n)] of local listing prices by month (dated, active listings only) —
    shows whether the local market is drifting under you."""
    ph = ",".join("?" * len(platforms))
    where = "" if include_archived else " AND COALESCE(al.is_archived,0)=0"
    rows = conn.execute(
        f"SELECT substr(al.date_of_listing,1,7) AS ym, li.unit_price AS price "
        f"FROM listing_items li JOIN all_listings al ON li.lsid=al.lsid "
        f"WHERE li.catid=? AND li.unit_price IS NOT NULL AND al.platform IN ({ph}) "
        f"AND al.currency=? AND al.date_of_listing IS NOT NULL AND al.date_of_listing!=''{where} "
        f"ORDER BY ym", (catid, *platforms, currency)).fetchall()
    by_month = {}
    for r in rows:
        by_month.setdefault(r["ym"], []).append(money(r["price"]))
    out = []
    for ym in sorted(by_month)[-months:]:
        ps = sorted(by_month[ym]); k = len(ps); mid = k // 2
        med = ps[mid] if k % 2 else money((ps[mid - 1] + ps[mid]) / 2)
        out.append((ym, med, k))
    return out


def get_market_rate(conn):
    """The CURRENT market USD->LYD rate (latest history row), or None if never set.
    This values LISTED items in reports; it never touches batches or cost basis."""
    r = conn.execute("SELECT rate FROM market_rate_history ORDER BY mrid DESC LIMIT 1").fetchone()
    return money(r["rate"]) if r else None


def set_market_rate(conn, rate):
    """Record a new current market rate (history is append-only, so every change and
    its timestamp is kept)."""
    rate = _positive(rate, "market rate")
    from datetime import datetime as _dt
    now = _dt.now()
    conn.execute("INSERT INTO market_rate_history(rate, set_date, set_time) VALUES(?,?,?)",
                 (fl(rate), now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")))
    _log(conn, "EDIT", "market_rate", 0, f"market USD rate set to {rate}")
    conn.commit()
    return rate


def market_rate_history(conn, limit=200):
    """Newest-first history of market-rate changes."""
    return [{"rate": money(r["rate"]), "date": r["set_date"], "time": r["set_time"]}
            for r in conn.execute("SELECT rate, set_date, set_time FROM market_rate_history "
                                  "ORDER BY mrid DESC LIMIT ?", (limit,))]


def catalog_performance(conn, filt=None, market_days=90):
    """Per catalogue item: listing / purchase / sale aggregates for market research.
    `platform` filters the listing side; `date_from/to` filter the sale side.
    Also carries the windowed local market value (`market_days`, archive-aware) so the
    report view and xlsx export agree with the Catalogue column and Market Value popup;
    market_days=None means all time."""
    f = filt or {}
    local = market_value_map(conn, days=market_days)
    vsfx = variant_suffix_map(conn)      # 'Dell 7520 (A)' vs '(B)' — two variants must be
                                         # tellable apart in the report table and xlsx export
    mkt_rate = get_market_rate(conn)
    cat_where, cat_params = ["1=1"], []
    if f.get("catid"):
        cat_where.append("catid=?"); cat_params.append(f["catid"])
    if f.get("category"):
        cat_where.append("category=?"); cat_params.append(f["category"])
    cats = conn.execute("SELECT catid, display_name, category FROM catalog_items WHERE "
                        + " AND ".join(cat_where) + " ORDER BY catid", cat_params).fetchall()
    plat = f.get("platform")
    db, dp = _between(f, "so.date_committed")
    out = []
    for ci in cats:
        catid = ci["catid"]
        # listings side — LYD-normalised: LYD prices as-is, USD prices at the CURRENT
        # market rate (never batch rates: batches are cost basis for owned dollars,
        # this is street value of a listing today). No rate set -> USD excluded.
        lq = ("SELECT al.currency AS cur, li.unit_price AS p FROM listing_items li "
              "JOIN all_listings al ON li.lsid=al.lsid WHERE li.catid=? AND li.unit_price IS NOT NULL "
              "AND COALESCE(al.is_archived,0)=0")   # archived = dead market signal, everywhere
        lp = [catid]
        if plat:
            lq += " AND al.platform=?"; lp.append(plat)
        lyd_prices = []
        n_listed = 0
        for lrow in conn.execute(lq, lp):
            n_listed += 1
            if (lrow["cur"] or "LYD").upper() == "LYD":
                lyd_prices.append(money(lrow["p"]))
            elif mkt_rate is not None:
                lyd_prices.append(money(Decimal(str(lrow["p"])) * mkt_rate))
        lr = {"n": n_listed,
              "avg_price": (sum(lyd_prices, Decimal("0")) / len(lyd_prices)) if lyd_prices else None}
        # purchases side
        pr = conn.execute(
            "SELECT COUNT(*) AS n, AVG(pl.unit_price_allocated) AS avg_cost FROM purchase_lines pl "
            "WHERE pl.catid=?", (catid,)).fetchone()
        # sales side
        sq = ("SELECT COUNT(*) AS n, AVG(s.sale_price) AS avg_sale, SUM(s.sale_price) AS vol, "
              "AVG(s.sale_price - COALESCE(i.total_cost,0)) AS avg_margin "
              "FROM sales s JOIN inventory_items i ON s.lywrid=i.lywrid "
              "JOIN sales_orders so ON s.sale_order_id=so.sale_order_id WHERE i.catid=?")
        sp = [catid]
        if db:
            sq += " AND " + db; sp += dp
        sr = conn.execute(sq, sp).fetchone()
        out.append({
            "catid": catid, "item": ci["display_name"] + vsfx.get(catid, ""),
            "category": ci["category"],
            "times_listed": lr["n"] or 0,
            "avg_listing_price": money(lr["avg_price"]) if lr["avg_price"] is not None else None,
            "qty_purchased": pr["n"] or 0,
            "avg_purchase_cost": money(pr["avg_cost"]) if pr["avg_cost"] is not None else None,
            "qty_sold": sr["n"] or 0,
            "avg_sale_price": money(sr["avg_sale"]) if sr["avg_sale"] is not None else None,
            "sale_volume": money(sr["vol"]) if sr["vol"] is not None else money(0),
            "avg_margin": money(sr["avg_margin"]) if sr["avg_margin"] is not None else None,
            "local_value_avg": (local.get(catid) or {}).get("avg"),
            "local_value_n": (local.get(catid) or {}).get("n", 0)})
    return out


def accounts_report(conn, filt=None):
    """Balance snapshot per account (LYD + USD)."""
    out = []
    for a in list_accounts(conn, include_hidden=True):
        out.append({"acctid": a["acctid"], "account": a["account_name"], "type": a["account_type"],
                    "lyd": lyd_balance(conn, a["acctid"]),
                    "usd": fx_balance(conn, a["acctid"], "USD"),
                    "hidden": bool(a["is_hidden"]), "created": (a["created_at"] or "")[:10]})
    return out


def dashboard_summary(conn):
    """Headline numbers for the Home tab bubbles (uses today's live state)."""
    from datetime import date
    one = lambda q, p=(): conn.execute(q, p).fetchone()[0]
    month_start = date.today().replace(day=1).isoformat()
    fs = financial_summary(conn, {"date_from": month_start})
    instock_v = money(one("SELECT COALESCE(SUM(total_cost),0) FROM inventory_items WHERE status='In Stock'"))
    accts = list_accounts(conn)
    cash = sum((lyd_balance(conn, a["acctid"]) for a in accts), money(0))
    usd = sum((fx_balance(conn, a["acctid"], "USD") for a in accts), money(0))
    top = conn.execute(
        "SELECT ci.display_name, COUNT(*) AS n FROM sales s JOIN inventory_items i ON s.lywrid=i.lywrid "
        "JOIN catalog_items ci ON i.catid=ci.catid GROUP BY i.catid ORDER BY n DESC LIMIT 1").fetchone()
    return {
        "instock_units": one("SELECT COUNT(*) FROM inventory_items WHERE status='In Stock'"),
        "instock_value": instock_v,
        "pending_units": one("SELECT COUNT(*) FROM inventory_items WHERE status='Pending Approval'"),
        "shipping_units": one("SELECT COUNT(*) FROM inventory_items i JOIN inventory_statuses st "
                              "ON i.status=st.status WHERE st.stage='shipping'"),
        "to_customer_units": one("SELECT COUNT(*) FROM sales_orders WHERE status='Shipping'"),
        "sold_units": one("SELECT COUNT(*) FROM inventory_items WHERE status='Sold'"),
        "cash_lyd": cash, "cash_usd": usd,
        "month_revenue": fs["revenue"], "month_expense": fs["expense"], "month_net": fs["net"],
        "open_listings": one("SELECT COUNT(*) FROM all_listings"),
        "catalog_items": one("SELECT COUNT(*) FROM catalog_items"),
        "top_item": (f'{top["display_name"]} ({top["n"]})' if top else "\u2014"),
    }


# ===========================================================================
# USER-ERROR PREVENTION — Phase 1 (safety) + Phase 2 (mistake correction)
# ---------------------------------------------------------------------------
# Philosophy: corrections ERASE/REWRITE a mistaken entry; they are distinct
# from exception events (cancel/return/write-off, Phase 3) which PRESERVE the
# record and post a compensating entry. Reference data is edited freely (it is
# FK-normalized so it propagates; the two denormalized snapshots are re-synced).
# Money-movers are only voidable while safe. Automatic DB snapshots are the
# universal backstop.
# ===========================================================================
import shutil as _shutil


def backup_dir(db_path=DB_PATH):
    d = os.path.join(os.path.dirname(os.path.abspath(db_path)) or ".", "lyware_backups")
    os.makedirs(d, exist_ok=True)
    return d


def make_backup(db_path=DB_PATH, reason="manual", keep=10):
    """Snapshot the live DB to a timestamped file using SQLite's online backup API, which
    is guaranteed consistent even while the app is writing (a raw file copy can capture a
    torn, mid-transaction state — the kind of backup that fails exactly when needed).
    Prunes to the newest `keep`."""
    if not os.path.exists(db_path):
        return None
    from datetime import datetime as _dt
    stamp = _dt.now().strftime("%Y%m%d-%H%M%S")
    safe = "".join(ch for ch in reason if ch.isalnum() or ch in "-_")[:24] or "snap"
    dest = os.path.join(backup_dir(db_path), f"{stamp}_{safe}.db")
    src = sqlite3.connect(db_path)
    try:
        dst = sqlite3.connect(dest)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    snaps = sorted(_list_backup_files(db_path))
    for old in snaps[:-keep] if keep else []:
        try:
            os.remove(old)
        except OSError:
            pass
    return dest


def export_backup(dest_path, db_path=DB_PATH):
    """Consistent snapshot of the live DB to a user-chosen location (USB stick, cloud
    folder) — an off-machine copy, so a dead disk doesn't take the data AND the backups."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(db_path)
    src = sqlite3.connect(db_path)
    try:
        dst = sqlite3.connect(dest_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return dest_path


def _list_backup_files(db_path=DB_PATH):
    d = backup_dir(db_path)
    return [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".db")]


def list_backups(db_path=DB_PATH):
    """Newest-first list of (path, label, size_bytes) for the Restore picker."""
    out = []
    for p in sorted(_list_backup_files(db_path), reverse=True):
        out.append((p, os.path.basename(p), os.path.getsize(p)))
    return out


def restore_backup(backup_path, db_path=DB_PATH):
    """Replace the live DB with a snapshot. Caller must close its connection first;
    the current live DB is itself snapshotted (reason 'pre-restore') beforehand."""
    if not os.path.exists(backup_path):
        raise FileNotFoundError(backup_path)
    make_backup(db_path, reason="pre-restore")
    _shutil.copy2(backup_path, db_path)
    return db_path


# ---- catalogue: hide / edit / delete --------------------------------------
def hide_catalog_item(conn, catid):
    conn.execute("UPDATE catalog_items SET is_hidden=1 WHERE catid=?", (catid,))
    _log(conn, "UPDATE", "catalog_item", catid, "hidden")
    conn.commit()


def unhide_catalog_item(conn, catid):
    conn.execute("UPDATE catalog_items SET is_hidden=0 WHERE catid=?", (catid,))
    _log(conn, "UPDATE", "catalog_item", catid, "unhidden")
    conn.commit()


def catalog_usage(conn, catid):
    """How many listings / purchase lines / inventory units reference this item."""
    one = lambda q: conn.execute(q, (catid,)).fetchone()[0]
    return {"listings": one("SELECT COUNT(*) FROM listing_items WHERE catid=?"),
            "purchases": one("SELECT COUNT(*) FROM purchase_lines WHERE catid=?"),
            "inventory": one("SELECT COUNT(*) FROM inventory_items WHERE catid=?")}


def edit_catalog_item(conn, catid, **kw):
    """Backwards-compatible alias for update_catalog_item (kept for callers/tests)."""
    return update_catalog_item(
        conn, catid, kw.get("category"), kw.get("display_name"),
        kw.get("manufacturer"), kw.get("model_name"), kw.get("attributes"))


def delete_catalog_item(conn, catid):
    """Hard-delete a catalogue item — ONLY when nothing references it. Cascades its
    attributes. If it is in use, raises (the caller should offer Hide instead)."""
    u = catalog_usage(conn, catid)
    if any(u.values()):
        raise StateError(f"catalog item {catid} is in use "
                         f"(listings {u['listings']}, purchases {u['purchases']}, "
                         f"inventory {u['inventory']}); hide it instead of deleting.")
    conn.execute("DELETE FROM catalog_items WHERE catid=?", (catid,))   # attributes cascade
    _log(conn, "DELETE", "catalog_item", catid, "deleted (was unused)")
    conn.commit()


# ---- listings: edit / delete ----------------------------------------------
def edit_listing(conn, lsid, link=None, price=None, currency=None, seller_name=None,
                 date_of_listing=None, reference=None, phone_number=None, qty_items=None,
                 listing_name=None, seller_link=None):
    """Edit a listing's fields. Updates the master row AND the platform subtype copies
    (the denormalized price/seller/link/reference) so they never drift."""
    al = conn.execute("SELECT * FROM all_listings WHERE lsid=?", (lsid,)).fetchone()
    if not al:
        raise ValueError(f"no listing {lsid}")
    platform = al["platform"]
    new_price = fl(money(price)) if price not in (None, "", "None") else (None if price == "" else al["price"])
    new_cur = currency if currency is not None else al["currency"]
    new_qty = int(qty_items) if str(qty_items).strip() not in ("", "None") else (
        None if qty_items == "" else al["qty_items"])
    sets = {"link": link if link is not None else al["link"],
            "price": new_price, "currency": new_cur,
            "seller_name": seller_name if seller_name is not None else al["seller_name"],
            "date_of_listing": date_of_listing if date_of_listing is not None else al["date_of_listing"],
            "phone_number": phone_number if phone_number is not None else al["phone_number"],
            "listing_name": listing_name if listing_name is not None else al["listing_name"],
            "seller_link": seller_link if seller_link is not None else al["seller_link"],
            "qty_items": new_qty}
    conn.execute("UPDATE all_listings SET link=?, price=?, currency=?, seller_name=?, "
                 "date_of_listing=?, phone_number=?, qty_items=?, listing_name=?, seller_link=? "
                 "WHERE lsid=?",
                 (sets["link"], sets["price"], sets["currency"], sets["seller_name"],
                  sets["date_of_listing"], sets["phone_number"], sets["qty_items"],
                  sets["listing_name"], sets["seller_link"], lsid))
    if platform == "eBay":
        conn.execute("UPDATE ebay_listings SET ebay_item_number=COALESCE(?,ebay_item_number), "
                     "link=?, price=?, currency=?, seller_name=? WHERE lsid=?",
                     (reference, sets["link"], sets["price"], sets["currency"], sets["seller_name"], lsid))
    elif platform == "Amazon":
        conn.execute("UPDATE amazon_listings SET asin=COALESCE(?,asin), link=?, price=?, currency=? "
                     "WHERE lsid=?", (reference, sets["link"], sets["price"], sets["currency"], lsid))
    elif platform == "Facebook":
        conn.execute("UPDATE facebook_listings SET link=? WHERE lsid=?", (sets["link"], lsid))
    elif platform == "In-Person":
        conn.execute("UPDATE inperson_listings SET seller_name=? WHERE lsid=?", (sets["seller_name"], lsid))
    _log(conn, "UPDATE", "listing", lsid, f"{platform} listing edited")
    conn.commit()


def set_listing_items(conn, lsid, items):
    """Replace the catalogue lines on a listing. `items` = [(catid, qty, unit_price), ...]."""
    conn.execute("DELETE FROM listing_items WHERE lsid=?", (lsid,))
    add_listing_items(conn, lsid, items)
    _log(conn, "UPDATE", "listing", lsid, f"{len(items)} item line(s) set")
    conn.commit()


def listing_usage(conn, lsid):
    return {"purchases": conn.execute(
        "SELECT COUNT(*) FROM purchase_orders WHERE lsid=?", (lsid,)).fetchone()[0]}


def delete_listing(conn, lsid):
    """Delete a listing — only when no purchase was made from it. Removes the subtype
    row and (cascade) its item lines."""
    if listing_usage(conn, lsid)["purchases"]:
        raise StateError("a purchase was recorded from this listing; edit it instead of deleting.")
    plat = conn.execute("SELECT platform FROM all_listings WHERE lsid=?", (lsid,)).fetchone()
    if not plat:
        raise ValueError(f"no listing {lsid}")
    sub = {"eBay": "ebay_listings", "Amazon": "amazon_listings",
           "Facebook": "facebook_listings", "In-Person": "inperson_listings"}[plat["platform"]]
    conn.execute(f"DELETE FROM {sub} WHERE lsid=?", (lsid,))
    conn.execute("DELETE FROM all_listings WHERE lsid=?", (lsid,))   # listing_items cascade
    _log(conn, "DELETE", "listing", lsid, "deleted (no purchase referenced it)")
    conn.commit()


# ---- accounts: edit / delete ----------------------------------------------
def account_usage(conn, acctid):
    one = lambda q: conn.execute(q, (acctid,)).fetchone()[0]
    return {"transactions": one("SELECT COUNT(*) FROM all_transactions WHERE acctid=?"),
            "fx_batches": one("SELECT COUNT(*) FROM fx_batches WHERE acctid=?")}


def edit_account(conn, acctid, account_name=None, account_type=None):
    """Rename an account; account_type may only change while it has no transactions."""
    a = conn.execute("SELECT * FROM accounts WHERE acctid=?", (acctid,)).fetchone()
    if not a:
        raise ValueError(f"no account {acctid}")
    name = (account_name if account_name is not None else a["account_name"]).strip()
    if not name:
        raise ValueError("account name is required")
    new_type = account_type if account_type is not None else a["account_type"]
    if new_type != a["account_type"] and account_usage(conn, acctid)["transactions"]:
        raise StateError("cannot change the type of an account that already has transactions.")
    conn.execute("UPDATE accounts SET account_name=?, account_type=? WHERE acctid=?",
                 (name, new_type, acctid))
    _log(conn, "UPDATE", "account", acctid, f"edited -> {name} ({new_type})")
    conn.commit()


def delete_account(conn, acctid):
    """Delete an account only when it has no transactions/FX. Otherwise hide it."""
    u = account_usage(conn, acctid)
    if any(u.values()):
        raise StateError("account has activity; hide it instead of deleting.")
    conn.execute("DELETE FROM accounts WHERE acctid=?", (acctid,))
    _log(conn, "DELETE", "account", acctid, "deleted (was unused)")
    conn.commit()


# ---- buyer / vendor metadata ----------------------------------------------
def edit_sale_order_meta(conn, sale_order_id, buyer_name=None, buyer_phone=None):
    o = conn.execute("SELECT * FROM sales_orders WHERE sale_order_id=?", (sale_order_id,)).fetchone()
    if not o:
        raise ValueError(f"no sale order {sale_order_id}")
    bn = buyer_name if buyer_name is not None else o["buyer_name"]
    bp = buyer_phone if buyer_phone is not None else o["buyer_phone"]
    conn.execute("UPDATE sales_orders SET buyer_name=?, buyer_phone=? WHERE sale_order_id=?",
                 (bn, bp, sale_order_id))
    _log(conn, "UPDATE", "sale_order", sale_order_id, "buyer details edited")
    conn.commit()


def edit_purchase_meta(conn, poid, vendor_name=None, order_date=None, purchaser_name=None):
    o = conn.execute("SELECT * FROM purchase_orders WHERE poid=?", (poid,)).fetchone()
    if not o:
        raise ValueError(f"no purchase order {poid}")
    vn = vendor_name if vendor_name is not None else o["vendor_name"]
    od = order_date if order_date is not None else o["order_date"]
    pn = purchaser_name if purchaser_name is not None else o["purchaser_name"]
    conn.execute("UPDATE purchase_orders SET vendor_name=?, order_date=?, purchaser_name=? WHERE poid=?",
                 (vn, od, pn, poid))
    _log(conn, "UPDATE", "purchase_order", poid, "purchase details edited")
    conn.commit()


# ---- adjust shipping cost (their example) ---------------------------------
def adjust_shipping_cost(conn, shipid, new_total_lyd, settle_acctid):
    """Correct the LYD cost recorded for a shipping leg. The difference is settled in
    LYD from/to `settle_acctid` (charge if the corrected cost is higher, refund if lower).
    Unfrozen items re-apportion automatically; already-frozen item costs are untouched."""
    sh = conn.execute("SELECT shipid, lyd_shipping_cost FROM shipments WHERE shipid=?",
                      (shipid,)).fetchone()
    if not sh:
        raise ValueError(f"no shipment {shipid}")
    old = money(sh["lyd_shipping_cost"]) if sh["lyd_shipping_cost"] is not None else money(0)
    new = money(new_total_lyd)
    delta = money(new - old)
    if delta > 0:
        if lyd_balance(conn, settle_acctid) < delta:
            raise InsufficientLYD(f"account {settle_acctid} cannot afford {delta} LYD")
        _txn(conn, settle_acctid, "Shipping_Expense", -delta, "LYD")
    elif delta < 0:
        _txn(conn, settle_acctid, "Shipping_Expense", -delta, "LYD")   # -delta is positive -> refund
    conn.execute("UPDATE shipments SET shipping_cost=?, shipping_cost_currency='LYD', lyd_shipping_cost=? "
                 "WHERE shipid=?", (fl(new), fl(new), shipid))
    _log(conn, "UPDATE", "shipment", shipid, f"shipping cost corrected {old} -> {new} LYD")
    conn.commit()
    return delta


# ---- reverse the last shipping / inventory step ---------------------------
def _credit_account(conn, acctid, amount, currency, ttype, rate=None, source="Refund"):
    """Append-only credit to an account (never rewinds FIFO). LYD adds to balance;
    FX adds a fresh batch at `rate`. Returns the transaction id."""
    amount = money(amount)
    tid = _txn(conn, acctid, ttype, amount, currency)
    if currency != "LYD":
        if rate is None:
            raise ValueError("a rate is required to credit foreign currency")
        _create_batch(conn, acctid, tid, currency, amount, money(rate), source)
    return tid


def _reverse_shipping_payment(conn, shipid):
    """Refund whatever was paid on a shipping leg, append-only, to the paying account."""
    sh = conn.execute("SELECT shipping_cost, shipping_cost_currency, lyd_shipping_cost, "
                      "shipping_paid_trnsid FROM shipments WHERE shipid=?", (shipid,)).fetchone()
    if not sh or sh["lyd_shipping_cost"] is None or not sh["shipping_paid_trnsid"]:
        return
    acct = conn.execute("SELECT acctid FROM all_transactions WHERE trnsid=?",
                        (sh["shipping_paid_trnsid"],)).fetchone()
    if not acct:
        return
    cur = sh["shipping_cost_currency"] or "LYD"
    if cur == "LYD":
        _credit_account(conn, acct["acctid"], money(sh["lyd_shipping_cost"]), "LYD", "Shipping_Expense")
    else:
        usd = money(sh["shipping_cost"])
        rate = money(Decimal(str(sh["lyd_shipping_cost"])) / usd) if usd else money(0)
        _credit_account(conn, acct["acctid"], usd, cur, "Shipping_Expense", rate=rate, source="Refund")


def can_reverse_last_status(conn, lywrid):
    """(ok, message) — whether the most recent status step on this unit can be safely undone."""
    s = get_item_status(conn, lywrid)
    if s in ("Sold", "Sold Pending"):
        return False, "This unit is in a sale — use the sales tools to undo that, not shipping reverse."
    if s == "In Stock":
        adj_tx = conn.execute("SELECT cost_adjustment_trnsid FROM inventory_items WHERE lywrid=?",
                              (lywrid,)).fetchone()["cost_adjustment_trnsid"]
        if _adjustment_refund_consumed(conn, adj_tx):
            return False, ("This unit's cost-adjustment refund has already been spent; you can't "
                           "unwind the acceptance until that spend is undone.")
    if s in ("Cancelled", "Written Off", "Returned to Seller", "Customer Returned"):
        return False, "This unit is in a terminal state recorded as an event; it isn't a step to undo."
    if s == "Awaiting Shipment":
        return False, "Nothing precedes this step except the purchase itself (void the purchase instead)."
    if s == "Pending Approval":
        has_local = conn.execute(
            "SELECT 1 FROM shipment_items si JOIN shipments s ON si.shipid=s.shipid "
            "WHERE si.lywrid=? AND s.shipment_type='Local' LIMIT 1", (lywrid,)).fetchone()
        has_intl_pickup = conn.execute(
            "SELECT 1 FROM shipment_items si JOIN shipments s ON si.shipid=s.shipid "
            "JOIN international_shipping i ON i.shipid=s.shipid WHERE si.lywrid=? "
            "AND i.date_picked_up IS NOT NULL LIMIT 1", (lywrid,)).fetchone()
        if not (has_local or has_intl_pickup):
            return False, "This was bought in person and entered the queue directly — there is no shipping step to undo."
    return True, ""


def reverse_last_status(conn, lywrid, date=None):
    """Reverse ONLY the single most recent shipping/inventory transition on this unit,
    operating on the whole group where the forward step was group-based. Guarded so it
    never runs when something downstream has happened."""
    ok, msg = can_reverse_last_status(conn, lywrid)
    if not ok:
        raise StateError(msg)
    s = get_item_status(conn, lywrid)
    if s == "In Stock":                                  # undo accept_into_inventory
        if conn.execute("SELECT 1 FROM sales WHERE lywrid=? LIMIT 1", (lywrid,)).fetchone():
            raise StateError("this unit is attached to a sale; remove it from the sale first.")
        adj_tx = conn.execute("SELECT cost_adjustment_trnsid FROM inventory_items WHERE lywrid=?",
                              (lywrid,)).fetchone()["cost_adjustment_trnsid"]
        _undo_money_movement(conn, adj_tx)               # refunds/expenses unwound with the accept
        conn.execute("UPDATE inventory_items SET status='Pending Approval', total_cost=NULL, "
                     "date_entered_inventory=NULL, cost_adjustment=0, cost_adjustment_note=NULL, "
                     "cost_adjustment_trnsid=NULL WHERE lywrid=?", (lywrid,))
        _log(conn, "STATUS", "inventory_item", lywrid, "reversed accept -> Pending Approval (cost unfrozen)")
    elif s == "Pending Approval":                        # undo receive_at_shop / pickup_to_shop
        loc = _shipment_peers(conn, lywrid, "Local", "Pending Approval")
        if loc[1]:
            for lid in loc[0]:
                _set_status(conn, lid, "At Local Office")
        else:
            grp, shipid = _shipment_peers(conn, lywrid, "International", "Pending Approval")
            for lid in grp:
                _set_status(conn, lid, "At Libya Warehouse")
            if shipid:
                conn.execute("UPDATE international_shipping SET date_picked_up=NULL WHERE shipid=?", (shipid,))
    elif s == "At Local Office":                         # undo mark_arrived_local_office
        grp, shipid = _shipment_peers(conn, lywrid, "Local", "At Local Office")
        for lid in grp:
            _set_status(conn, lid, "Local Transit")
        if shipid:
            conn.execute("UPDATE local_shipping SET date_arrived_local_office=NULL WHERE shipid=?", (shipid,))
    elif s == "Local Transit":                           # undo start_local_shipment (refund + delete leg)
        grp, shipid = _shipment_peers(conn, lywrid, "Local", "Local Transit")
        back = "At Libya Warehouse" if conn.execute(
            "SELECT 1 FROM shipment_items si JOIN shipments s ON si.shipid=s.shipid "
            "JOIN international_shipping i ON i.shipid=s.shipid WHERE si.lywrid=? "
            "AND i.date_arrived_libya_warehouse IS NOT NULL LIMIT 1", (lywrid,)).fetchone() else "Awaiting Shipment"
        if shipid:
            _reverse_shipping_payment(conn, shipid)
            conn.execute("DELETE FROM shipment_items WHERE shipid=?", (shipid,))
            conn.execute("DELETE FROM local_shipping WHERE shipid=?", (shipid,))
            conn.execute("DELETE FROM shipments WHERE shipid=?", (shipid,))
        for lid in grp:
            _set_status(conn, lid, back)
        _log(conn, "STATUS", "shipment", shipid or lywrid, f"reversed local start -> {back} (refunded)")
    elif s == "At Libya Warehouse":                      # undo mark_arrived_libya_warehouse
        grp, shipid = _shipment_peers(conn, lywrid, "International", "At Libya Warehouse")
        for lid in grp:
            _set_status(conn, lid, "International Transit")
        if shipid:
            conn.execute("UPDATE international_shipping SET date_arrived_libya_warehouse=NULL WHERE shipid=?",
                         (shipid,))
    elif s == "International Transit":                    # undo US-warehouse arrival, else the start
        grp, shipid = _shipment_peers(conn, lywrid, "International", "International Transit")
        usw = conn.execute("SELECT date_arrived_us_warehouse FROM international_shipping WHERE shipid=?",
                           (shipid,)).fetchone() if shipid else None
        if usw and usw["date_arrived_us_warehouse"]:
            conn.execute("UPDATE international_shipping SET date_arrived_us_warehouse=NULL WHERE shipid=?",
                         (shipid,))
            _log(conn, "STATUS", "shipment", shipid, "reversed US-warehouse arrival (still in transit)")
        else:
            for lid in grp:
                _set_status(conn, lid, "Awaiting Shipment")
            _log(conn, "STATUS", "shipment", shipid or lywrid,
                 "reversed international start -> Awaiting Shipment")
    else:
        raise StateError(f"no reversible step for status '{s}'.")
    conn.commit()


# ===========================================================================
# EXCEPTION EVENTS — Phase 3 (cancellations / write-offs / returns)
# ---------------------------------------------------------------------------
# These are real business events, NOT mistakes: they PRESERVE the original
# record and post a compensating entry, then move the unit to a terminal
# 'closed' status. Refunds are append-only credits (no FIFO rewind). The signed
# LYD cash impact of the closure is stamped on the unit (closure_recovery) for
# the Losses & Returns report. A unit's sunk cost is its frozen total_cost if it
# reached stock, else its live cost breakdown.
# ===========================================================================
_PRE_STOCK = {"Awaiting Shipment", "International Transit", "At Libya Warehouse",
              "Local Transit", "At Local Office", "Pending Approval"}


def unit_sunk_cost(conn, lywrid):
    """LYD cost tied up in a unit: frozen total if it reached stock, else live breakdown."""
    r = conn.execute("SELECT total_cost FROM inventory_items WHERE lywrid=?", (lywrid,)).fetchone()
    if r and r["total_cost"] is not None:
        return money(r["total_cost"])
    return item_cost_breakdown(conn, lywrid)["total"]


def _close_unit(conn, lywrid, status, recovery_lyd, date, note):
    conn.execute("UPDATE inventory_items SET status=?, closure_recovery=?, closure_note=?, "
                 "closure_date=? WHERE lywrid=?",
                 (status, fl(money(recovery_lyd)), note, date, lywrid))
    _log(conn, "STATUS", "inventory_item", lywrid, f"-> {status} (recovery {money(recovery_lyd)} LYD)")


def cancel_item(conn, lywrid, date, refund_amount=0, refund_currency="LYD", refund_acctid=None,
                refund_rate=None, note=None):
    """Seller cancelled / the item never arrived. The unit -> Cancelled; siblings in its
    shipment group are untouched (group ops skip a closed unit). Optionally records the
    seller's refund as an append-only credit that offsets the original purchase expense."""
    s = get_item_status(conn, lywrid)
    if s not in _PRE_STOCK:
        raise StateError(f"only a pre-stock unit can be cancelled (this one is '{s}').")
    recovery = money(0)
    if refund_amount and refund_acctid:
        amt = money(refund_amount)
        _credit_account(conn, refund_acctid, amt, refund_currency, "Refund_Received", refund_rate, "Refund (cancel)")
        recovery = amt if refund_currency == "LYD" else money(amt * money(refund_rate or 0))
    _close_unit(conn, lywrid, "Cancelled", recovery, date, note)
    conn.commit()


def write_off_item(conn, lywrid, date, extra_expense=0, expense_currency="LYD", expense_acctid=None,
                   note=None):
    """Scrap a damaged/defective unit (from the approval gate OR from stock). The unit's
    cost is already a sunk purchase expense, so no entry is needed for the loss itself;
    an OPTIONAL extra expense (disposal, etc.) may be recorded."""
    s = get_item_status(conn, lywrid)
    if s not in _PRE_STOCK and s != "In Stock":
        raise StateError(f"can only write off a pre-stock or in-stock unit (this one is '{s}').")
    recovery = money(0)
    if extra_expense and expense_acctid:
        amt = money(extra_expense)
        _spend_fx_or_lyd(conn, expense_acctid, "Business_Expense", amt, expense_currency)
        recovery = money(-amt) if expense_currency == "LYD" else money(0)   # extra cost = negative recovery
        _log(conn, "INSERT", "transaction", expense_acctid, f"damage expense {amt} {expense_currency}")
    _close_unit(conn, lywrid, "Written Off", recovery, date, note)
    conn.commit()


def return_to_seller(conn, lywrid, date, refund_amount=0, refund_currency="LYD", refund_acctid=None,
                     refund_rate=None, note=None):
    """Send a unit back to the seller (from the approval gate or while pre-stock).
    Optionally records the refund as an append-only credit."""
    s = get_item_status(conn, lywrid)
    if s not in _PRE_STOCK:
        raise StateError(f"only a pre-stock unit can be returned to the seller (this one is '{s}').")
    recovery = money(0)
    if refund_amount and refund_acctid:
        amt = money(refund_amount)
        _credit_account(conn, refund_acctid, amt, refund_currency, "Refund_Received", refund_rate,
                        "Refund (return to seller)")
        recovery = amt if refund_currency == "LYD" else money(amt * money(refund_rate or 0))
    _close_unit(conn, lywrid, "Returned to Seller", recovery, date, note)
    conn.commit()


def customer_return(conn, lywrid, date, refund_amount=0, refund_currency="LYD", refund_acctid=None,
                    restock=True, note=None):
    """A customer returns a sold unit (works even after finalation). Refunds the customer
    (money out; a negative-Sale contra that reduces net revenue), then either restocks the
    unit (back to In Stock, frozen cost preserved) or closes it as Customer Returned."""
    s = get_item_status(conn, lywrid)
    if s not in ("Sold", "Sold Pending"):
        raise StateError(f"only a sold unit can be customer-returned (this one is '{s}').")
    refund_lyd = money(0)
    if refund_amount and refund_acctid:
        amt = money(refund_amount)
        if refund_currency == "LYD":
            _txn(conn, refund_acctid, "Refund_Issued", -amt, "LYD")   # contra revenue, money out
        else:
            _spend_fx_or_lyd(conn, refund_acctid, "Refund_Issued", amt, refund_currency)
        refund_lyd = amt if refund_currency == "LYD" else amt       # LYD-equiv shown for reporting
        _log(conn, "INSERT", "transaction", refund_acctid, f"customer refund {amt} {refund_currency}")
    if restock:
        conn.execute("UPDATE inventory_items SET status='In Stock', closure_recovery=0, "
                     "closure_note=?, closure_date=? WHERE lywrid=?",
                     ((note or "") + " [restocked after return]", date, lywrid))
        _log(conn, "STATUS", "inventory_item", lywrid, "customer return -> restocked (In Stock)")
    else:
        _close_unit(conn, lywrid, "Customer Returned", money(-refund_lyd), date, note)
    conn.commit()


def void_sale_order(conn, sale_order_id):
    """Undo a sale that never completed (status 'Order Placed' or 'Shipping'). Items return
    to In Stock; any customer-shipping the shop paid is refunded; the order is removed. (A
    correction — use customer_return for a FINALIZED order.)"""
    o = conn.execute("SELECT * FROM sales_orders WHERE sale_order_id=?", (sale_order_id,)).fetchone()
    if not o:
        raise ValueError(f"no sale order {sale_order_id}")
    if o["status"] not in ("Order Placed", "Shipping"):
        raise StateError(f"order {sale_order_id} is '{o['status']}'; only an un-finalized order can be voided.")
    # refund any customer shipping the shop bore
    for cs in conn.execute("SELECT shipping_paid_trnsid, shipping_cost, shipping_cost_currency "
                           "FROM customer_shipments WHERE sale_order_id=? AND shipping_paid_trnsid IS NOT NULL",
                           (sale_order_id,)):
        acct = conn.execute("SELECT acctid FROM all_transactions WHERE trnsid=?",
                            (cs["shipping_paid_trnsid"],)).fetchone()
        if acct and cs["shipping_cost"]:
            _credit_account(conn, acct["acctid"], money(cs["shipping_cost"]),
                            cs["shipping_cost_currency"] or "LYD", "Shipping_Expense")
    for r in conn.execute("SELECT lywrid FROM sales WHERE sale_order_id=?", (sale_order_id,)):
        _set_status(conn, r["lywrid"], "In Stock")
    conn.execute("DELETE FROM customer_shipments WHERE sale_order_id=?", (sale_order_id,))
    conn.execute("DELETE FROM sales WHERE sale_order_id=?", (sale_order_id,))
    conn.execute("DELETE FROM sales_orders WHERE sale_order_id=?", (sale_order_id,))
    _log(conn, "DELETE", "sale_order", sale_order_id, "voided (un-finalized) -> items back in stock")
    conn.commit()


def losses_report(conn, filt=None):
    """Phase 4: every closed/terminal unit (cancelled, written off, returned to seller,
    customer returned) with its sunk cost, recorded recovery and net impact in LYD."""
    f = filt or {}
    where, params = ["i.status IN ('Cancelled','Written Off','Returned to Seller','Customer Returned')"], []
    db, dp = _between(f, "i.closure_date")
    if db:
        where.append(db); params += dp
    if f.get("status"):
        where.append("i.status=?"); params.append(f["status"])
    if f.get("catid"):
        where.append("i.catid=?"); params.append(f["catid"])
    if f.get("category"):
        where.append("ci.category=?"); params.append(f["category"])
    rows = conn.execute(
        "SELECT i.lywrid, pl.item_name, i.status, i.closure_date, i.closure_recovery, i.closure_note "
        "FROM inventory_items i JOIN purchase_lines pl ON i.polnid=pl.polnid "
        "LEFT JOIN catalog_items ci ON i.catid=ci.catid WHERE " + " AND ".join(where) +
        " ORDER BY i.closure_date DESC, i.lywrid DESC", params).fetchall()
    out = []
    for r in rows:
        cost = unit_sunk_cost(conn, r["lywrid"])
        recovery = money(r["closure_recovery"])
        # customer-returned: the cost was offset by the (retained) sale, so net impact is the refund
        if r["status"] == "Customer Returned":
            net = recovery            # already negative (refund paid)
        else:
            net = money(recovery - cost)   # negative = loss
        out.append({"lywrid": r["lywrid"], "item": r["item_name"], "status": r["status"],
                    "date": r["closure_date"], "cost": cost, "recovery": recovery,
                    "net": net, "note": r["closure_note"]})
    return out


def losses_summary(conn, filt=None):
    """Headline totals for the Losses & Returns view / Home."""
    rows = losses_report(conn, filt)
    by = {}
    for r in rows:
        by[r["status"]] = by.get(r["status"], 0) + 1
    total_cost = sum((r["cost"] for r in rows if r["status"] != "Customer Returned"), money(0))
    total_recovery = sum((r["recovery"] for r in rows), money(0))
    net = sum((r["net"] for r in rows), money(0))
    return {"count": len(rows), "by_status": by, "sunk_cost": money(total_cost),
            "recovery": money(total_recovery), "net": money(net)}


# ===========================================================================
# TRANSACTION REVERSAL & EDIT  (QOL: undo a money mistake safely)
# ---------------------------------------------------------------------------
# Foolproof principle: a transaction may be reversed ONLY when nothing downstream
# depends on it; otherwise we refuse and say exactly what to unwind first. The
# schema makes this exact rather than guesswork:
#   * fx_batches.trnsid       -> the txn that CREATED a USD batch
#   * batch_allocations.trnsid-> the txn that CONSUMED USD (with the precise split)
#   * linked_transfer_id      -> ties a transfer's legs / a sale's FX g/l together
# Reversal restores consumed batches from their allocation records, deletes any
# unconsumed batch the txn created, removes the whole linked group, and verifies
# no account is left negative — all inside a SAVEPOINT so a bad case rolls back
# cleanly. Product-linked transactions are redirected to their proper unwind tool.
# ===========================================================================

# Types that are entangled with inventory/sales/shipping and must be unwound via
# their dedicated tools, never by deleting the bare transaction.
_REVERSAL_REDIRECT = {
    "Purchase": "This paid for a purchase. Cancel the unit(s) it bought from the Inventory / "
                "Shipping tabs (that refunds correctly); don't reverse the raw payment.",
    "Shipping_Expense": "This paid for shipping. Use 'Adjust shipping cost' or 'Undo last step' on "
                        "the item's shipping dialog instead.",
    "Sale": "This is sale revenue. Void the order (before finalizing) or use 'Customer Return' on "
            "the Sales tab.",
    "Refund_Received": "This refund is tied to a cancellation / return. Undo it from the item that "
                       "generated it.",
    "Refund_Issued": "This refund is tied to a customer return. Undo it from the sale / item that "
                     "generated it.",
}


def _linked_group(conn, trnsid):
    """All transaction ids joined to this one through linked_transfer_id (a transfer's
    out/in/fee legs, or a conversion-sell + its FX gain/loss). Single id if standalone."""
    ids, frontier = {trnsid}, [trnsid]
    while frontier:
        cur = frontier.pop()
        row = conn.execute("SELECT linked_transfer_id FROM all_transactions WHERE trnsid=?",
                           (cur,)).fetchone()
        nxt = []
        if row and row["linked_transfer_id"] and row["linked_transfer_id"] not in ids:
            nxt.append(row["linked_transfer_id"])
        for r in conn.execute("SELECT trnsid FROM all_transactions WHERE linked_transfer_id=?", (cur,)):
            if r["trnsid"] not in ids:
                nxt.append(r["trnsid"])
        for n in nxt:
            ids.add(n); frontier.append(n)
    return ids


def transaction_reversibility(conn, trnsid):
    """(ok, reason) — pure check, no mutation. `reason` explains a block in plain language."""
    base = conn.execute("SELECT * FROM all_transactions WHERE trnsid=?", (trnsid,)).fetchone()
    if not base:
        return False, "That transaction no longer exists."
    group = _linked_group(conn, trnsid)
    for tid in group:
        if conn.execute("SELECT 1 FROM inventory_items WHERE cost_adjustment_trnsid=?", (tid,)).fetchone():
            return False, ("This is an item's cost adjustment. Undo it from the item itself — "
                           "reverse the acceptance on the Inventory tab — not from the ledger.")
        r = conn.execute("SELECT type FROM all_transactions WHERE trnsid=?", (tid,)).fetchone()
        if r["type"] in _REVERSAL_REDIRECT:
            return False, _REVERSAL_REDIRECT[r["type"]]
    # any USD this group created must be entirely unspent
    for tid in group:
        spent = conn.execute(
            "SELECT COALESCE(SUM(ba.fx_consumed),0) AS s FROM batch_allocations ba "
            "JOIN fx_batches b ON ba.bachid=b.bachid WHERE b.trnsid=?", (tid,)).fetchone()["s"]
        if money(spent) > 0:
            b = conn.execute("SELECT currency FROM fx_batches WHERE trnsid=? LIMIT 1", (tid,)).fetchone()
            cur = b["currency"] if b else "USD"
            return False, (f"Some of the {cur} from this has already been spent (on a purchase or "
                           "conversion). Cancel whatever used it first, then reverse this.")
    return True, ""


def reverse_transaction(conn, trnsid):
    """Delete a transaction (and its linked group) and undo its money effects exactly:
    restore consumed FX batches, drop any unconsumed batch it created, remove a business
    -expense detail row, and refuse (rolling back) if it would overdraw any account."""
    ok, reason = transaction_reversibility(conn, trnsid)
    if not ok:
        raise StateError(reason)
    group = sorted(_linked_group(conn, trnsid))
    summary = []
    affected = set()
    conn.execute("SAVEPOINT revtxn")
    try:
        for tid in group:
            r = conn.execute("SELECT acctid, type, amount, currency FROM all_transactions WHERE trnsid=?",
                             (tid,)).fetchone()
            affected.add(r["acctid"])
            summary.append(f"{r['type']} {money(r['amount'])} {r['currency']}")
            # restore FX this txn consumed
            for a in conn.execute("SELECT alocid, bachid, fx_consumed FROM batch_allocations WHERE trnsid=?",
                                  (tid,)):
                b = conn.execute("SELECT acctid, fx_remaining FROM fx_batches WHERE bachid=?",
                                 (a["bachid"],)).fetchone()
                affected.add(b["acctid"])
                conn.execute("UPDATE fx_batches SET fx_remaining=? WHERE bachid=?",
                             (fl(money(Decimal(str(b["fx_remaining"])) + Decimal(str(a["fx_consumed"])))),
                              a["bachid"]))
                conn.execute("DELETE FROM batch_allocations WHERE alocid=?", (a["alocid"],))
            # drop any (verified unconsumed) batch this txn created
            for b in conn.execute("SELECT bachid, acctid FROM fx_batches WHERE trnsid=?", (tid,)):
                affected.add(b["acctid"])
                conn.execute("DELETE FROM fx_batches WHERE bachid=?", (b["bachid"],))
            # business-expense detail row
            conn.execute("DELETE FROM business_expenses WHERE trnsid=?", (tid,))
        # break cross-links, then delete the transactions
        for tid in group:
            conn.execute("UPDATE all_transactions SET linked_transfer_id=NULL WHERE trnsid=?", (tid,))
        for tid in group:
            conn.execute("DELETE FROM all_transactions WHERE trnsid=?", (tid,))
        # never leave an account negative (e.g. reversing a deposit already spent)
        for acctid in affected:
            if lyd_balance(conn, acctid) < 0:
                raise StateError("Reversing this would overdraw an account — the funds were already "
                                 "used. Undo the later activity first.")
            for cur in [x["currency"] for x in conn.execute(
                    "SELECT DISTINCT currency FROM fx_batches WHERE acctid=?", (acctid,))]:
                if fx_balance(conn, acctid, cur) < 0:
                    raise StateError(f"Reversing this would leave a negative {cur} balance.")
        conn.execute("RELEASE revtxn")
    except Exception:
        conn.execute("ROLLBACK TO revtxn")
        conn.execute("RELEASE revtxn")
        raise
    _log(conn, "DELETE", "transaction", trnsid, "reversed: " + "; ".join(summary))
    conn.commit()
    return group


# Simple cash transactions whose amount/date can be corrected in place.
_EDITABLE_TYPES = {"Deposit", "Withdrawal", "Business_Expense", "FX_Gain_Loss"}


def edit_transaction(conn, trnsid, new_amount=None, new_date=None):
    """Correct a simple LYD cash transaction's amount and/or date in place. Only types
    with no FX/inventory entanglement qualify; for anything else, reverse and re-enter."""
    t = conn.execute("SELECT * FROM all_transactions WHERE trnsid=?", (trnsid,)).fetchone()
    if not t:
        raise ValueError("no such transaction")
    if _linked_group(conn, trnsid) != {trnsid}:
        raise StateError("This is part of a linked transfer/conversion; reverse and re-enter it instead.")
    if t["type"] not in _EDITABLE_TYPES or t["currency"] != "LYD":
        raise StateError("Only simple LYD cash transactions (deposit, withdrawal, business expense, "
                         "FX adjustment) can be edited directly. For others, reverse and re-enter.")
    conn.execute("SAVEPOINT edittxn")
    try:
        if new_amount is not None and str(new_amount).strip() != "":
            sign = -1 if Decimal(str(t["amount"])) < 0 else 1
            newamt = money(sign * abs(money(new_amount)))
            conn.execute("UPDATE all_transactions SET amount=? WHERE trnsid=?", (fl(newamt), trnsid))
            if lyd_balance(conn, t["acctid"]) < 0:
                raise StateError("That amount would overdraw the account.")
        if new_date and str(new_date).strip():
            conn.execute("UPDATE all_transactions SET date=? WHERE trnsid=?", (new_date, trnsid))
            conn.execute("UPDATE business_expenses SET date=? WHERE trnsid=?", (new_date, trnsid))
        conn.execute("RELEASE edittxn")
    except Exception:
        conn.execute("ROLLBACK TO edittxn"); conn.execute("RELEASE edittxn"); raise
    _log(conn, "UPDATE", "transaction", trnsid, "edited amount/date")
    conn.commit()


# --- health check + inventory aging (v10 upgrade pass) --------------------------------

def health_check(conn):
    """One-click consistency audit of the live database. Returns a list of
    {'check', 'ok', 'detail'} rows: SQLite's own integrity scan plus LYWARE's invariants
    (FIFO batches never negative, no orphaned rows, ledger vs balances reconcile)."""
    out = []

    def add(name, ok, detail=""):
        out.append({"check": name, "ok": bool(ok), "detail": detail})

    row = conn.execute("PRAGMA integrity_check").fetchone()
    add("SQLite file integrity", row and row[0] == "ok", row[0] if row else "no result")

    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    add("Foreign keys consistent", len(fk) == 0,
        "" if not fk else f"{len(fk)} broken reference(s), e.g. table {fk[0][0]}")

    neg = conn.execute("SELECT COUNT(*) AS n FROM fx_batches WHERE fx_remaining < -0.0001").fetchone()["n"]
    add("No negative FX batch remainders", neg == 0, "" if not neg else f"{neg} batch(es) negative")

    over = conn.execute(
        "SELECT b.bachid FROM fx_batches b LEFT JOIN batch_allocations a ON a.bachid=b.bachid "
        "GROUP BY b.bachid HAVING COALESCE(SUM(a.fx_consumed),0) - (b.fx_amount - b.fx_remaining) "
        "NOT BETWEEN -0.01 AND 0.01").fetchall()
    add("Batch consumption matches allocations", len(over) == 0,
        "" if not over else f"batch(es) {[r['bachid'] for r in over[:5]]} out of step")

    orphan_alloc = conn.execute(
        "SELECT COUNT(*) AS n FROM batch_allocations a LEFT JOIN fx_batches b ON a.bachid=b.bachid "
        "WHERE b.bachid IS NULL").fetchone()["n"]
    add("No orphaned batch allocations", orphan_alloc == 0,
        "" if not orphan_alloc else f"{orphan_alloc} allocation(s) point at missing batches")

    orphan_inv = conn.execute(
        "SELECT COUNT(*) AS n FROM inventory_items i LEFT JOIN purchase_lines pl ON i.polnid=pl.polnid "
        "WHERE pl.polnid IS NULL").fetchone()["n"]
    add("Every inventory unit has a purchase line", orphan_inv == 0,
        "" if not orphan_inv else f"{orphan_inv} unit(s) orphaned")

    orphan_sale = conn.execute(
        "SELECT COUNT(*) AS n FROM sales s LEFT JOIN inventory_items i ON s.lywrid=i.lywrid "
        "WHERE i.lywrid IS NULL").fetchone()["n"]
    add("Every sale row has an inventory unit", orphan_sale == 0,
        "" if not orphan_sale else f"{orphan_sale} sale row(s) orphaned")

    stray_ship = conn.execute(
        "SELECT COUNT(*) AS n FROM shipment_items si LEFT JOIN shipments s ON si.shipid=s.shipid "
        "WHERE s.shipid IS NULL").fetchone()["n"]
    add("Shipment items all belong to shipments", stray_ship == 0,
        "" if not stray_ship else f"{stray_ship} stray shipment item(s)")

    # per-account: ledger sum of LYD movements should reconcile with the computed balance.
    # Must apply the same affects_balance rule as lyd_balance — informational rows like
    # FX_Gain_Loss carry an amount but don't move money, and a naive SUM would cry wolf
    # on every currency conversion.
    bad_bal = []
    for a in conn.execute("SELECT acctid, account_name FROM accounts"):
        led = conn.execute(
            "SELECT COALESCE(SUM(t.amount),0) AS s FROM all_transactions t "
            "JOIN transaction_types tt ON t.type=tt.type "
            "WHERE t.acctid=? AND t.currency='LYD' AND tt.affects_balance=1",
            (a["acctid"],)).fetchone()["s"]
        if abs(float(lyd_balance(conn, a["acctid"])) - float(led)) > 0.01:
            bad_bal.append(a["account_name"])
    add("LYD balances reconcile with ledger", not bad_bal,
        "" if not bad_bal else f"accounts out of step: {bad_bal[:4]}")

    dup_var = conn.execute(
        "SELECT LOWER(TRIM(display_name)) AS fam, LOWER(TRIM(variant)) AS v, COUNT(*) AS n "
        "FROM catalog_items GROUP BY fam, v HAVING n > 1").fetchall()
    add("Variant labels unique within families", len(dup_var) == 0,
        "" if not dup_var else f"{len(dup_var)} clash(es), e.g. '{dup_var[0]['fam']}' variant "
                               f"'{dup_var[0]['v']}'")
    return out


def inventory_aging(conn, buckets=(30, 60, 90)):
    """Value and count of In-Stock inventory by age bucket (days since entering stock).
    Slow stock is tied-up capital — this shows where it's sitting."""
    edges = sorted(buckets)
    labels = [f"0\u2013{edges[0]}"] + [f"{edges[i - 1] + 1}\u2013{edges[i]}" for i in range(1, len(edges))] \
        + [f"{edges[-1] + 1}+"]
    out = [{"bucket": lb, "count": 0, "value": money(0)} for lb in labels]
    for r in conn.execute(
            "SELECT total_cost, CAST(julianday('now') - julianday(COALESCE(NULLIF("
            "date_entered_inventory,''), date('now'))) AS INTEGER) AS days "
            "FROM inventory_items WHERE status='In Stock'"):
        d = max(0, r["days"] or 0)
        idx = len(edges)
        for i, e in enumerate(edges):
            if d <= e:
                idx = i
                break
        out[idx]["count"] += 1
        out[idx]["value"] = money(out[idx]["value"] + money(r["total_cost"] or 0))
    return out
