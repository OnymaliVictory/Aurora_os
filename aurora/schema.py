"""Database structure. Each entry in MIGRATIONS runs once, in order, and is recorded in
PRAGMA user_version — so a shop that already has data upgrades safely when we add things.

Money is ALWAYS stored as whole kobo (integers). ₦1,250.50 = 125050. That avoids the
rounding errors floats cause. Quantities are REAL so weighed goods (1.250 kg) work.
"""

MIGRATIONS = []

MIGRATIONS.append((1, """
CREATE TABLE settings (
  key   TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  name          TEXT NOT NULL,
  username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,
  pin_hash      TEXT,                                   -- manager PIN for approvals
  role          TEXT NOT NULL CHECK (role IN ('owner','manager','cashier')),
  phone         TEXT,
  is_active     INTEGER NOT NULL DEFAULT 1,
  failed_logins INTEGER NOT NULL DEFAULT 0,
  locked_until  TEXT,
  last_login_at TEXT,
  created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE categories (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  name      TEXT NOT NULL UNIQUE COLLATE NOCASE,
  color     TEXT NOT NULL DEFAULT '#34d399',
  emoji     TEXT NOT NULL DEFAULT '🛒',
  is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE suppliers (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  name           TEXT NOT NULL,
  company        TEXT,
  contact_person TEXT,
  phone          TEXT,
  email          TEXT,
  address        TEXT,
  payment_terms  TEXT,
  is_active      INTEGER NOT NULL DEFAULT 1,
  created_at     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE products (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL,
  sku         TEXT UNIQUE,
  barcode     TEXT UNIQUE,
  category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
  supplier_id INTEGER REFERENCES suppliers(id)  ON DELETE SET NULL,
  brand       TEXT,
  unit        TEXT NOT NULL DEFAULT 'pcs',
  is_weighed  INTEGER NOT NULL DEFAULT 0,              -- sold by weight (kg) at the till
  cost_kobo   INTEGER NOT NULL DEFAULT 0,
  price_kobo  INTEGER NOT NULL DEFAULT 0,
  tax_exempt  INTEGER NOT NULL DEFAULT 0,
  min_stock   REAL NOT NULL DEFAULT 5,
  qty         REAL NOT NULL DEFAULT 0,                 -- always = SUM(product_lots.qty)
  track_stock INTEGER NOT NULL DEFAULT 1,
  status      TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive')),
  total_sold  REAL NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  updated_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  deleted_at  TEXT
);
CREATE INDEX idx_products_name ON products(name);
CREATE INDEX idx_products_category ON products(category_id);

-- Every delivery / batch of a product, with its own expiry date. Sales take from the
-- batch that expires FIRST (FEFO) so old stock never gets stuck at the back of the shelf.
CREATE TABLE product_lots (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  qty         REAL NOT NULL,
  expiry_date TEXT,
  cost_kobo   INTEGER NOT NULL DEFAULT 0,
  received_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  note        TEXT,
  po_id       INTEGER
);
CREATE INDEX idx_lots_product ON product_lots(product_id);

-- The permanent diary of every stock change. Never edited, only added to.
CREATE TABLE stock_movements (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  lot_id     INTEGER,
  qty_change REAL NOT NULL,
  qty_after  REAL NOT NULL,
  reason     TEXT NOT NULL,   -- purchase, sale, refund, damage, expired, correction, stocktake, opening
  ref_type   TEXT,
  ref_id     INTEGER,
  user_id    INTEGER,
  note       TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX idx_moves_product ON stock_movements(product_id, created_at);

CREATE TABLE customers (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  name              TEXT NOT NULL,
  phone             TEXT UNIQUE,
  email             TEXT,
  address           TEXT,
  dob               TEXT,
  notes             TEXT,
  loyalty_points    INTEGER NOT NULL DEFAULT 0,
  credit_limit_kobo INTEGER NOT NULL DEFAULT 0,
  balance_kobo      INTEGER NOT NULL DEFAULT 0,        -- what the customer owes the shop
  total_spent_kobo  INTEGER NOT NULL DEFAULT 0,
  orders_count      INTEGER NOT NULL DEFAULT 0,
  is_active         INTEGER NOT NULL DEFAULT 1,
  created_at        TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE shifts (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id            INTEGER NOT NULL REFERENCES users(id),
  opened_at          TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  closed_at          TEXT,
  opening_float_kobo INTEGER NOT NULL DEFAULT 0,
  counted_cash_kobo  INTEGER,
  expected_cash_kobo INTEGER,
  difference_kobo    INTEGER,
  notes              TEXT,
  status             TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed'))
);

CREATE TABLE sales (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  receipt_no     TEXT NOT NULL UNIQUE,
  shift_id       INTEGER REFERENCES shifts(id),
  cashier_id     INTEGER NOT NULL REFERENCES users(id),
  customer_id    INTEGER REFERENCES customers(id) ON DELETE SET NULL,
  subtotal_kobo  INTEGER NOT NULL DEFAULT 0,
  discount_kobo  INTEGER NOT NULL DEFAULT 0,
  tax_kobo       INTEGER NOT NULL DEFAULT 0,
  total_kobo     INTEGER NOT NULL DEFAULT 0,
  paid_kobo      INTEGER NOT NULL DEFAULT 0,
  change_kobo    INTEGER NOT NULL DEFAULT 0,
  points_earned  INTEGER NOT NULL DEFAULT 0,
  status         TEXT NOT NULL DEFAULT 'completed'
                 CHECK (status IN ('completed','voided','refunded','partially_refunded')),
  note           TEXT,
  void_reason    TEXT,
  voided_by      INTEGER,
  created_at     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX idx_sales_created ON sales(created_at);
CREATE INDEX idx_sales_shift ON sales(shift_id);

CREATE TABLE sale_items (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  sale_id          INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
  product_id       INTEGER NOT NULL REFERENCES products(id),
  name             TEXT NOT NULL,
  unit_price_kobo  INTEGER NOT NULL,
  cost_kobo        INTEGER NOT NULL DEFAULT 0,
  qty              REAL NOT NULL,
  discount_kobo    INTEGER NOT NULL DEFAULT 0,
  tax_kobo         INTEGER NOT NULL DEFAULT 0,
  total_kobo       INTEGER NOT NULL,
  returned_qty     REAL NOT NULL DEFAULT 0
);
CREATE INDEX idx_items_sale ON sale_items(sale_id);
CREATE INDEX idx_items_product ON sale_items(product_id);

CREATE TABLE payments (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  sale_id     INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
  method      TEXT NOT NULL CHECK (method IN ('cash','card','transfer','credit','points')),
  amount_kobo INTEGER NOT NULL,
  reference   TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE refunds (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  sale_id     INTEGER NOT NULL REFERENCES sales(id),
  user_id     INTEGER NOT NULL REFERENCES users(id),
  approved_by INTEGER REFERENCES users(id),
  shift_id    INTEGER,
  total_kobo  INTEGER NOT NULL,
  method      TEXT NOT NULL,
  reason      TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE refund_items (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  refund_id    INTEGER NOT NULL REFERENCES refunds(id) ON DELETE CASCADE,
  sale_item_id INTEGER NOT NULL REFERENCES sale_items(id),
  qty          REAL NOT NULL,
  amount_kobo  INTEGER NOT NULL,
  restock      INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE held_sales (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER NOT NULL REFERENCES users(id),
  label       TEXT,
  cart_json   TEXT NOT NULL,
  customer_id INTEGER,
  created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE cash_movements (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  shift_id    INTEGER REFERENCES shifts(id),
  user_id     INTEGER NOT NULL REFERENCES users(id),
  kind        TEXT NOT NULL CHECK (kind IN ('in','out')),
  amount_kobo INTEGER NOT NULL,
  reason      TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE customer_payments (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  shift_id    INTEGER,
  user_id     INTEGER NOT NULL REFERENCES users(id),
  amount_kobo INTEGER NOT NULL,
  method      TEXT NOT NULL DEFAULT 'cash',
  note        TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE expenses (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  category    TEXT NOT NULL,
  amount_kobo INTEGER NOT NULL,
  note        TEXT,
  paid_on     TEXT NOT NULL DEFAULT (date('now','localtime')),
  user_id     INTEGER,
  created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE purchase_orders (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  po_no       TEXT NOT NULL UNIQUE,
  supplier_id INTEGER REFERENCES suppliers(id) ON DELETE SET NULL,
  status      TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','ordered','partial','received','cancelled')),
  expected_on TEXT,
  note        TEXT,
  total_kobo  INTEGER NOT NULL DEFAULT 0,
  paid_kobo   INTEGER NOT NULL DEFAULT 0,
  user_id     INTEGER,
  created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  received_at TEXT
);

CREATE TABLE po_items (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  po_id        INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
  product_id   INTEGER NOT NULL REFERENCES products(id),
  qty_ordered  REAL NOT NULL,
  qty_received REAL NOT NULL DEFAULT 0,
  cost_kobo    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE stocktakes (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','applied','cancelled')),
  user_id    INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  applied_at TEXT
);

CREATE TABLE stocktake_items (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  stocktake_id INTEGER NOT NULL REFERENCES stocktakes(id) ON DELETE CASCADE,
  product_id   INTEGER NOT NULL REFERENCES products(id),
  expected_qty REAL NOT NULL,
  counted_qty  REAL,
  UNIQUE (stocktake_id, product_id)
);

CREATE TABLE notifications (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  kind       TEXT NOT NULL DEFAULT 'info',
  title      TEXT NOT NULL,
  message    TEXT,
  link       TEXT,
  dedupe_key TEXT,
  is_read    INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX idx_notif_dedupe ON notifications(dedupe_key);

CREATE TABLE audit_logs (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER,
  user_name   TEXT,
  action      TEXT NOT NULL,
  entity      TEXT,
  entity_id   INTEGER,
  description TEXT NOT NULL,
  created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX idx_audit_created ON audit_logs(created_at);
"""))
