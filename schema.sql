-- =====================================================================
--  LYWARE  —  SQLite schema  (v4: multi-item sale orders, approval gate,
--  account hiding, change log)
--  Run in DB Browser: Execute SQL -> paste -> run. Keep the PRAGMA and tick
--  Edit > Preferences > "Enable foreign keys".
-- =====================================================================
PRAGMA foreign_keys = ON;

-- =====================================================================
-- 0. LOOKUP / REFERENCE TABLES
-- =====================================================================
CREATE TABLE transaction_types (
    type             TEXT PRIMARY KEY,
    category         TEXT NOT NULL CHECK (category IN ('Capital','Expense','Revenue','Neutral','GainLoss')),
    affects_balance  INTEGER NOT NULL CHECK (affects_balance IN (0,1)),
    description      TEXT
);

INSERT INTO transaction_types (type, category, affects_balance, description) VALUES
  ('Deposit',          'Capital',  1, 'Owner funds into the business (capital). Not an expense.'),
  ('Withdrawal',       'Capital',  1, 'Owner funds out to a personal/bank account. Not negative revenue.'),
  ('Recharge',         'Neutral',  1, 'LYD spent to put FX onto a Card (creates an fx_batch).'),
  ('Conversion_Buy',   'Neutral',  1, 'LYD spent to acquire FX inside a Cash/Digital account.'),
  ('Conversion_Sell',  'Neutral',  1, 'FX cashed out to LYD; difference vs cost basis = FX gain/loss.'),
  ('Transfer',         'Neutral',  1, 'Move of funds between own accounts (paired rows).'),
  ('Transfer_Fee',     'Expense',  1, 'Fee incurred on a transfer.'),
  ('FX_Gain_Loss',     'GainLoss', 0, 'Value from exchange-rate movement on cash-out. P&L only, not cash.'),
  ('Purchase',         'Expense',  1, 'Buying inventory.'),
  ('Shipping_Expense', 'Expense',  1, 'Cost of shipping (inbound to shop or outbound to customer).'),
  ('Sale',             'Revenue',  1, 'Selling inventory.'),
  ('Refund_Received',  'Expense',  1, 'Money back from a seller (cancel/return) — offsets purchase expense.'),
  ('Refund_Issued',    'Revenue',  1, 'Money refunded to a customer (return) — offsets sale revenue.'),
  ('Business_Expense', 'Expense',  1, 'Operating expense not tied to a product.');

CREATE TABLE inventory_statuses (
    status TEXT PRIMARY KEY, stage TEXT NOT NULL, description TEXT
);
INSERT INTO inventory_statuses (status, stage, description) VALUES
  ('Awaiting Shipment',    'shipping',  'Bought; seller has not shipped / no tracking yet.'),
  ('International Transit', 'shipping',  'In transit to the US/Libya warehouse.'),
  ('At Libya Warehouse',   'shipping',  'Arrived at Libya warehouse; awaiting local move or pickup.'),
  ('Local Transit',        'shipping',  'In local shipping to the local office.'),
  ('At Local Office',      'shipping',  'At local office; awaiting collection.'),
  ('Pending Approval',     'approval',  'Shipping done or bought in person; awaiting OK into inventory.'),
  ('In Stock',             'inventory', 'In sellable inventory.'),
  ('Sold Pending',         'sold',      'Part of a committed sale order; not yet finalized.'),
  ('Sold',                 'sold',      'Sale finalized.'),
  ('Defective',            'issue',     'Damaged/defective.'),
  ('Returned',             'issue',     'Returned by customer.'),
  ('Cancelled',            'closed',    'Order cancelled by seller / never shipped.'),
  ('Written Off',          'closed',    'Scrapped — damaged or defective beyond use.'),
  ('Returned to Seller',   'closed',    'Sent back to the seller.'),
  ('Customer Returned',    'closed',    'Returned by the customer.');

-- =====================================================================
-- 0.5  CATALOG / REPOSITORY  (v5: item-type repository + EAV attributes)
--   catalog_items = a TYPE / variant of product (NOT a physical unit).
--   Each distinct configuration is its own row (4GB vs 8GB = two rows).
--   Specs are open-ended (name,value) attributes; attribute NAMES come from
--   an editable vocabulary, values are free text. A signature fingerprints
--   core fields + the full attribute set so identical items can't duplicate.
-- =====================================================================
CREATE TABLE categories (
    cat_name   TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE manufacturers (
    manu_name  TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE attribute_names (
    attr_name  TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE catalog_items (
    catid         INTEGER PRIMARY KEY AUTOINCREMENT,
    category      TEXT NOT NULL,                 -- required (FK categories)
    manufacturer  TEXT,                          -- nullable (FK manufacturers)
    model_name    TEXT,                          -- nullable, free text
    display_name  TEXT NOT NULL,                 -- required, free text
    signature     TEXT NOT NULL UNIQUE,          -- canonical fingerprint (core + attrs)
    variant       TEXT NOT NULL DEFAULT 'A',     -- v9: display label to disambiguate same-named items
    is_hidden     INTEGER NOT NULL DEFAULT 0 CHECK (is_hidden IN (0,1)),
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category) REFERENCES categories(cat_name),
    FOREIGN KEY (manufacturer) REFERENCES manufacturers(manu_name)
);

CREATE TABLE catalog_attributes (
    catattrid  INTEGER PRIMARY KEY AUTOINCREMENT,
    catid      INTEGER NOT NULL,
    attr_name  TEXT NOT NULL,                    -- FK attribute_names (controlled)
    attr_value TEXT NOT NULL,                    -- free text
    sort_order INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (catid) REFERENCES catalog_items(catid) ON DELETE CASCADE,
    FOREIGN KEY (attr_name) REFERENCES attribute_names(attr_name)
);

-- Persistent UI preferences (e.g. per-table visible-column choices)
CREATE TABLE ui_prefs (
    pref_key   TEXT PRIMARY KEY,
    pref_value TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================
-- 1. ACCOUNTS, LEDGER & FX BATCHES
-- =====================================================================
CREATE TABLE accounts (
    acctid        INTEGER PRIMARY KEY AUTOINCREMENT,
    account_name  TEXT NOT NULL,
    account_type  TEXT NOT NULL CHECK (account_type IN ('Cash','Digital Funds','Card')),
    is_hidden     INTEGER NOT NULL DEFAULT 0 CHECK (is_hidden IN (0,1)),
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE all_transactions (
    trnsid INTEGER PRIMARY KEY AUTOINCREMENT, acctid INTEGER NOT NULL, type TEXT NOT NULL,
    amount NUMERIC NOT NULL, currency TEXT NOT NULL, linked_transfer_id INTEGER,
    date TEXT NOT NULL, time TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (acctid) REFERENCES accounts(acctid),
    FOREIGN KEY (type) REFERENCES transaction_types(type),
    FOREIGN KEY (linked_transfer_id) REFERENCES all_transactions(trnsid)
);

CREATE TABLE fx_batches (
    bachid INTEGER PRIMARY KEY AUTOINCREMENT, acctid INTEGER NOT NULL, trnsid INTEGER NOT NULL,
    currency TEXT NOT NULL, fx_amount NUMERIC NOT NULL, rate NUMERIC NOT NULL,
    lyd_cost NUMERIC NOT NULL, fx_remaining NUMERIC NOT NULL, source TEXT NOT NULL,
    date_acquired TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (acctid) REFERENCES accounts(acctid),
    FOREIGN KEY (trnsid) REFERENCES all_transactions(trnsid)
);

CREATE TABLE batch_allocations (
    alocid INTEGER PRIMARY KEY AUTOINCREMENT, trnsid INTEGER NOT NULL, bachid INTEGER NOT NULL,
    fx_consumed NUMERIC NOT NULL, rate_applied NUMERIC NOT NULL, lyd_allocated NUMERIC NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (trnsid) REFERENCES all_transactions(trnsid),
    FOREIGN KEY (bachid) REFERENCES fx_batches(bachid)
);

-- =====================================================================
-- 2. LISTINGS
-- =====================================================================
CREATE TABLE all_listings (
    lsid INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT NOT NULL, link TEXT, price NUMERIC,
    currency TEXT, qty_items INTEGER, seller_name TEXT, date_of_listing TEXT,
    phone_number TEXT,                          -- v6 (BUG4): contact phone, all platforms, nullable
    listing_name TEXT, seller_link TEXT,        -- v8: human name for the listing + link to seller
    is_archived INTEGER NOT NULL DEFAULT 0,     -- v10: archived listings drop out of market value
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE ebay_listings (
    ebid INTEGER PRIMARY KEY AUTOINCREMENT, lsid INTEGER NOT NULL, ebay_item_number TEXT,
    link TEXT, price NUMERIC, currency TEXT, seller_name TEXT,
    FOREIGN KEY (lsid) REFERENCES all_listings(lsid));
CREATE TABLE amazon_listings (
    amid INTEGER PRIMARY KEY AUTOINCREMENT, lsid INTEGER NOT NULL, asin TEXT, link TEXT,
    price NUMERIC, currency TEXT, FOREIGN KEY (lsid) REFERENCES all_listings(lsid));
CREATE TABLE facebook_listings (
    fbid INTEGER PRIMARY KEY AUTOINCREMENT, lsid INTEGER NOT NULL, link TEXT,
    FOREIGN KEY (lsid) REFERENCES all_listings(lsid));
CREATE TABLE inperson_listings (
    ipid INTEGER PRIMARY KEY AUTOINCREMENT, lsid INTEGER NOT NULL, seller_name TEXT,
    FOREIGN KEY (lsid) REFERENCES all_listings(lsid));

-- What a listing actually offers: catalog items + quantity (1 row per product,
-- even for 50 identical units — the count lives in `quantity`, not repeated rows).
CREATE TABLE listing_items (
    lnitid    INTEGER PRIMARY KEY AUTOINCREMENT,
    lsid      INTEGER NOT NULL,
    catid     INTEGER NOT NULL,
    quantity  INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 1),
    unit_price NUMERIC,                         -- v6 (M1): per-item listing price, nullable
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (lsid)  REFERENCES all_listings(lsid) ON DELETE CASCADE,
    FOREIGN KEY (catid) REFERENCES catalog_items(catid));

-- =====================================================================
-- 3. PURCHASES
-- =====================================================================
CREATE TABLE purchase_orders (
    poid INTEGER PRIMARY KEY AUTOINCREMENT, trnsid INTEGER NOT NULL, vendor_name TEXT NOT NULL,
    purchaser_name TEXT, order_date TEXT NOT NULL, total_paid NUMERIC NOT NULL, currency TEXT NOT NULL,
    delivery_method TEXT CHECK (delivery_method IN ('International','Local','In-Person')),
    lsid INTEGER,                               -- v6 (M2/M3): listing this purchase was made from, nullable
    receipt_path TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (trnsid) REFERENCES all_transactions(trnsid),
    FOREIGN KEY (lsid) REFERENCES all_listings(lsid));
CREATE TABLE purchase_lines (
    polnid INTEGER PRIMARY KEY AUTOINCREMENT, poid INTEGER NOT NULL, lsid INTEGER,
    catid INTEGER,                              -- v5: catalog item this line buys (nullable in phase 1)
    item_name TEXT NOT NULL, unit_price_allocated NUMERIC NOT NULL, currency TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (poid) REFERENCES purchase_orders(poid),
    FOREIGN KEY (lsid) REFERENCES all_listings(lsid),
    FOREIGN KEY (catid) REFERENCES catalog_items(catid));

-- =====================================================================
-- 4. INVENTORY
-- =====================================================================
CREATE TABLE inventory_items (
    lywrid INTEGER PRIMARY KEY AUTOINCREMENT, polnid INTEGER NOT NULL, serial_number TEXT,
    catid INTEGER,                              -- v5: catalog item this unit is an instance of (nullable in phase 1)
    lyd_cost_basis NUMERIC NOT NULL, cost_adjustment NUMERIC NOT NULL DEFAULT 0,
    cost_adjustment_note TEXT, total_cost NUMERIC, status TEXT NOT NULL,
    date_entered_inventory TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closure_recovery NUMERIC NOT NULL DEFAULT 0, closure_note TEXT, closure_date TEXT,
    condition TEXT NOT NULL DEFAULT 'Used', condition_note TEXT,
    cost_adjustment_trnsid INTEGER REFERENCES all_transactions(trnsid),
    FOREIGN KEY (polnid) REFERENCES purchase_lines(polnid),
    FOREIGN KEY (catid) REFERENCES catalog_items(catid),
    FOREIGN KEY (status) REFERENCES inventory_statuses(status)
);

-- =====================================================================
-- 5. SALES  (header / detail — one order, many atomized items)
-- =====================================================================
CREATE TABLE sales_orders (
    sale_order_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_name             TEXT,
    buyer_phone            TEXT,                -- v6 (M13): buyer contact phone, nullable
    currency               TEXT NOT NULL,
    requires_shipping      INTEGER NOT NULL DEFAULT 0 CHECK (requires_shipping IN (0,1)),
    status                 TEXT NOT NULL CHECK (status IN ('Order Placed','Shipping','Finalized')),
    trnsid                 INTEGER,             -- single revenue txn; NULL until paid
    date_committed         TEXT NOT NULL,
    date_arrived_customer  TEXT,
    paid_in_full           INTEGER NOT NULL DEFAULT 0 CHECK (paid_in_full IN (0,1)),
    date_finalized         TEXT,
    created_at             TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (trnsid) REFERENCES all_transactions(trnsid));

CREATE TABLE sales (
    slsid                       INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_order_id               INTEGER NOT NULL,
    lywrid                      INTEGER NOT NULL,
    sale_price                  NUMERIC NOT NULL,
    additional_sales_cost       NUMERIC NOT NULL DEFAULT 0,
    additional_sales_cost_note  TEXT,
    created_at                  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sale_order_id) REFERENCES sales_orders(sale_order_id),
    FOREIGN KEY (lywrid) REFERENCES inventory_items(lywrid));

-- =====================================================================
-- 6. INBOUND SHIPPING  (to the shop) — cost on the supertype
-- =====================================================================
CREATE TABLE shipments (
    shipid INTEGER PRIMARY KEY AUTOINCREMENT,
    shipment_type TEXT NOT NULL CHECK (shipment_type IN ('International','Local')),
    shipping_cost NUMERIC, shipping_cost_currency TEXT, lyd_shipping_cost NUMERIC,
    shipping_paid_trnsid INTEGER, date_arrived_shop TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (shipping_paid_trnsid) REFERENCES all_transactions(trnsid));
CREATE TABLE international_shipping (
    intid INTEGER PRIMARY KEY AUTOINCREMENT, shipid INTEGER NOT NULL, tracking_number TEXT,
    freight_forwarder_name TEXT, flight_number TEXT, weight_kg NUMERIC,
    date_arrived_us_warehouse TEXT, date_arrived_libya_warehouse TEXT, date_picked_up TEXT,
    FOREIGN KEY (shipid) REFERENCES shipments(shipid));
CREATE TABLE local_shipping (
    locid INTEGER PRIMARY KEY AUTOINCREMENT, shipid INTEGER NOT NULL, shipping_office_name TEXT,
    date_shipped TEXT, date_arrived_local_office TEXT,
    FOREIGN KEY (shipid) REFERENCES shipments(shipid));
CREATE TABLE shipment_items (
    shpitid INTEGER PRIMARY KEY AUTOINCREMENT, shipid INTEGER NOT NULL, lywrid INTEGER NOT NULL,
    FOREIGN KEY (shipid) REFERENCES shipments(shipid),
    FOREIGN KEY (lywrid) REFERENCES inventory_items(lywrid));

-- =====================================================================
-- 7. OUTBOUND SHIPPING  (to the customer) — per ORDER, local only
-- =====================================================================
CREATE TABLE customer_shipments (
    cshipid INTEGER PRIMARY KEY AUTOINCREMENT, sale_order_id INTEGER NOT NULL,
    postal_office_name TEXT, shipping_cost NUMERIC NOT NULL DEFAULT 0, shipping_cost_currency TEXT,
    shipping_paid_trnsid INTEGER, date_shipped_to_customer TEXT, date_arrived_customer TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sale_order_id) REFERENCES sales_orders(sale_order_id),
    FOREIGN KEY (shipping_paid_trnsid) REFERENCES all_transactions(trnsid));

-- =====================================================================
-- 8. BUSINESS EXPENSES  &  CHANGE LOG
-- =====================================================================
CREATE TABLE business_expenses (
    bexpid INTEGER PRIMARY KEY AUTOINCREMENT, trnsid INTEGER NOT NULL, category TEXT,
    description TEXT, date TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (trnsid) REFERENCES all_transactions(trnsid));

CREATE TABLE change_log (
    logid   INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    action  TEXT NOT NULL,        -- INSERT / UPDATE / STATUS / ...
    entity  TEXT NOT NULL,        -- which concept/table
    ref     TEXT,                 -- id it refers to
    detail  TEXT                  -- human-readable summary
);

-- =====================================================================
-- Indexes
-- =====================================================================
CREATE INDEX idx_batches_acct   ON fx_batches(acctid, currency, fx_remaining);
CREATE INDEX idx_alloc_trns     ON batch_allocations(trnsid);
CREATE INDEX idx_txn_acct       ON all_transactions(acctid, currency);
CREATE INDEX idx_txn_type       ON all_transactions(type);
CREATE INDEX idx_inv_status     ON inventory_items(status);
CREATE INDEX idx_sales_order    ON sales(sale_order_id);
CREATE INDEX idx_shipitems_lyw  ON shipment_items(lywrid);
CREATE INDEX idx_custship_order ON customer_shipments(sale_order_id);
CREATE INDEX idx_catattr_cat    ON catalog_attributes(catid);
CREATE INDEX idx_catattr_name   ON catalog_attributes(attr_name);
CREATE INDEX idx_catitem_cat    ON catalog_items(category);
CREATE INDEX idx_listitems_ls   ON listing_items(lsid);
CREATE INDEX idx_listitems_cat  ON listing_items(catid);
CREATE INDEX idx_pline_catid    ON purchase_lines(catid);
CREATE INDEX idx_inv_catid      ON inventory_items(catid);

-- v11: the CURRENT market USD->LYD rate for valuing LISTED items in reports.
-- Deliberately separate from fx_batches: batches freeze the rate your OWNED dollars
-- were bought at (cost basis); this rate answers "what is a $100 listing worth in
-- LYD on the street today?" and is expected to change often. Latest row = current.
CREATE TABLE IF NOT EXISTS market_rate_history (
    mrid     INTEGER PRIMARY KEY AUTOINCREMENT,
    rate     REAL NOT NULL,
    set_date TEXT NOT NULL,
    set_time TEXT NOT NULL
);
