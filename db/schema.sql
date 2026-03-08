-- SPDX-License-Identifier: Apache-2.0

PRAGMA foreign_keys = ON;

------------------------------------------------------------
-- LOOKUPS
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS acc_type (
  id   INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS acc_apy (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  acc_id INTEGER NOT NULL,
  rate   NUMERIC
);

CREATE TABLE IF NOT EXISTS trans_method (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  method TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS trans_cat (
  id  INTEGER PRIMARY KEY AUTOINCREMENT,
  cat TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS trans_type (
  id   INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS months (
  id    INTEGER PRIMARY KEY AUTOINCREMENT,
  month TEXT NOT NULL UNIQUE
);

------------------------------------------------------------
-- ORIGINAL ACCOUNTS / TRANSACTIONS
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounts (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  institution TEXT NOT NULL,
  type        INTEGER NOT NULL REFERENCES acc_type(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  acc_id      TEXT NOT NULL,
  active      TEXT NOT NULL,
  balance     NUMERIC NOT NULL,
  interest    TEXT NOT NULL,
  apy         INTEGER,
  opened      DATE NOT NULL DEFAULT '1970-01-01',
  day         INTEGER NOT NULL DEFAULT 0,
  month       INTEGER NOT NULL DEFAULT 1 REFERENCES months(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  year        INTEGER NOT NULL DEFAULT 1970
);

CREATE TABLE IF NOT EXISTS transactions (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  c_id     INTEGER NOT NULL DEFAULT 0,
  acc_id   INTEGER NOT NULL REFERENCES accounts(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  pending  INTEGER NOT NULL DEFAULT 1 CHECK (pending IN (0,1)),
  type     INTEGER NOT NULL REFERENCES trans_type(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  name     TEXT NOT NULL,
  method   INTEGER NOT NULL REFERENCES trans_method(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  cat      INTEGER NOT NULL REFERENCES trans_cat(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  amount   NUMERIC NOT NULL,
  balance  NUMERIC NOT NULL DEFAULT 0.0,
  date     DATE NOT NULL DEFAULT '1970-01-01',
  day      INTEGER NOT NULL DEFAULT 0,
  month    INTEGER NOT NULL DEFAULT 0,
  year     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_accounts_active           ON accounts(active);
CREATE INDEX IF NOT EXISTS idx_txn_acc_cid               ON transactions(acc_id, c_id);
CREATE INDEX IF NOT EXISTS idx_txn_acc_date              ON transactions(acc_id, date, id);
CREATE INDEX IF NOT EXISTS idx_txn_acc_pending           ON transactions(acc_id, pending);

------------------------------------------------------------
-- SETTINGS
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS settings (
  dateStamp  TEXT NOT NULL,
  dateformat TEXT NOT NULL
);

------------------------------------------------------------
-- BILLS / PAY SCHEDULE
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pay_schedule (
  id          INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  frequency   TEXT NOT NULL CHECK (frequency IN ('biweekly')),
  anchor_date DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS bills (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  payee        TEXT NOT NULL,
  frequency    TEXT NOT NULL CHECK (frequency IN ('monthly','yearly')),
  amount_due   NUMERIC NOT NULL,
  total_debt   NUMERIC NOT NULL DEFAULT 0.0,
  account_id   INTEGER REFERENCES accounts(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  due_day      INTEGER,
  due_month    INTEGER,
  due_dom      INTEGER,
  active       INTEGER NOT NULL DEFAULT 1,
  notes        TEXT,
  created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT bills_monthly_or_yearly CHECK (
    (frequency='monthly' AND due_day IS NOT NULL AND due_month IS NULL AND due_dom IS NULL)
    OR
    (frequency='yearly'  AND due_day IS NULL AND due_month IS NOT NULL AND due_dom IS NOT NULL)
  )
);

CREATE TRIGGER IF NOT EXISTS bills_touch_updated
AFTER UPDATE ON bills
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
  UPDATE bills SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

CREATE TABLE IF NOT EXISTS bill_payments (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  bill_id    INTEGER NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
  due_date   DATE NOT NULL,
  amount     NUMERIC NOT NULL,
  paid_at    TEXT,
  ignored    INTEGER NOT NULL DEFAULT 0,
  UNIQUE (bill_id, due_date)
);

CREATE INDEX IF NOT EXISTS idx_bills_active           ON bills(active);
CREATE INDEX IF NOT EXISTS idx_bills_account          ON bills(account_id);
CREATE INDEX IF NOT EXISTS idx_bill_payments_due      ON bill_payments(due_date);
CREATE INDEX IF NOT EXISTS idx_bill_payments_bill_due ON bill_payments(bill_id, due_date);
CREATE INDEX IF NOT EXISTS idx_bill_payments_ignored  ON bill_payments(ignored);

------------------------------------------------------------
-- SEED DATA (idempotent)
------------------------------------------------------------
INSERT OR IGNORE INTO settings(dateStamp, dateformat)
VALUES (CURRENT_TIMESTAMP, 'D j M Y, G:ia');

INSERT OR IGNORE INTO acc_type(type) VALUES ('Checking');
INSERT OR IGNORE INTO acc_type(type) VALUES ('Savings');

INSERT OR IGNORE INTO trans_type(type) VALUES ('Expense');
INSERT OR IGNORE INTO trans_type(type) VALUES ('Deposit');
INSERT OR IGNORE INTO trans_type(type) VALUES ('Transfer');

INSERT OR IGNORE INTO trans_method(method) VALUES
  ('Debit'), ('Credit'), ('Check'), ('Online'), ('Transfer'), ('N/A');

INSERT OR IGNORE INTO trans_cat(cat) VALUES
 ('Advance'), ('Cash'), ('Check'), ('Interest'), ('Paycheck'), ('Rebate'), ('Refund'),
 ('Transfer [EXT]'), ('ATM'), ('Automotive'), ('Bills'), ('Clothing-Shoes'), ('Dining'),
 ('Education'), ('Electronics'), ('Entertainment'), ('Fee'), ('Gas'), ('Groceries'),
 ('Hobby'), ('Medical'), ('Misc'), ('Self-Care'), ('Services'), ('Taxes'), ('Transfer');

INSERT OR IGNORE INTO months(month) VALUES
 ('Jan'),('Feb'),('Mar'),('Apr'),('May'),('Jun'),
 ('Jul'),('Aug'),('Sep'),('Oct'),('Nov'),('Dec');

INSERT OR IGNORE INTO pay_schedule (id, frequency, anchor_date)
VALUES (1, 'biweekly', DATE('now'));
