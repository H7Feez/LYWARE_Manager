#!/usr/bin/env python3
"""LYWARE — test harness (v4). Run: python3 test_lyware.py"""

import lyware as L

_checks = []


def check(label, got, expected):
    ok = L.money(got) == L.money(expected)
    _checks.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: got {L.money(got)}, expected {L.money(expected)}")


def ceq(label, got, expected):
    ok = got == expected
    _checks.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: got {got!r}, expected {expected!r}")


def expect_raise(label, exc, fn):
    try:
        fn(); _checks.append(False); print(f"  [FAIL] {label}: nothing raised")
    except exc:
        _checks.append(True); print(f"  [PASS] {label}: raised {exc.__name__}")
    except Exception as e:  # noqa
        _checks.append(False); print(f"  [FAIL] {label}: raised {type(e).__name__}, wanted {exc.__name__}")


def main():
    conn = L.init_db()
    print("Fresh database built from schema.sql (v4)\n")

    cash = L.add_account(conn, "Cash drawer", "Cash")
    card = L.add_account(conn, "Online Card", "Card")
    main = L.add_account(conn, "Main holding", "Cash")
    L.deposit_lyd(conn, cash, 50000)
    L.recharge_card(conn, cash, card, "USD", 500, 11)        # cash -5500 -> 44500; card $500

    pA = L.record_purchase(conn, card, "ebay_x", "USD",
                           [{"name": "Chromebook #1", "unit_price": 100},
                            {"name": "Chromebook #2", "unit_price": 100}],
                           delivery_method="International", purchaser_name="hafiz")
    a1, a2 = pA["items"][0]["lywrid"], pA["items"][1]["lywrid"]
    pD = L.record_purchase(conn, cash, "fb_seller", "LYD",
                           [{"name": "Used monitor", "unit_price": 800}],
                           delivery_method="In-Person", purchaser_name="hafiz")
    d1 = pD["items"][0]["lywrid"]

    print("Purchases:")
    check("Card USD ($500-$200)", L.fx_balance(conn, card), 300)
    check("Cash LYD (50000-5500-800)", L.lyd_balance(conn, cash), 43700)
    ceq("In-person item -> Pending Approval", L.get_item_status(conn, d1), "Pending Approval")
    ceq("International item -> Awaiting Shipment", L.get_item_status(conn, a1), "Awaiting Shipment")
    print()

    # inbound international leg
    intl = L.start_international_shipment(conn, [a1, a2], tracking_number="FX-1",
                                         freight_forwarder_name="MyUS", weight_kg=2.4)
    L.pay_shipping(conn, intl, card, 20, "USD")              # $20@11 = 220 LYD; card $280
    L.mark_arrived_us_warehouse(conn, intl, "2026-06-10")
    L.mark_arrived_libya_warehouse(conn, intl, "2026-06-18")
    print("International leg:")
    check("Card USD after $20 shipping", L.fx_balance(conn, card), 280)
    ceq("A1 at Libya warehouse", L.get_item_status(conn, a1), "At Libya Warehouse")
    print()

    # the whole international group moves together: local leg (paid at start), then to approval
    loc = L.start_local_shipment(conn, [a1], shipping_office_name="Al Bayda Express",
                                 date_shipped="2026-06-19", cost=40, paying_acctid=cash,
                                 currency="LYD")               # cash -40 -> 43660
    ceq("A2 moved local with the group", L.get_item_status(conn, a2), "Local Transit")
    L.mark_arrived_local_office(conn, loc, "2026-06-20")
    L.receive_at_shop(conn, a1, "2026-06-21")                  # promotes the whole local group
    print("Branch -> approval queue:")
    ceq("A1 Pending Approval", L.get_item_status(conn, a1), "Pending Approval")
    ceq("A2 Pending Approval (group)", L.get_item_status(conn, a2), "Pending Approval")
    print()

    # accept into inventory (freezes cost here) — local 40 shared across the 2-item group = 20 each
    tA1 = L.accept_into_inventory(conn, a1, "2026-06-21")
    tA2 = L.accept_into_inventory(conn, a2, "2026-06-19")
    tD1 = L.accept_into_inventory(conn, d1, "2026-06-15")
    print("Accept into inventory (cost frozen):")
    check("A1 total cost (1100 + 110 intl + 20 local)", tA1, 1230)
    check("A2 total cost (1100 + 110 intl + 20 local)", tA2, 1230)
    check("D1 total cost (800, no shipping)", tD1, 800)
    ceq("A1 In Stock", L.get_item_status(conn, a1), "In Stock")
    expect_raise("Can't accept an already-accepted item", L.StateError,
                 lambda: L.accept_into_inventory(conn, a1, "2026-06-21"))
    print()

    # multi-item sale order WITH shipping (A1 + A2 together)
    o1 = L.commit_sale_order(conn, [{"lywrid": a1, "price": 2000}, {"lywrid": a2, "price": 1800}],
                             buyer_name="Mr X", requires_shipping=True)
    ceq("A1 Sold Pending", L.get_item_status(conn, a1), "Sold Pending")
    L.ship_order_to_customer(conn, o1, "Tobruk Post", shipping_cost=50, currency="LYD",
                             date_shipped="2026-06-23", paying_acctid=cash)   # cash -50 -> 43610
    expect_raise("Can't finalize before delivery", L.StateError,
                 lambda: L.finalize_sale_order(conn, o1, main, "2026-06-25"))
    L.mark_order_arrived_customer(conn, o1, "2026-06-25")
    L.finalize_sale_order(conn, o1, main, "2026-06-25")       # main +3800
    print("Multi-item sale order (A1+A2, shipped):")
    ceq("A1 Sold", L.get_item_status(conn, a1), "Sold")
    ceq("A2 Sold", L.get_item_status(conn, a2), "Sold")
    check("Order 1 profit (3800 - 2460 - 50)", L.order_profit(conn, o1), 1290)
    print()

    # in-person sale order, no shipping
    o2 = L.commit_sale_order(conn, [{"lywrid": d1, "price": 1200}], buyer_name="Walk-in")
    L.finalize_sale_order(conn, o2, main, "2026-06-26")        # main +1200
    print("In-person sale order (no shipping):")
    ceq("D1 Sold", L.get_item_status(conn, d1), "Sold")
    check("Order 2 profit (1200 - 800)", L.order_profit(conn, o2), 400)
    print()

    # business expenses
    L.record_business_expense(conn, cash, 100, "LYD", "Rent", "shop rent")     # cash -100 -> 43510
    L.record_business_expense(conn, card, 10, "USD", "Software", "VPN")        # card $280-10 -> 270
    print("Business expenses:")
    check("Cash LYD after rent", L.lyd_balance(conn, cash), 43510)
    check("Card USD after software", L.fx_balance(conn, card), 270)
    expect_raise("Cash business expense can't be USD", ValueError,
                 lambda: L.record_business_expense(conn, cash, 5, "USD"))
    print()

    # money sanity + reporting roll-ups
    print("Money & reporting:")
    check("Cash LYD final", L.lyd_balance(conn, cash), 43510)
    check("Main LYD (3800 + 1200)", L.lyd_balance(conn, main), 5000)
    check("Total expenses in LYD (800+40+50+100)", L.category_total(conn, "Expense"), -990)
    check("Total revenue in LYD (3800+1200)", L.category_total(conn, "Revenue"), 5000)
    check("Capital in (50000)", L.category_total(conn, "Capital"), 50000)
    print()

    # account hiding
    print("Account hiding:")
    extra = L.add_account(conn, "Old card", "Card")
    ceq("Account visible before hide", any(a["acctid"] == extra for a in L.list_accounts(conn)), True)
    L.hide_account(conn, extra)
    ceq("Account gone after hide", any(a["acctid"] == extra for a in L.list_accounts(conn)), False)
    ceq("Hidden account shown with include_hidden",
        any(a["acctid"] == extra for a in L.list_accounts(conn, include_hidden=True)), True)
    L.unhide_account(conn, extra)
    ceq("Account back after unhide", any(a["acctid"] == extra for a in L.list_accounts(conn)), True)
    print()

    # ---- catalog / repository (v5) ----------------------------------------
    print("Catalog / repository:")
    cb4 = L.add_catalog_item(conn, "Laptop", "HP Chromebook x360 11 G3", manufacturer="HP",
                             model_name="x360 11 G3 EE",
                             attributes=[("RAM", "4GB"), ("Storage", "32GB eMMC"),
                                         ("RAM Type", "DDR4")])
    cb8 = L.add_catalog_item(conn, "Laptop", "HP Chromebook x360 11 G3", manufacturer="HP",
                             model_name="x360 11 G3 EE",
                             attributes=[("RAM", "8GB"), ("Storage", "32GB eMMC"),
                                         ("RAM Type", "DDR4")])
    ssd = L.add_catalog_item(conn, "Storage", "Kingston 1TB NVMe SSD", manufacturer="Kingston",
                             attributes=[("Capacity", "1TB"), ("Interface", "M.2 NVMe Gen4x4")])
    ceq("4GB and 8GB variants are distinct entries", cb4 != cb8, True)
    ceq("Catalog has 3 items", len(L.list_catalog_items(conn)), 3)

    # duplicate: identical core + attributes (order-independent) must be rejected
    expect_raise("Exact duplicate rejected", L.DuplicateCatalogItem,
                 lambda: L.add_catalog_item(conn, "Laptop", "HP Chromebook x360 11 G3",
                                            manufacturer="HP", model_name="x360 11 G3 EE",
                                            attributes=[("Storage", "32GB eMMC"), ("RAM Type", "DDR4"),
                                                        ("RAM", "4GB")]))
    # differs only by one attribute value -> allowed
    cb4b = L.add_catalog_item(conn, "Laptop", "HP Chromebook x360 11 G3", manufacturer="HP",
                              model_name="x360 11 G3 EE",
                              attributes=[("RAM", "4GB"), ("Storage", "64GB eMMC"), ("RAM Type", "DDR4")])
    ceq("Different storage -> new entry", cb4b not in (cb4, cb8), True)

    # required-field validation
    expect_raise("Missing category rejected", ValueError,
                 lambda: L.add_catalog_item(conn, "", "Something"))
    expect_raise("Missing display name rejected", ValueError,
                 lambda: L.add_catalog_item(conn, "Laptop", ""))

    # vocabularies auto-registered from use
    ceq("Category vocab grew", set(["Laptop", "Storage"]).issubset(set(L.list_categories(conn))), True)
    ceq("Manufacturer vocab grew", "Kingston" in L.list_manufacturers(conn), True)
    ceq("Attribute-name vocab grew", "Capacity" in L.list_attribute_names(conn), True)

    # read-back + attributes preserved in order
    got = L.get_catalog_item(conn, cb4)
    ceq("Read-back display name", got["item"]["display_name"], "HP Chromebook x360 11 G3")
    ceq("Read-back attribute count", len(got["attributes"]), 3)

    # scoped value autocomplete
    ceq("RAM value suggestions", sorted(L.attribute_value_suggestions(conn, "RAM")), ["4GB", "8GB"])

    # search
    ceq("Search by attribute value finds NVMe", any(r["catid"] == ssd for r in L.search_catalog(conn, "nvme")), True)
    ceq("Search by category=Laptop excludes SSD",
        all(r["category"] == "Laptop" for r in L.search_catalog(conn, category="Laptop")), True)

    # update changes signature; cannot collide with another item
    L.update_catalog_item(conn, cb4b, "Laptop", "HP Chromebook x360 11 G3", manufacturer="HP",
                          model_name="x360 11 G3 EE",
                          attributes=[("RAM", "4GB"), ("Storage", "128GB eMMC"), ("RAM Type", "DDR4")])
    ceq("Update applied", L.get_catalog_item(conn, cb4b)["attributes"][1], ("Storage", "128GB eMMC"))
    expect_raise("Update into a duplicate rejected", L.DuplicateCatalogItem,
                 lambda: L.update_catalog_item(conn, cb4b, "Laptop", "HP Chromebook x360 11 G3",
                                               manufacturer="HP", model_name="x360 11 G3 EE",
                                               attributes=[("RAM", "4GB"), ("Storage", "32GB eMMC"),
                                                           ("RAM Type", "DDR4")]))

    # listing composition: one row per product, quantity holds the count; bundles allowed
    ls = L.add_listing(conn, "eBay", price=110, currency="USD", seller_name="techseller")
    L.add_listing_items(conn, ls, [(cb4, 10), (ssd, 1)])   # 10 identical CBs + 1 SSD bundle
    lines = L.get_listing_items(conn, ls)
    ceq("Listing has 2 product lines", len(lines), 2)
    ceq("Identical units held as quantity, not repeated rows",
        next(x["quantity"] for x in lines if x["catid"] == cb4), 10)

    # phase 3: catalog-linked purchase stamps catid onto the inventory unit; name from catalog
    pcat = L.record_purchase(conn, cash, "ebay_cat", "LYD",
                             [{"catid": ssd, "unit_price": 600}],
                             delivery_method="In-Person", purchaser_name="hafiz")
    lyw_cat = pcat["items"][0]["lywrid"]
    row = conn.execute("SELECT catid FROM inventory_items WHERE lywrid=?", (lyw_cat,)).fetchone()
    ceq("Inventory unit carries catid", row["catid"], ssd)
    ceq("Purchase name pulled from catalog", pcat["items"][0]["name"], "Kingston 1TB NVMe SSD")
    det = L.item_detail(conn, ssd)
    ceq("item_detail exposes category", det["Category"], "Storage")
    ceq("item_detail exposes attribute", det.get("Capacity"), "1TB")
    ceq("used_attribute_names includes Capacity", "Capacity" in L.used_attribute_names(conn), True)

    # ---- v6 / checkpoint 1: shipping groups, costs, listings, sales --------
    print("v6 shipping groups, cost breakdown, listings, sales:")
    cashA = L.add_account(conn, "ShipCash", "Cash"); L.deposit_lyd(conn, cashA, 100000)
    cardA = L.add_account(conn, "ShipCard", "Card"); L.recharge_card(conn, cashA, cardA, "USD", 1000, 11)
    # M9: international purchase with shipping cost paid immediately at purchase
    bal_before = L.fx_balance(conn, cardA, "USD")
    pp = L.record_purchase(conn, cardA, "ebay", "USD",
                           [{"catid": cb4, "unit_price": 100}] * 3,
                           delivery_method="International", purchaser_name="hafiz",
                           shipping_cost=30, shipping_acct=cardA, shipping_currency="USD")
    ceq("Purchase created a grouped shipment", pp["shipid"] is not None, True)
    ceq("M9 shipping charged immediately (USD spent = 300+30)",
        L.fx_balance(conn, cardA, "USD"), L.money(bal_before - 330))
    units = [it["lywrid"] for it in pp["items"]]
    grp = L.shop_shipment_groups(conn)
    ceq("One inbound shipment group of 3", next(g["count"] for g in grp if g["shipid"] == pp["shipid"]), 3)

    # M5: split the group (1 item into a new shipment) while pre-transit
    new_ship = L.split_shipment(conn, pp["shipid"], [units[2]])
    ceq("Split made a second shipment", new_ship != pp["shipid"], True)
    ceq("Original shipment now has 2", len(L.shipment_member_items(conn, pp["shipid"])), 2)
    ceq("New shipment has 1", len(L.shipment_member_items(conn, new_ship)), 1)
    # the two groups progress independently
    L.start_international_shipment(conn, pp["shipid"], tracking_number="TA")
    ceq("Group A in transit, group B still awaiting",
        (L.get_item_status(conn, units[0]), L.get_item_status(conn, units[2])),
        ("International Transit", "Awaiting Shipment"))

    # cost breakdown: intl shipping apportioned across the (now 2-item) shipment
    L.mark_arrived_us_warehouse(conn, pp["shipid"], "2026-06-10")
    L.mark_arrived_libya_warehouse(conn, pp["shipid"], "2026-06-18")
    L.pickup_to_shop(conn, units[0], "2026-06-19")
    bd = L.item_cost_breakdown(conn, units[0])
    # shipment cost 30 USD * 11 = 330 LYD; per-item share 110 is PRESERVED through the split
    ceq("Split preserves per-item intl share", bd["intl_shipping"], L.money(110))
    ceq("Breakdown item cost = basis", bd["item_cost"], L.money(1100))

    # M7: cost adjustment applied at approval, folded into total + breakdown
    tot = L.accept_into_inventory(conn, units[0], "2026-06-20", cost_adjustment=50,
                                  cost_adjustment_note="cleaning")
    ceq("Total cost includes basis+intl+adjustment", tot, L.money(1100 + 110 + 50))
    bd2 = L.item_cost_breakdown(conn, units[0])
    ceq("Breakdown additional reflects adjustment", bd2["additional"], L.money(50))
    ceq("Breakdown total matches frozen total", bd2["total"], bd2["frozen_total"])

    # M1: per-item listing price + listing total + value breakdown
    lp = L.add_listing(conn, "eBay", currency="USD", seller_name="s", phone_number="0910000000")
    L.add_listing_items(conn, lp, [(cb4, 2, 120), (ssd, 1, 60)])
    ceq("Listing total = sum(unit*qty)", L.listing_total(conn, lp), L.money(2 * 120 + 60))
    vb = L.listing_value_breakdown(conn, lp)
    ceq("Listing breakdown line total", next(x["line_total"] for x in vb if x["quantity"] == 2), L.money(240))
    ceq("BUG4 phone stored on listing",
        conn.execute("SELECT phone_number FROM all_listings WHERE lsid=?", (lp,)).fetchone()["phone_number"],
        "0910000000")

    # M2/M3: purchase can reference a listing
    pl2 = L.record_purchase(conn, cashA, "ebay", "LYD", [{"catid": cb4, "unit_price": 1000}],
                            lsid=lp, delivery_method="In-Person")
    ceq("Purchase stores its source listing",
        conn.execute("SELECT lsid FROM purchase_orders WHERE poid=?",
                     (pl2["poid"],)).fetchone()["lsid"], lp)

    # M13 + M6: buyer phone on sale; finalized order exposes its atomized items
    L.accept_into_inventory(conn, pl2["items"][0]["lywrid"], "2026-06-21")
    so = L.commit_sale_order(conn, [{"lywrid": pl2["items"][0]["lywrid"], "price": 2500}],
                             buyer_name="Mr X", buyer_phone="0925550000")
    ceq("M13 buyer phone stored",
        conn.execute("SELECT buyer_phone FROM sales_orders WHERE sale_order_id=?",
                     (so,)).fetchone()["buyer_phone"], "0925550000")
    main2 = L.add_account(conn, "Recv", "Cash")
    L.finalize_sale_order(conn, so, main2, "2026-06-22")
    ceq("M6 order_items_detail returns atomized units", len(L.order_items_detail(conn, so)), 1)

    # delete guard: in-use item can't be deleted; unused can
    expect_raise("In-use catalog item delete blocked", L.StateError,
                 lambda: L.delete_catalog_item(conn, cb4))
    free = L.add_catalog_item(conn, "Accessory", "Spare USB-C cable")
    L.delete_catalog_item(conn, free)
    ceq("Unused catalog item deleted", L.get_catalog_item(conn, free), None)
    expect_raise("Vocab in use can't be removed", L.StateError,
                 lambda: L.delete_vocab(conn, "category", "Laptop"))

    # persistent UI prefs round-trip
    L.set_pref(conn, "cols.inventory", "id,display,ram,storage")
    ceq("Pref round-trips", L.get_pref(conn, "cols.inventory"), "id,display,ram,storage")
    L.set_pref(conn, "cols.inventory", "id,display")
    ceq("Pref overwrites", L.get_pref(conn, "cols.inventory"), "id,display")
    print()

    # change log populated
    n_log = conn.execute("SELECT COUNT(*) AS n FROM change_log").fetchone()["n"]
    print("Change log:")
    ceq("Change log has entries", n_log > 0, True)
    print()

    _shipping_group_regressions()
    _error_prevention_regressions()
    _exception_event_regressions()
    _polish_regressions()
    _reversal_regressions()
    _qol_feature_regressions()
    _cost_adjustment_money_regressions()
    _variant_market_regressions()
    _upgrade_v10_regressions()
    _market_rate_regressions()

    total, passed = len(_checks), sum(_checks)
    print("=" * 56)
    print(f"  {passed}/{total} checks passed"
          + ("  — all green." if passed == total else "  — SOMETHING FAILED."))
    print("=" * 56)
    conn.close()


def _shipping_group_regressions():
    """Regression tests for the shipping-group bug batch (split cost, group promotion,
    group local transit, intl+local cost, paid-at-start local leg)."""
    print("Shipping group regressions:")
    import os
    p = "/tmp/lyware_ship_regression.db"
    if os.path.exists(p):
        os.remove(p)
    conn = L.open_or_create_db(p)
    cb = L.add_catalog_item(conn, "Laptop", "HP", "HP", "x", [("RAM", "4GB")])
    cash = L.add_account(conn, "Cash", "Cash")
    card = L.add_account(conn, "Card", "Card")
    L.deposit_lyd(conn, cash, 1_000_000)
    L.recharge_card(conn, cash, card, "USD", 5000, 1)        # rate 1 -> clean LYD math

    # --- BUG 3 & 4: split apportions cost; per-item share preserved -------------
    pp = L.record_purchase(conn, card, "v", "USD", [{"catid": cb, "unit_price": 25}] * 4,
                           delivery_method="International", shipping_cost=10,
                           shipping_acct=card, shipping_currency="USD")
    u = [it["lywrid"] for it in pp["items"]]
    ns = L.split_shipment(conn, pp["shipid"], u[:2])
    check("Split: original keeps half the cost", conn.execute(
        "SELECT lyd_shipping_cost FROM shipments WHERE shipid=?", (pp["shipid"],)).fetchone()[0], 5)
    check("Split: new shipment gets half the cost", conn.execute(
        "SELECT lyd_shipping_cost FROM shipments WHERE shipid=?", (ns,)).fetchone()[0], 5)
    for lid in u:
        check(f"Split preserves item {lid} share at 2.5",
              L.item_cost_breakdown(conn, lid)["intl_shipping"], L.money("2.5"))

    # --- BUG 1: promotion to approval moves the whole group ----------------------
    pp2 = L.record_purchase(conn, card, "v", "USD", [{"catid": cb, "unit_price": 25}] * 3,
                            delivery_method="International", shipping_cost=9,
                            shipping_acct=card, shipping_currency="USD")
    g = [it["lywrid"] for it in pp2["items"]]
    L.start_international_shipment(conn, pp2["shipid"], tracking_number="T")
    L.mark_arrived_us_warehouse(conn, pp2["shipid"], "2026-01-01")
    L.mark_arrived_libya_warehouse(conn, pp2["shipid"], "2026-01-02")
    L.pickup_to_shop(conn, g[0], "2026-01-03")
    ceq("Group promotion: all 3 -> Pending Approval",
        [L.get_item_status(conn, x) for x in g],
        ["Pending Approval", "Pending Approval", "Pending Approval"])

    # --- BUG 2 & 5: intl group -> local moves together; intl+local both counted --
    pp3 = L.record_purchase(conn, card, "v", "USD", [{"catid": cb, "unit_price": 50}] * 2,
                            delivery_method="International", shipping_cost=50,
                            shipping_acct=card, shipping_currency="USD")  # 50 LYD intl / 2 = 25 each
    h = [it["lywrid"] for it in pp3["items"]]
    L.start_international_shipment(conn, pp3["shipid"], tracking_number="T")
    L.mark_arrived_us_warehouse(conn, pp3["shipid"], "2026-01-01")
    L.mark_arrived_libya_warehouse(conn, pp3["shipid"], "2026-01-02")
    ls = L.start_local_shipment(conn, [h[0]], shipping_office_name="off", date_shipped="2026-01-03",
                                cost=40, paying_acctid=cash, currency="LYD")    # 40 / 2 = 20 each
    ceq("Local transit moves the whole group",
        [L.get_item_status(conn, x) for x in h], ["Local Transit", "Local Transit"])
    L.mark_arrived_local_office(conn, ls, "2026-01-04")
    L.receive_at_shop(conn, h[0], "2026-01-05")
    tot = L.accept_into_inventory(conn, h[0], "2026-01-06")
    bd = L.item_cost_breakdown(conn, h[0])
    check("Intl+local both counted: intl share (50/2)", bd["intl_shipping"], 25)
    check("Intl+local both counted: local share (40/2)", bd["local_shipping"], 20)
    check("Frozen total = basis 50 + intl 25 + local 20", tot, 95)

    # --- BUG 5 single item: local cost fully applies (was being skipped) ---------
    pp4 = L.record_purchase(conn, card, "v", "USD", [{"catid": cb, "unit_price": 50}],
                            delivery_method="International", shipping_cost=50,
                            shipping_acct=card, shipping_currency="USD")
    s = pp4["items"][0]["lywrid"]
    L.start_international_shipment(conn, pp4["shipid"], tracking_number="T")
    L.mark_arrived_us_warehouse(conn, pp4["shipid"], "2026-01-01")
    L.mark_arrived_libya_warehouse(conn, pp4["shipid"], "2026-01-02")
    L.start_local_shipment(conn, [s], shipping_office_name="off", date_shipped="2026-01-03",
                           cost=50, paying_acctid=cash, currency="LYD")
    L.mark_arrived_local_office(conn, L._shipment_peers(conn, s, "Local", "Local Transit")[1], "2026-01-04")
    L.receive_at_shop(conn, s, "2026-01-05")
    check("Single intl->local item = 50 + 50 + 50 = 150",
          L.accept_into_inventory(conn, s, "2026-01-06"), 150)

    # --- conservation: split never creates or destroys total shipping cost ------
    total_intl = sum(float(L.item_cost_breakdown(conn, x)["intl_shipping"]) for x in u)
    check("Conservation: 4-item split still totals 10 LYD intl", total_intl, 10)
    conn.close()
    print()


def _error_prevention_regressions():
    """Phase 1-2: edits propagate, deletes are gated, shipping adjusts, reverse works, backups."""
    print("User-error prevention regressions:")
    import os
    p = "/tmp/lyware_errprev_regression.db"
    if os.path.exists(p):
        os.remove(p)
    conn = L.open_or_create_db(p)
    cb = L.add_catalog_item(conn, "Laptop", "HP x360", "HP", "x360", [("RAM", "4GB")])
    unused = L.add_catalog_item(conn, "Mouse", "Logi", "Logitech", None, [])
    cash = L.add_account(conn, "Cash", "Cash")
    card = L.add_account(conn, "Card", "Card")
    L.deposit_lyd(conn, cash, 1_000_000)
    L.recharge_card(conn, cash, card, "USD", 5000, 1)
    ls = L.add_listing(conn, "eBay", currency="USD", seller_name="s")
    L.add_listing_items(conn, ls, [(cb, 2, 100)])
    pp = L.record_purchase(conn, card, "v", "USD", [{"catid": cb, "unit_price": 100}] * 2, lsid=ls,
                           delivery_method="International", shipping_cost=20, shipping_acct=card,
                           shipping_currency="USD")
    u = [it["lywrid"] for it in pp["items"]]

    # edit catalogue -> name re-syncs to the denormalized purchase_lines snapshot
    L.update_catalog_item(conn, cb, "Laptop", "HP x360 G3", "HP", "x360", [("RAM", "4GB")])
    nm = conn.execute("SELECT item_name FROM purchase_lines WHERE catid=?", (cb,)).fetchone()["item_name"]
    ceq("Catalogue edit re-syncs purchase line name", nm, "HP x360 G3")

    # delete gating + hide fallback
    expect_raise("Delete in-use catalogue item blocked", L.StateError,
                 lambda: L.delete_catalog_item(conn, cb))
    L.delete_catalog_item(conn, unused)
    ceq("Unused catalogue item deletes", conn.execute(
        "SELECT COUNT(*) AS n FROM catalog_items WHERE catid=?", (unused,)).fetchone()["n"], 0)
    L.hide_catalog_item(conn, cb)
    ceq("Hidden item excluded from pickers", any(r["catid"] == cb for r in L.search_catalog(conn)), False)
    ceq("Hidden item still visible with include_hidden", any(
        r["catid"] == cb for r in L.search_catalog(conn, include_hidden=True)), True)

    # listing edit syncs subtype; delete blocked while a purchase references it
    L.edit_listing(conn, ls, price=120, seller_name="s2")
    sub = conn.execute("SELECT price, seller_name FROM ebay_listings WHERE lsid=?", (ls,)).fetchone()
    check("Listing edit syncs subtype price", sub["price"], 120)
    expect_raise("Delete referenced listing blocked", L.StateError, lambda: L.delete_listing(conn, ls))

    # adjust shipping cost: correct 220 -> 200, refund 20, re-apportion to 100/item
    L.adjust_shipping_cost(conn, pp["shipid"], 200, cash)
    check("Shipping cost corrected", conn.execute(
        "SELECT lyd_shipping_cost FROM shipments WHERE shipid=?", (pp["shipid"],)).fetchone()[0], 200)
    check("Adjusted shipping re-apportions per item",
          L.item_cost_breakdown(conn, u[0])["intl_shipping"], 100)

    # reverse last step: start intl then undo -> Awaiting Shipment
    L.start_international_shipment(conn, pp["shipid"], tracking_number="T")
    L.reverse_last_status(conn, u[0])
    ceq("Reverse undoes intl start", L.get_item_status(conn, u[0]), "Awaiting Shipment")

    # reverse accept unfreezes cost
    L.start_international_shipment(conn, pp["shipid"], tracking_number="T")
    L.mark_arrived_us_warehouse(conn, pp["shipid"], "2026-01-01")
    L.mark_arrived_libya_warehouse(conn, pp["shipid"], "2026-01-02")
    L.pickup_to_shop(conn, u[0], "2026-01-03")
    L.accept_into_inventory(conn, u[0], "2026-01-04")
    L.reverse_last_status(conn, u[0])
    ceq("Reverse accept -> Pending Approval", L.get_item_status(conn, u[0]), "Pending Approval")
    ceq("Reverse accept unfreezes cost", conn.execute(
        "SELECT total_cost FROM inventory_items WHERE lywrid=?", (u[0],)).fetchone()[0], None)

    # account edit + delete gating
    expect_raise("Delete account with activity blocked", L.StateError,
                 lambda: L.delete_account(conn, card))
    fresh = L.add_account(conn, "Temp", "Cash")
    L.delete_account(conn, fresh)
    ceq("Unused account deletes", conn.execute(
        "SELECT COUNT(*) AS n FROM accounts WHERE acctid=?", (fresh,)).fetchone()["n"], 0)

    # backups
    b = L.make_backup(p, "test")
    ceq("Backup created", bool(b) and os.path.exists(b), True)
    ceq("Backup listed", len(L.list_backups(p)) >= 1, True)
    conn.close()
    print()


def _exception_event_regressions():
    """Phase 3-4: cancellation, write-off, returns, void, and the losses report."""
    print("Exception-event regressions:")
    import os
    p = "/tmp/lyware_exception_regression.db"
    if os.path.exists(p):
        os.remove(p)
    conn = L.open_or_create_db(p)
    cb = L.add_catalog_item(conn, "Laptop", "HP", "HP", "x", [("RAM", "4GB")])
    cash = L.add_account(conn, "Cash", "Cash")
    card = L.add_account(conn, "Card", "Card")
    main = L.add_account(conn, "Main", "Cash")
    L.deposit_lyd(conn, cash, 1_000_000)
    L.deposit_lyd(conn, main, 200_000)
    L.recharge_card(conn, cash, card, "USD", 5000, 1)

    def buy(n=1, method="In-Person"):
        pp = L.record_purchase(conn, card, "v", "USD", [{"catid": cb, "unit_price": 100}] * n,
                               delivery_method=method)
        return [it["lywrid"] for it in pp["items"]], pp["shipid"]

    # cancel leaves siblings untouched
    u, sh = buy(2, "International")
    L.start_international_shipment(conn, sh, tracking_number="T")
    L.cancel_item(conn, u[0], "2026-06-25", refund_amount=100, refund_currency="LYD", refund_acctid=cash)
    ceq("Cancel sets unit Cancelled", L.get_item_status(conn, u[0]), "Cancelled")
    ceq("Cancel leaves sibling in transit", L.get_item_status(conn, u[1]), "International Transit")

    # write off from stock with extra expense
    u2, _ = buy(1)
    L.accept_into_inventory(conn, u2[0], "2026-06-20")
    bal = L.lyd_balance(conn, cash)
    L.write_off_item(conn, u2[0], "2026-06-25", extra_expense=15, expense_currency="LYD", expense_acctid=cash)
    ceq("Write off sets Written Off", L.get_item_status(conn, u2[0]), "Written Off")
    check("Write off extra expense charged", bal - L.lyd_balance(conn, cash), 15)

    # return to seller
    u3, _ = buy(1)
    L.return_to_seller(conn, u3[0], "2026-06-25", refund_amount=100, refund_acctid=cash)
    ceq("Return to seller status", L.get_item_status(conn, u3[0]), "Returned to Seller")

    # customer return: restock vs close; refund reduces revenue
    u4, _ = buy(2)
    for x in u4:
        L.accept_into_inventory(conn, x, "2026-06-20")
    o = L.commit_sale_order(conn, [{"lywrid": u4[0], "price": 2500}, {"lywrid": u4[1], "price": 2500}],
                            buyer_name="B", requires_shipping=False)
    L.finalize_sale_order(conn, o, main, "2026-06-22")
    rev0 = L.financial_summary(conn)["revenue"]
    L.customer_return(conn, u4[0], "2026-06-25", refund_amount=2500, refund_acctid=main, restock=True)
    L.customer_return(conn, u4[1], "2026-06-25", refund_amount=2400, refund_acctid=main, restock=False)
    ceq("Customer return restock -> In Stock", L.get_item_status(conn, u4[0]), "In Stock")
    ceq("Customer return close -> Customer Returned", L.get_item_status(conn, u4[1]), "Customer Returned")
    check("Customer refunds reduce revenue", rev0 - L.financial_summary(conn)["revenue"], 4900)

    # void pre-finalize order
    u5, _ = buy(1)
    L.accept_into_inventory(conn, u5[0], "2026-06-20")
    o2 = L.commit_sale_order(conn, [{"lywrid": u5[0], "price": 2000}], buyer_name="X")
    L.void_sale_order(conn, o2)
    ceq("Void returns unit to stock", L.get_item_status(conn, u5[0]), "In Stock")
    ceq("Void removes order", conn.execute(
        "SELECT COUNT(*) AS n FROM sales_orders WHERE sale_order_id=?", (o2,)).fetchone()["n"], 0)

    # losses report covers the four terminal outcomes
    ls = L.losses_summary(conn)
    ceq("Losses summary counts 4 closed units", ls["count"], 4)
    ceq("Losses has all four outcomes", sorted(ls["by_status"].keys()),
        ["Cancelled", "Customer Returned", "Returned to Seller", "Written Off"])
    conn.close()
    print()


def _polish_regressions():
    """Polish stage: refund labeling, signed cost adjustments, contra-sign integrity."""
    print("Polish regressions:")
    import os
    p = "/tmp/lyware_polish_regression.db"
    if os.path.exists(p):
        os.remove(p)
    conn = L.open_or_create_db(p)
    cb = L.add_catalog_item(conn, "Laptop", "HP", "HP", "x", [("RAM", "4GB")])
    cash = L.add_account(conn, "Cash", "Cash")
    card = L.add_account(conn, "Card", "Card")
    main = L.add_account(conn, "Main", "Cash")
    L.deposit_lyd(conn, cash, 5_000_000)
    L.deposit_lyd(conn, main, 1_000_000)
    L.recharge_card(conn, cash, card, "USD", 10000, 11)

    def cat(tp):
        return conn.execute("SELECT category FROM transaction_types WHERE type=?", (tp,)).fetchone()["category"]
    ceq("Refund_Received type exists (Expense)", cat("Refund_Received"), "Expense")
    ceq("Refund_Issued type exists (Revenue)", cat("Refund_Issued"), "Revenue")

    # seller refund -> Refund_Received, positive (money in). USD refund posts in USD.
    pp = L.record_purchase(conn, card, "v", "USD", [{"catid": cb, "unit_price": 100}],
                           delivery_method="In-Person")
    u = pp["items"][0]["lywrid"]
    L.return_to_seller(conn, u, "2026-06-25", refund_amount=80, refund_currency="USD",
                       refund_acctid=card, refund_rate=11)
    r = conn.execute("SELECT type, amount, currency FROM all_transactions ORDER BY trnsid DESC LIMIT 1").fetchone()
    ceq("Seller refund typed Refund_Received", r["type"], "Refund_Received")
    check("USD seller refund posts in USD (money in)", r["amount"], 80)
    ceq("USD seller refund currency USD", r["currency"], "USD")
    ceq("USD seller refund credits the card", L.fx_balance(conn, card, "USD") > 0, True)

    # a LYD seller refund DOES lower the LYD net expense (contra against purchase)
    u1b = L.record_purchase(conn, cash, "v", "LYD", [{"catid": cb, "unit_price": 500}],
                            delivery_method="In-Person")["items"][0]["lywrid"]
    exp0 = L.financial_summary(conn)["expense"]
    L.return_to_seller(conn, u1b, "2026-06-25", refund_amount=300, refund_currency="LYD", refund_acctid=cash)
    check("LYD seller refund lowers net expense", exp0 - L.financial_summary(conn)["expense"], 300)

    # customer refund -> Refund_Issued, negative (money out), reduces revenue
    u2 = L.record_purchase(conn, cash, "v", "LYD", [{"catid": cb, "unit_price": 1000}],
                           delivery_method="In-Person")["items"][0]["lywrid"]
    L.accept_into_inventory(conn, u2, "2026-06-20")
    o = L.commit_sale_order(conn, [{"lywrid": u2, "price": 2500}], buyer_name="B")
    L.finalize_sale_order(conn, o, main, "2026-06-22")
    rev0 = L.financial_summary(conn)["revenue"]
    L.customer_return(conn, u2, "2026-06-25", refund_amount=2500, refund_acctid=main, restock=False)
    r2 = conn.execute("SELECT type, amount FROM all_transactions ORDER BY trnsid DESC LIMIT 1").fetchone()
    ceq("Customer refund typed Refund_Issued", r2["type"], "Refund_Issued")
    check("Customer refund posts negative (money out)", r2["amount"], -2500)
    check("Customer refund lowers revenue", rev0 - L.financial_summary(conn)["revenue"], 2500)

    # negative cost adjustment allowed; over-large negative blocked
    u3 = L.record_purchase(conn, cash, "v", "LYD", [{"catid": cb, "unit_price": 1000}],
                           delivery_method="In-Person")["items"][0]["lywrid"]
    tot = L.accept_into_inventory(conn, u3, "2026-06-20", cost_adjustment=-200, cost_adjustment_note="discount")
    check("Negative cost adjustment lowers total", tot, 800)
    u4 = L.record_purchase(conn, cash, "v", "LYD", [{"catid": cb, "unit_price": 100}],
                           delivery_method="In-Person")["items"][0]["lywrid"]
    expect_raise("Negative total cost blocked", ValueError,
                 lambda: L.accept_into_inventory(conn, u4, "2026-06-20", cost_adjustment=-500))

    # restocked unit resells (two sale rows, second one finalizes)
    u5 = L.record_purchase(conn, cash, "v", "LYD", [{"catid": cb, "unit_price": 1000}],
                           delivery_method="In-Person")["items"][0]["lywrid"]
    L.accept_into_inventory(conn, u5, "2026-06-20")
    oa = L.commit_sale_order(conn, [{"lywrid": u5, "price": 2000}], buyer_name="X")
    L.finalize_sale_order(conn, oa, main, "2026-06-22")
    L.customer_return(conn, u5, "2026-06-25", refund_amount=2000, refund_acctid=main, restock=True)
    ob = L.commit_sale_order(conn, [{"lywrid": u5, "price": 1900}], buyer_name="Y")
    L.finalize_sale_order(conn, ob, main, "2026-06-26")
    ceq("Restocked unit resold -> Sold", L.get_item_status(conn, u5), "Sold")
    ceq("Resold unit has two sale rows", conn.execute(
        "SELECT COUNT(*) AS n FROM sales WHERE lywrid=?", (u5,)).fetchone()["n"], 2)
    conn.close()
    print()


def _reversal_regressions():
    """Transaction reversal & edit, plus LYD-paid recharge."""
    print("Reversal & edit regressions:")
    import os
    p = "/tmp/lyware_reversal_regression.db"
    if os.path.exists(p):
        os.remove(p)
    conn = L.open_or_create_db(p)
    cash = L.add_account(conn, "Cash", "Cash")
    card = L.add_account(conn, "Card", "Card")
    card2 = L.add_account(conn, "WrongCard", "Card")
    main = L.add_account(conn, "Main", "Cash")
    cb = L.add_catalog_item(conn, "Laptop", "HP", "HP", "x", [])
    L.deposit_lyd(conn, cash, 200_000)
    L.deposit_lyd(conn, main, 50_000)

    # recharge with lyd_paid -> exact rate + exact funding debit
    r = L.recharge_card(conn, cash, card, "USD", 100, lyd_paid=1105)
    b = conn.execute("SELECT rate FROM fx_batches WHERE trnsid=?", (r,)).fetchone()
    check("LYD-paid recharge derives exact rate", b["rate"], "11.05")
    t = conn.execute("SELECT amount FROM all_transactions WHERE trnsid=?", (r,)).fetchone()
    check("LYD-paid recharge debits exactly what was paid", L.money(t["amount"]) * -1, 1105)

    # wrong-card recharge reversed cleanly (the reported bug)
    wr = L.recharge_card(conn, cash, card2, "USD", 100, 11)
    before = L.lyd_balance(conn, cash)
    L.reverse_transaction(conn, wr)
    check("Reversed recharge clears the card's USD", L.fx_balance(conn, card2, "USD"), 0)
    check("Reversed recharge refunds the funder", L.lyd_balance(conn, cash) - before, 1100)
    ceq("Reversed recharge removes the transaction", conn.execute(
        "SELECT COUNT(*) AS n FROM all_transactions WHERE trnsid=?", (wr,)).fetchone()["n"], 0)

    # spent recharge cannot be reversed (clean card so FIFO consumes THIS batch)
    card3 = L.add_account(conn, "Card3", "Card")
    sr = L.recharge_card(conn, cash, card3, "USD", 200, 11)
    L.record_purchase(conn, card3, "v", "USD", [{"catid": cb, "unit_price": 50}], delivery_method="In-Person")
    ok, _ = L.transaction_reversibility(conn, sr)
    ceq("Spent recharge is not reversible", ok, False)

    # transfer pair + fee reverse together
    L.deposit_lyd(conn, cash, 10_000)
    out_id, in_id = L.transfer_lyd(conn, cash, main, 3000, fee=100)
    cb0 = L.lyd_balance(conn, cash)
    L.reverse_transaction(conn, in_id)
    ceq("Reversing a transfer removes both legs", conn.execute(
        "SELECT COUNT(*) AS n FROM all_transactions WHERE trnsid IN (?,?)", (out_id, in_id)).fetchone()["n"], 0)
    check("Reversing a transfer refunds source incl. fee", L.lyd_balance(conn, cash) - cb0, 3000)

    # conversion-sell reverse restores consumed USD exactly
    L.convert_buy(conn, cash, "USD", 300, 11)
    usd0 = L.fx_balance(conn, cash, "USD")
    sid, *_ = L.convert_sell(conn, cash, "USD", 100, 12)
    L.reverse_transaction(conn, sid)
    check("Reversing convert-sell restores USD", L.fx_balance(conn, cash, "USD"), usd0)
    ceq("Reversing convert-sell removes its FX gain/loss", conn.execute(
        "SELECT COUNT(*) AS n FROM all_transactions WHERE type='FX_Gain_Loss'").fetchone()["n"], 0)

    # product-linked is redirected, not deleted
    pid = conn.execute("SELECT trnsid FROM all_transactions WHERE type='Purchase' LIMIT 1").fetchone()["trnsid"]
    expect_raise("Purchase payment isn't reversible directly", L.StateError,
                 lambda: L.reverse_transaction(conn, pid))

    # deposit already spent can't be reversed; unspent can
    d = L.deposit_lyd(conn, main, 5000)
    L.withdraw_lyd(conn, main, L.lyd_balance(conn, main) - 100)   # drain below the deposit
    expect_raise("Spent deposit can't be reversed", L.StateError,
                 lambda: L.reverse_transaction(conn, d))

    # edit a simple LYD transaction
    dep = L.deposit_lyd(conn, main, 1000)
    base = L.lyd_balance(conn, main)
    L.edit_transaction(conn, dep, new_amount=1600)
    check("Editing a deposit adjusts the balance", L.lyd_balance(conn, main) - base, 600)
    expect_raise("Editing a recharge is refused", L.StateError,
                 lambda: L.edit_transaction(conn, sr, new_amount=5))
    conn.close()
    print()


def _qol_feature_regressions():
    """Make-similar-item (clone), listing name/seller-link, and item condition —
    including that condition never splits report grouping (groups by catid)."""
    print("QOL feature regressions:")
    import os
    p = "/tmp/lyware_qol_regression.db"
    if os.path.exists(p):
        os.remove(p)
    conn = L.open_or_create_db(p)

    # migrated columns exist
    icols = [r["name"] for r in conn.execute("PRAGMA table_info(inventory_items)")]
    lcols = [r["name"] for r in conn.execute("PRAGMA table_info(all_listings)")]
    ceq("inventory_items has condition", "condition" in icols, True)
    ceq("inventory_items has condition_note", "condition_note" in icols, True)
    ceq("all_listings has listing_name", "listing_name" in lcols, True)
    ceq("all_listings has seller_link", "seller_link" in lcols, True)

    cb = L.add_catalog_item(conn, "HP Chromebook", "Computers", "HP", "x360",
                            [("RAM", "4GB"), ("Storage", "32GB")])

    # listing name + seller link persist through add and edit
    lid = L.add_listing(conn, "eBay", link="http://item", price=100, currency="USD",
                        seller_name="joe", listing_name="HP lot of 5", seller_link="http://seller/joe")
    al = conn.execute("SELECT listing_name, seller_link FROM all_listings WHERE lsid=?", (lid,)).fetchone()
    ceq("Listing name stored", al["listing_name"], "HP lot of 5")
    ceq("Seller link stored", al["seller_link"], "http://seller/joe")
    L.edit_listing(conn, lid, listing_name="HP lot of 6", seller_link="http://seller/joe2")
    al = conn.execute("SELECT listing_name, seller_link FROM all_listings WHERE lsid=?", (lid,)).fetchone()
    ceq("Listing name edited", al["listing_name"], "HP lot of 6")
    ceq("Seller link edited", al["seller_link"], "http://seller/joe2")

    # condition stored per unit at purchase; defaults to Used
    cash = L.add_account(conn, "Cash", "Cash")
    L.deposit_lyd(conn, cash, 100_000)
    pp = L.record_purchase(conn, cash, "v", "LYD", [
        {"catid": cb, "unit_price": 1000, "condition": "Used", "condition_note": "Grade A"},
        {"catid": cb, "unit_price": 1000, "condition": "Unused", "condition_note": "sealed"},
        {"catid": cb, "unit_price": 1000}], delivery_method="In-Person")
    u_used, u_unused, u_default = [it["lywrid"] for it in pp["items"]]
    g = lambda lyw, col: conn.execute(
        f"SELECT {col} AS v FROM inventory_items WHERE lywrid=?", (lyw,)).fetchone()["v"]
    ceq("Used condition stored", g(u_used, "condition"), "Used")
    ceq("Condition note stored", g(u_used, "condition_note"), "Grade A")
    ceq("Unused condition stored", g(u_unused, "condition"), "Unused")
    ceq("Condition defaults to Used", g(u_default, "condition"), "Used")

    # set_item_condition edits + validates
    L.set_item_condition(conn, u_used, "Unused", "open box")
    ceq("Condition edited", g(u_used, "condition"), "Unused")
    ceq("Condition note edited", g(u_used, "condition_note"), "open box")
    expect_raise("Invalid condition rejected", ValueError,
                 lambda: L.set_item_condition(conn, u_used, "Refurb"))

    # reports group by catid — condition must NOT split the item
    for u in (u_used, u_unused, u_default):
        L.accept_into_inventory(conn, u, "2026-06-20")
    o = L.commit_sale_order(conn, [{"lywrid": u_used, "price": 2000},
                                   {"lywrid": u_unused, "price": 2000}], buyer_name="B")
    L.finalize_sale_order(conn, o, cash, "2026-06-22")
    perf = [row for row in L.catalog_performance(conn) if row["catid"] == cb]
    ceq("One catalogue-performance row regardless of condition", len(perf), 1)
    ceq("Both conditions roll into one item's sold count", perf[0]["qty_sold"], 2)

    # --- bug-fix regressions (adversarial stress pass) ---
    # shipping shares must sum EXACTLY to each shipment's booked cost (no sub-cent drift)
    card = L.add_account(conn, "Card", "Card")
    L.deposit_lyd(conn, cash, 5_000_000)
    L.recharge_card(conn, cash, card, "USD", 20000, 11)
    for ship, n in (("100", 3), ("333.33", 7), ("1", 9), ("99.97", 4)):
        pp2 = L.record_purchase(conn, card, "v", "USD", [{"catid": cb, "unit_price": 5}] * n,
                                delivery_method="International", shipping_cost=ship,
                                shipping_acct=card, shipping_currency="USD")
        ids = [it["lywrid"] for it in pp2["items"]]
        L.start_international_shipment(conn, pp2["shipid"], tracking_number="TS" + ship + str(n))
        booked = conn.execute("SELECT lyd_shipping_cost AS c FROM shipments WHERE shipid=?",
                              (pp2["shipid"],)).fetchone()["c"]
        summed = sum(float(L._item_shipping_cost_lyd(conn, i)) for i in ids)
        check(f"Shipping shares sum exactly ({ship}/{n})", summed, booked)

    # money entry points reject zero/negative (can't sign-flip a deposit into a withdrawal)
    expect_raise("Negative deposit rejected", ValueError, lambda: L.deposit_lyd(conn, cash, -100))
    expect_raise("Zero deposit rejected", ValueError, lambda: L.deposit_lyd(conn, cash, 0))
    expect_raise("Negative withdrawal rejected", ValueError, lambda: L.withdraw_lyd(conn, cash, -50))
    expect_raise("Negative recharge rejected", ValueError,
                 lambda: L.recharge_card(conn, cash, card, "USD", -100, 11))
    expect_raise("Negative convert_buy rejected", ValueError,
                 lambda: L.convert_buy(conn, cash, "USD", -100, 11))
    expect_raise("Negative business expense rejected", ValueError,
                 lambda: L.record_business_expense(conn, cash, -100, "LYD", "x"))
    conn.close()
    print()


def _cost_adjustment_money_regressions():
    """Cost adjustments now move real money: + = expense (withdraw), - = refund (credit),
    FX refunds create a batch at a chosen rate; reversal unwinds the money; basis-only
    (no account) still works for backwards compatibility."""
    print("Cost-adjustment money regressions:")
    import os
    p = "/tmp/lyware_adjmoney_regression.db"
    if os.path.exists(p):
        os.remove(p)
    conn = L.open_or_create_db(p)
    ceq("cost_adjustment_trnsid column migrated", "cost_adjustment_trnsid" in
        [r["name"] for r in conn.execute("PRAGMA table_info(inventory_items)")], True)
    cat = L.add_catalog_item(conn, "Computers", "HP CB", manufacturer="HP", attributes=[])
    cash = L.add_account(conn, "Cash", "Cash")
    card = L.add_account(conn, "Card", "Card")
    L.deposit_lyd(conn, cash, 1_000_000)
    L.recharge_card(conn, cash, card, "USD", 1000, 11)
    u = [it["lywrid"] for it in L.record_purchase(
        conn, cash, "v", "LYD", [{"catid": cat, "unit_price": 1000}] * 5,
        delivery_method="In-Person")["items"]]

    # + LYD adjustment = expense (money out, cost up)
    b0 = L.lyd_balance(conn, cash)
    t = L.accept_into_inventory(conn, u[0], "2026-06-20", cost_adjustment=30,
                                adjustment_acctid=cash, adjustment_currency="LYD")
    check("LYD expense withdraws from account", b0 - L.lyd_balance(conn, cash), 30)
    check("LYD expense raises cost basis", t, 1030)

    # - LYD adjustment = refund (money in, cost down)
    b1 = L.lyd_balance(conn, cash)
    t = L.accept_into_inventory(conn, u[1], "2026-06-20", cost_adjustment=-50,
                                adjustment_acctid=cash, adjustment_currency="LYD")
    check("LYD refund credits the account", L.lyd_balance(conn, cash) - b1, 50)
    check("LYD refund lowers cost basis", t, 950)

    # - USD adjustment = refund into a card as a fresh batch at the chosen rate
    usd0 = L.fx_balance(conn, card, "USD")
    nb0 = conn.execute("SELECT COUNT(*) AS n FROM fx_batches WHERE acctid=?", (card,)).fetchone()["n"]
    t = L.accept_into_inventory(conn, u[2], "2026-06-20", cost_adjustment=-10,
                                adjustment_acctid=card, adjustment_currency="USD", adjustment_rate=11)
    check("USD refund adds USD to the card", L.fx_balance(conn, card, "USD") - usd0, 10)
    ceq("USD refund creates a new batch", conn.execute(
        "SELECT COUNT(*) AS n FROM fx_batches WHERE acctid=?", (card,)).fetchone()["n"], nb0 + 1)
    check("USD refund lowers basis by amount*rate", t, 890)
    expect_raise("USD refund without a rate is rejected", ValueError,
                 lambda: L.accept_into_inventory(conn, u[3], "2026-06-20", cost_adjustment=-5,
                                                 adjustment_acctid=card, adjustment_currency="USD"))

    # + USD adjustment = expense spent FIFO from the card
    usd1 = L.fx_balance(conn, card, "USD")
    t = L.accept_into_inventory(conn, u[3], "2026-06-20", cost_adjustment=5,
                                adjustment_acctid=card, adjustment_currency="USD")
    check("USD expense spends from the card", usd1 - L.fx_balance(conn, card, "USD"), 5)
    check("USD expense raises basis by FIFO LYD", t, 1055)

    # account_batches exposes rates for the picker
    ceq("account_batches returns batch rates", all("rate" in b for b in
        L.account_batches(conn, card, "USD")), True)

    # reversing the acceptance unwinds the money movement
    usd_before = L.fx_balance(conn, card, "USD")
    L.reverse_last_status(conn, u[2])     # had the USD refund
    check("Reversing accept removes the refunded USD", usd_before - L.fx_balance(conn, card, "USD"), 10)
    ceq("Reversed item returns to Pending", L.get_item_status(conn, u[2]), "Pending Approval")
    ceq("Reversed item clears the adjustment link", conn.execute(
        "SELECT cost_adjustment_trnsid AS x FROM inventory_items WHERE lywrid=?",
        (u[2],)).fetchone()["x"], None)

    # the adjustment transaction can't be reversed straight from the ledger
    adjtx = conn.execute("SELECT cost_adjustment_trnsid AS x FROM inventory_items WHERE lywrid=?",
                         (u[1],)).fetchone()["x"]
    ok, _ = L.transaction_reversibility(conn, adjtx)
    ceq("Adjustment txn is not directly ledger-reversible", ok, False)

    # backwards compatibility: no account = cost-only, no money moved
    b2 = L.lyd_balance(conn, cash)
    t = L.accept_into_inventory(conn, u[4], "2026-06-20", cost_adjustment=25)
    ceq("Basis-only adjustment moves no money", L.lyd_balance(conn, cash), b2)
    check("Basis-only adjustment still adjusts cost", t, 1025)
    conn.close()
    print()


def _variant_market_regressions():
    """Variant labels (default A, auto-next within a name family, unique, display suffix only
    when 2+ exist) and local market value from listings."""
    print("Variant + market-value regressions:")
    import os
    p = "/tmp/lyware_variant_regression.db"
    if os.path.exists(p):
        os.remove(p)
    conn = L.open_or_create_db(p)
    ceq("variant column migrated", "variant" in
        [r["name"] for r in conn.execute("PRAGMA table_info(catalog_items)")], True)

    a = L.add_catalog_item(conn, "Laptops", "Dell Precision 7520", manufacturer="Dell",
                           attributes=[("RAM", "16GB")])
    b = L.add_catalog_item(conn, "Laptops", "Dell Precision 7520", manufacturer="Dell",
                           attributes=[("RAM", "32GB")])
    lone = L.add_catalog_item(conn, "Laptops", "HP Victus", manufacturer="HP",
                              attributes=[("RAM", "8GB")])
    g = lambda cid: conn.execute("SELECT variant FROM catalog_items WHERE catid=?", (cid,)).fetchone()["variant"]
    ceq("First in family defaults to A", g(a), "A")
    ceq("Second same-name auto-assigns B", g(b), "B")
    ceq("Unique-name item is A", g(lone), "A")
    ceq("next_variant_label suggests C", L.next_variant_label(conn, "Dell Precision 7520"), "C")

    expect_raise("Duplicate variant label blocked", L.DuplicateCatalogItem,
                 lambda: L.add_catalog_item(conn, "Laptops", "Dell Precision 7520",
                                            manufacturer="Dell", attributes=[("RAM", "64GB")], variant="A"))
    custom = L.add_catalog_item(conn, "Laptops", "Dell Precision 7520", manufacturer="Dell",
                                attributes=[("RAM", "64GB")], variant="64GB")
    ceq("Custom variant label accepted", g(custom), "64GB")

    fam = L.catalog_variants(conn, "Dell Precision 7520")
    ceq("catalog_variants lists the whole family", len(fam), 3)
    ceq("catalog_variants carries spec summaries", all("spec_summary" in v for v in fam), True)

    sm = L.variant_suffix_map(conn)
    ceq("Family member gets a suffix", sm[a], " (A)")
    ceq("Second family member suffix", sm[b], " (B)")
    ceq("Lone item gets no suffix", sm[lone], "")
    pnames = {r["catid"]: r["item"] for r in L.catalog_performance(conn)}
    ceq("Market report row labels variant A", pnames[a], "Dell Precision 7520 (A)")
    ceq("Market report row labels variant B", pnames[b], "Dell Precision 7520 (B)")
    ceq("Market report lone item stays clean", pnames[lone], "HP Victus")
    amap = L.catalog_attributes_map(conn)
    ceq("Attribute map lowercases names", amap[a].get("ram"), "16GB")
    # blank-valued attributes are dropped at insert — 'has the attribute' means has a VALUE,
    # so an attribute column in the market report correctly hides items with blank entries
    blank = L.add_catalog_item(conn, "Laptops", "BlankAttrItem",
                               attributes=[("TempAttr", "  "), ("Real", "yes")])
    bm = L.catalog_attributes_map(conn).get(blank, {})
    ceq("Blank-valued attribute never stored", "tempattr" in bm, False)
    ceq("Real attribute on same item stored", bm.get("real"), "yes")
    L.delete_catalog_item(conn, blank)

    # editing a lone item's name into a family auto-reassigns its colliding default
    solo = L.add_catalog_item(conn, "Tablets", "iPad", attributes=[("Gen", "9")])
    ceq("Solo starts at A", g(solo), "A")
    L.update_catalog_item(conn, solo, "Laptops", "Dell Precision 7520", manufacturer="Dell",
                          attributes=[("RAM", "128GB")])  # renamed into the Dell family
    ceq("Renamed-into-family item avoids colliding with A", g(solo) != "A", True)

    # market value: local LYD only, outlier-robust median
    cash = L.add_account(conn, "Cash", "Cash")
    L.deposit_lyd(conn, cash, 100000)
    for price in (9000, 9500, 10000, 30000):     # 30000 = outlier
        lid = L.add_listing(conn, "Facebook", price=price, currency="LYD", seller_name="s")
        L.set_listing_items(conn, lid, [(a, 1, price)])
    lid = L.add_listing(conn, "eBay", price=120, currency="USD", seller_name="x")  # excluded
    L.set_listing_items(conn, lid, [(a, 1, 120)])
    mv = L.market_value(conn, a)
    ceq("Market value counts only local LYD listings", mv["count"], 4)
    check("Market value average", mv["avg"], 14625)
    check("Market value median resists the outlier", mv["median"], 9750)
    check("Market value min", mv["min"], 9000)
    check("Market value max", mv["max"], 30000)
    mm = L.market_value_map(conn)
    ceq("market_value_map includes the item", a in mm and mm[a]["n"] == 4, True)
    ceq("market_value_map excludes a no-listing item", lone in mm, False)
    conn.close()
    print()


def _upgrade_v10_regressions():
    """v10 upgrade pass: listing archive + market recency window, market trend, consistent
    backups via the SQLite backup API, health check, and inventory aging."""
    print("v10 upgrade regressions:")
    import os, sqlite3
    from datetime import date, timedelta
    p = "/tmp/lyware_v10_regression.db"
    if os.path.exists(p):
        os.remove(p)
    conn = L.open_or_create_db(p)
    ceq("is_archived column migrated", "is_archived" in
        [r["name"] for r in conn.execute("PRAGMA table_info(all_listings)")], True)

    cat = L.add_catalog_item(conn, "Laptops", "Dell 7520", attributes=[("RAM", "16GB")])
    cash = L.add_account(conn, "Cash", "Cash")
    L.deposit_lyd(conn, cash, 100000)
    today = date.today().isoformat()
    old = (date.today() - timedelta(days=200)).isoformat()
    l_new = L.add_listing(conn, "Facebook", price=1000, currency="LYD", seller_name="s",
                          date_of_listing=today)
    L.set_listing_items(conn, l_new, [(cat, 1, 1000)])
    l_old = L.add_listing(conn, "Facebook", price=5000, currency="LYD", seller_name="s",
                          date_of_listing=old)
    L.set_listing_items(conn, l_old, [(cat, 1, 5000)])
    l_nodate = L.add_listing(conn, "Facebook", price=1200, currency="LYD", seller_name="s")
    L.set_listing_items(conn, l_nodate, [(cat, 1, 1200)])

    mv = L.market_value(conn, cat)
    ceq("90-day window drops a 200-day-old listing", mv["count"], 2)
    ceq("Undated listings stay in the window", any(l["lsid"] == l_nodate for l in mv["listings"]), True)
    ceq("days=None widens to all time", L.market_value(conn, cat, days=None)["count"], 3)
    ceq("Window date range reported", mv["date_from"], today)

    L.set_listing_archived(conn, l_new, True)
    ceq("Archived listing excluded from market value", L.market_value(conn, cat)["count"], 1)
    L.set_listing_archived(conn, l_new, False)
    ceq("Restored listing counts again", L.market_value(conn, cat)["count"], 2)
    ceq("market_value_map honours window + archive", L.market_value_map(conn)[cat]["n"], 2)
    expect_raise("Archiving a missing listing rejected", ValueError,
                 lambda: L.set_listing_archived(conn, 99999, True))

    l_mid = L.add_listing(conn, "Facebook", price=900, currency="LYD", seller_name="s",
                          date_of_listing=(date.today() - timedelta(days=40)).isoformat())
    L.set_listing_items(conn, l_mid, [(cat, 1, 900)])
    tr = L.market_value_trend(conn, cat)
    ceq("Trend returns (month, median, n) rows", len(tr) >= 2 and all(len(x) == 3 for x in tr), True)

    # consistent backup while a write transaction is open
    conn.execute("BEGIN")
    conn.execute("UPDATE accounts SET account_name='Cash' WHERE acctid=?", (cash,))
    b = L.make_backup(p, reason="regress")
    conn.commit()
    bc = sqlite3.connect(b)
    ceq("Backup passes integrity while DB mid-write",
        bc.execute("PRAGMA integrity_check").fetchone()[0], "ok")
    bc.close()
    e = L.export_backup("/tmp/lyware_v10_export.db", p)
    ec = sqlite3.connect(e)
    ceq("Exported backup passes integrity", ec.execute("PRAGMA integrity_check").fetchone()[0], "ok")
    ec.close()

    hc = L.health_check(conn)
    ceq("Health check runs 10 checks", len(hc), 10)
    ceq("Health check all-green on a clean DB", all(h["ok"] for h in hc), True)
    # a currency conversion with a gain writes an informational FX_Gain_Loss row;
    # reconciliation must apply the affects_balance rule or it cries wolf on every sale of USD
    L.convert_buy(conn, cash, "USD", 50, 10)
    L.convert_sell(conn, cash, "USD", 50, 12)
    hc_conv = L.health_check(conn)
    ceq("Conversion gain does not trip reconciliation",
        all(h["ok"] for h in hc_conv if "reconcile" in h["check"].lower()), True)
    # seed an inconsistency: a negative batch remainder must be caught
    L.recharge_card(conn, cash, L.add_account(conn, "Card", "Card"), "USD", 100, 11)
    conn.execute("UPDATE fx_batches SET fx_remaining=-5 WHERE bachid=(SELECT MAX(bachid) FROM fx_batches)")
    hc2 = L.health_check(conn)
    bad = [h for h in hc2 if not h["ok"]]
    ceq("Health check catches a negative batch remainder",
        any("negative" in h["check"].lower() for h in bad), True)
    conn.execute("UPDATE fx_batches SET fx_remaining=100 WHERE fx_remaining=-5")

    # report view alignment: catalog_performance carries the same windowed local value
    perf = [r for r in L.catalog_performance(conn) if r["catid"] == cat][0]
    check("catalog_performance local value matches windowed map",
          perf["local_value_avg"], L.market_value_map(conn)[cat]["avg"])
    ceq("catalog_performance local n matches", perf["local_value_n"],
        L.market_value_map(conn)[cat]["n"])
    # archived listings must vanish from the report's Avg list too, not just Local value
    L.set_market_rate(conn, 10)
    lus = L.add_listing(conn, "eBay", price=100, currency="USD", seller_name="u",
                        date_of_listing=today)
    L.set_listing_items(conn, lus, [(cat, 1, 100)])
    with_usd = [r for r in L.catalog_performance(conn) if r["catid"] == cat][0]
    L.set_listing_archived(conn, lus, True)
    without = [r for r in L.catalog_performance(conn) if r["catid"] == cat][0]
    ceq("Report drops archived listing from the count",
        without["times_listed"], with_usd["times_listed"] - 1)
    ceq("Report avg recomputes without the archived listing",
        float(without["avg_listing_price"]) != float(with_usd["avg_listing_price"]), True)
    L.set_listing_archived(conn, lus, False)
    perf_all = [r for r in L.catalog_performance(conn, market_days=None) if r["catid"] == cat][0]
    ceq("market_days=None widens the report figure", perf_all["local_value_n"] >
        perf["local_value_n"], True)
    import lyware_reports as R
    R.build_report(conn, "catalogue", {}, "/tmp/lyware_v10_cat.xlsx")
    ceq("catalogue xlsx builds with local-value columns",
        os.path.getsize("/tmp/lyware_v10_cat.xlsx") > 1000, True)

    u = L.record_purchase(conn, cash, "v", "LYD", [{"catid": cat, "unit_price": 1000}],
                          delivery_method="In-Person")["items"][0]["lywrid"]
    L.accept_into_inventory(conn, u, (date.today() - timedelta(days=75)).isoformat())
    ag = L.inventory_aging(conn)
    ceq("Aging buckets cover all stock", sum(b["count"] for b in ag), 1)
    ceq("A 75-day unit lands in the 61-90 bucket", ag[2]["count"], 1)
    check("Aging bucket carries the unit's value", ag[2]["value"], 1000)
    conn.close()
    print()


def _market_rate_regressions():
    """Current market USD->LYD rate: history-backed, values LISTED items in reports at the
    street rate, never touches batches/cost basis. LYD-normalised listing averages."""
    print("Market-rate regressions:")
    import os
    p = "/tmp/lyware_rate_regression.db"
    if os.path.exists(p):
        os.remove(p)
    conn = L.open_or_create_db(p)
    ceq("market_rate_history table migrated", conn.execute(
        "SELECT name FROM sqlite_master WHERE name='market_rate_history'").fetchone() is not None, True)
    ceq("Rate unset -> None", L.get_market_rate(conn), None)

    cat = L.add_catalog_item(conn, "Laptops", "Dell", attributes=[])
    cash = L.add_account(conn, "Cash", "Cash")
    card = L.add_account(conn, "Card", "Card")
    L.deposit_lyd(conn, cash, 100000)
    L.recharge_card(conn, cash, card, "USD", 500, 10)          # batch at 10
    u = L.record_purchase(conn, card, "v", "USD", [{"catid": cat, "unit_price": 100}],
                          delivery_method="In-Person")["items"][0]["lywrid"]
    L.accept_into_inventory(conn, u, "2026-06-20")
    l1 = L.add_listing(conn, "Facebook", price=1000, currency="LYD", seller_name="s")
    L.set_listing_items(conn, l1, [(cat, 1, 1000)])
    l2 = L.add_listing(conn, "eBay", price=100, currency="USD", seller_name="s")
    L.set_listing_items(conn, l2, [(cat, 1, 100)])

    perf = [r for r in L.catalog_performance(conn) if r["catid"] == cat][0]
    check("No rate: USD listings excluded from LYD average", perf["avg_listing_price"], 1000)
    ceq("Listed count still includes the USD listing", perf["times_listed"], 2)

    L.set_market_rate(conn, 8.7)
    check("Rate stored", L.get_market_rate(conn), 8.7)
    perf = [r for r in L.catalog_performance(conn) if r["catid"] == cat][0]
    check("USD listing valued at street rate: (1000 + 870)/2", perf["avg_listing_price"], 935)
    check("Cost basis stays on the BATCH rate (10), untouched", conn.execute(
        "SELECT total_cost AS c FROM inventory_items WHERE lywrid=?", (u,)).fetchone()["c"], 1000)

    L.set_market_rate(conn, 9.5)
    perf = [r for r in L.catalog_performance(conn) if r["catid"] == cat][0]
    check("Changing the rate re-values listings globally", perf["avg_listing_price"], 975)
    hist = L.market_rate_history(conn)
    ceq("History keeps every change, newest first", [str(h["rate"]) for h in hist],
        ["9.5000", "8.7000"])
    ceq("History rows carry timestamps", all(h["date"] and h["time"] for h in hist), True)
    expect_raise("Zero rate rejected", ValueError, lambda: L.set_market_rate(conn, 0))
    expect_raise("Negative rate rejected", ValueError, lambda: L.set_market_rate(conn, -3))

    import lyware_reports as R
    R.build_report(conn, "catalogue", {}, "/tmp/lyware_rate_cat.xlsx")
    ceq("Catalogue xlsx builds with LYD-normalised column",
        os.path.getsize("/tmp/lyware_rate_cat.xlsx") > 1000, True)
    conn.close()
    print()


if __name__ == "__main__":
    main()
