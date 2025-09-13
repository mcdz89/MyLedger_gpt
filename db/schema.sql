# SPDX-License-Identifier: Apache-2.0

-- db/schema.sql
-- One-shot schema: Original tables + Bills (+ ignore) + seeds
-- Run with:  psql -v ON_ERROR_STOP=1 "$DATABASE_URL" -f db/schema.sql

BEGIN;

------------------------------------------------------------
-- LOOKUPS
------------------------------------------------------------
CREATE TABLE acc_type (
  id   SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  type VARCHAR(45) NOT NULL UNIQUE
);

CREATE TABLE acc_apy (
  id     SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  acc_id SMALLINT NOT NULL,
  rate   NUMERIC(18,9)
);

CREATE TABLE trans_method (
  id     SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  method VARCHAR(10) NOT NULL UNIQUE
);

CREATE TABLE trans_cat (
  id  SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  cat VARCHAR(15) NOT NULL UNIQUE
);

CREATE TABLE trans_type (
  id   SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  type VARCHAR(25) NOT NULL UNIQUE
);

CREATE TABLE months (
  id    SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  month VARCHAR(3) NOT NULL UNIQUE
);

------------------------------------------------------------
-- ORIGINAL ACCOUNTS / TRANSACTIONS
------------------------------------------------------------
CREATE TABLE accounts (
  id          INTEGER  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  institution VARCHAR(100) NOT NULL,
  type        INTEGER NOT NULL REFERENCES acc_type(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  acc_id      VARCHAR(50) NOT NULL,             -- user-visible account name
  active      VARCHAR(3) NOT NULL,              -- 'YES' / 'NO'
  balance     NUMERIC(18,9) NOT NULL,
  interest    VARCHAR(3) NOT NULL,              -- 'YES' / 'NO'
  apy         INTEGER,
  opened      DATE NOT NULL DEFAULT DATE '1970-01-01',
  day         SMALLINT NOT NULL DEFAULT 0,
  month       SMALLINT NOT NULL DEFAULT 1 REFERENCES months(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  year        INTEGER NOT NULL DEFAULT 1970
);

CREATE TABLE transactions (
  id       INTEGER  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  c_id     INTEGER  NOT NULL DEFAULT 0,         -- manual sort key
  acc_id   INTEGER  NOT NULL REFERENCES accounts(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  pending  SMALLINT NOT NULL DEFAULT 1 CHECK (pending IN (0,1)),  -- 1=pending, 0=cleared
  type     SMALLINT NOT NULL REFERENCES trans_type(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  name     VARCHAR(50) NOT NULL,
  method   SMALLINT NOT NULL REFERENCES trans_method(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  cat      SMALLINT NOT NULL REFERENCES trans_cat(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  amount   NUMERIC(18,9) NOT NULL,
  balance  NUMERIC(18,9) NOT NULL DEFAULT 0.0,
  date     DATE NOT NULL DEFAULT DATE '1970-01-01',
  day      SMALLINT NOT NULL DEFAULT 0,
  month    SMALLINT NOT NULL DEFAULT 0,
  year     INTEGER NOT NULL DEFAULT 0
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS idx_accounts_active           ON accounts(active);
CREATE INDEX IF NOT EXISTS idx_txn_acc_cid               ON transactions(acc_id, c_id);
CREATE INDEX IF NOT EXISTS idx_txn_acc_date              ON transactions(acc_id, date, id);
CREATE INDEX IF NOT EXISTS idx_txn_acc_pending           ON transactions(acc_id, pending);

------------------------------------------------------------
-- SETTINGS
------------------------------------------------------------
CREATE TABLE settings (
  dateStamp  TIMESTAMP NOT NULL,
  dateformat TEXT NOT NULL
);

------------------------------------------------------------
-- BILLS / PAY SCHEDULE
------------------------------------------------------------
-- Singleton pay schedule (biweekly for now)
CREATE TABLE pay_schedule (
  id          SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  frequency   VARCHAR(10) NOT NULL CHECK (frequency IN ('biweekly')),
  anchor_date DATE NOT NULL
);

-- Bills master
CREATE TABLE bills (
  id           SERIAL PRIMARY KEY,
  payee        VARCHAR(100) NOT NULL,
  frequency    VARCHAR(10)  NOT NULL CHECK (frequency IN ('monthly','yearly')),
  amount_due   NUMERIC(18,9) NOT NULL,
  total_debt   NUMERIC(18,9) NOT NULL DEFAULT 0.0,
  account_id   INTEGER REFERENCES accounts(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  -- monthly:
  due_day      SMALLINT,
  -- yearly:
  due_month    SMALLINT,
  due_dom      SMALLINT,
  active       BOOLEAN NOT NULL DEFAULT TRUE,
  notes        TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT bills_monthly_or_yearly CHECK (
    (frequency='monthly' AND due_day IS NOT NULL AND due_month IS NULL AND due_dom IS NULL)
    OR
    (frequency='yearly'  AND due_day IS NULL AND due_month IS NOT NULL AND due_dom IS NOT NULL)
  )
);

-- Keep updated_at fresh
CREATE OR REPLACE FUNCTION trg_touch_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at := NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS bills_touch_updated ON bills;
CREATE TRIGGER bills_touch_updated
BEFORE UPDATE ON bills
FOR EACH ROW
EXECUTE FUNCTION trg_touch_updated_at();

-- Each occurrence/payment
CREATE TABLE bill_payments (
  id         SERIAL PRIMARY KEY,
  bill_id    INTEGER NOT NULL REFERENCES bills(id) ON DELETE CASCADE,
  due_date   DATE NOT NULL,
  amount     NUMERIC(18,9) NOT NULL,
  paid_at    TIMESTAMPTZ,
  ignored    BOOLEAN NOT NULL DEFAULT FALSE,
  UNIQUE (bill_id, due_date)
);

-- Useful indexes
CREATE INDEX IF NOT EXISTS idx_bills_active           ON bills(active);
CREATE INDEX IF NOT EXISTS idx_bills_account          ON bills(account_id);
CREATE INDEX IF NOT EXISTS idx_bill_payments_due      ON bill_payments(due_date);
CREATE INDEX IF NOT EXISTS idx_bill_payments_bill_due ON bill_payments(bill_id, due_date);
CREATE INDEX IF NOT EXISTS idx_bill_payments_ignored  ON bill_payments(ignored);

------------------------------------------------------------
-- SEED DATA (idempotent)
------------------------------------------------------------
INSERT INTO settings(dateStamp, dateformat)
VALUES (CURRENT_TIMESTAMP, 'D j M Y, G:ia');

INSERT INTO acc_type(type) VALUES ('Checking') ON CONFLICT DO NOTHING;
INSERT INTO acc_type(type) VALUES ('Savings')  ON CONFLICT DO NOTHING;

INSERT INTO trans_type(type) VALUES ('Expense')  ON CONFLICT DO NOTHING;
INSERT INTO trans_type(type) VALUES ('Deposit')  ON CONFLICT DO NOTHING;
INSERT INTO trans_type(type) VALUES ('Transfer') ON CONFLICT DO NOTHING;

INSERT INTO trans_method(method) VALUES
  ('Debit'), ('Credit'), ('Check'), ('Online'), ('Transfer'), ('N/A')
ON CONFLICT DO NOTHING;

INSERT INTO trans_cat(cat) VALUES
 ('Advance'), ('Cash'), ('Check'), ('Interest'), ('Paycheck'), ('Rebate'), ('Refund'),
 ('Transfer [EXT]'), ('ATM'), ('Automotive'), ('Bills'), ('Clothing-Shoes'), ('Dining'),
 ('Education'), ('Electronics'), ('Entertainment'), ('Fee'), ('Gas'), ('Groceries'),
 ('Hobby'), ('Medical'), ('Misc'), ('Self-Care'), ('Services'), ('Taxes'), ('Transfer')
ON CONFLICT DO NOTHING;

INSERT INTO months(month) VALUES
 ('Jan'),('Feb'),('Mar'),('Apr'),('May'),('Jun'),
 ('Jul'),('Aug'),('Sep'),('Oct'),('Nov'),('Dec')
ON CONFLICT DO NOTHING;

-- Ensure a default pay schedule exists (biweekly, anchor today if absent)
INSERT INTO pay_schedule (id, frequency, anchor_date)
VALUES (1, 'biweekly', CURRENT_DATE)
ON CONFLICT (id) DO NOTHING;

COMMIT;
