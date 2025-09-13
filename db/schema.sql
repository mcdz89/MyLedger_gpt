BEGIN;

-- Drop (clean reset)
DROP VIEW IF EXISTS account_balances CASCADE;
DROP TABLE IF EXISTS transactions CASCADE;
DROP TABLE IF EXISTS accounts CASCADE;
DROP TABLE IF EXISTS acc_apy CASCADE;
DROP TABLE IF EXISTS acc_type CASCADE;
DROP TABLE IF EXISTS trans_method CASCADE;
DROP TABLE IF EXISTS trans_cat CASCADE;
DROP TABLE IF EXISTS trans_type CASCADE;
DROP TABLE IF EXISTS months CASCADE;
DROP TABLE IF EXISTS settings CASCADE;

-- Lookups
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

-- Accounts (original design)
CREATE TABLE accounts (
  id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  institution VARCHAR(100) NOT NULL,
  type        INTEGER NOT NULL REFERENCES acc_type(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  acc_id      VARCHAR(50) NOT NULL,  -- we use this as the user-visible account name
  active      VARCHAR(3) NOT NULL,   -- 'YES'/'NO'
  balance     NUMERIC(18,9) NOT NULL,
  interest    VARCHAR(3) NOT NULL,   -- 'YES'/'NO'
  apy         INTEGER,
  opened      DATE NOT NULL DEFAULT DATE '1970-01-01',
  day         SMALLINT NOT NULL DEFAULT 0,
  month       SMALLINT NOT NULL DEFAULT 1 REFERENCES months(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  year        INTEGER NOT NULL DEFAULT 1970
);

-- Transactions (original layout)
CREATE TABLE transactions (
  id       INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  c_id     INTEGER NOT NULL DEFAULT 0, -- we will use as manual sort key
  acc_id   INTEGER NOT NULL REFERENCES accounts(id) ON UPDATE CASCADE ON DELETE RESTRICT,
  pending  SMALLINT NOT NULL DEFAULT 1,  -- 1=pending, 0=cleared
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

-- Settings
CREATE TABLE settings (
  dateStamp  TIMESTAMP NOT NULL,
  dateformat TEXT NOT NULL
);

-- Seed lookups
INSERT INTO settings(dateStamp, dateformat) VALUES (CURRENT_TIMESTAMP, 'D j M Y, G:ia');
INSERT INTO acc_type(type) VALUES('Checking') ON CONFLICT DO NOTHING;
INSERT INTO acc_type(type) VALUES('Savings')  ON CONFLICT DO NOTHING;
INSERT INTO trans_type(type) VALUES('Expense') ON CONFLICT DO NOTHING;
INSERT INTO trans_type(type) VALUES('Deposit') ON CONFLICT DO NOTHING;
INSERT INTO trans_type(type) VALUES('Transfer') ON CONFLICT DO NOTHING;
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
 ('Jan'),('Feb'),('Mar'),('Apr'),('May'),('Jun'),('Jul'),('Aug'),('Sep'),('Oct'),('Nov'),('Dec')
ON CONFLICT DO NOTHING;

COMMIT;
