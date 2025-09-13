# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations
from decimal import Decimal
from datetime import date, timedelta
from typing import Optional, List, Dict, Tuple
from psycopg_pool import ConnectionPool


class Database:
    def __init__(self, dsn: str) -> None:
        # autocommit so each statement is its own transaction
        self.pool = ConnectionPool(conninfo=dsn, min_size=1, max_size=5, kwargs={"autocommit": True})

    # ---------------- Accounts ----------------

    def create_account(
        self,
        institution: str,
        type_id: int,
        account_name: str,
        starting_balance: Decimal,
        interest: bool,
    ) -> int:
        """Insert into ORIGINAL accounts schema. opened/day/month/year set to today, active='YES'."""
        today = date.today()
        mon_id = today.month  # months table is 1..12
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO accounts (institution, type, acc_id, active, balance, interest, apy, opened, day, month, year)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (
                    institution,
                    type_id,
                    account_name,
                    "YES",
                    starting_balance,
                    "YES" if interest else "NO",
                    None,
                    today,
                    today.day,
                    mon_id,
                    today.year,
                ),
            )
            return int(cur.fetchone()[0])

    def sidebar_accounts(self) -> List[Tuple[str, List[Tuple[int, str, Decimal]]]]:
        """
        Return list of (institution_name, [(account_id, account_name, available_balance), ...]) grouped by institution.
        'available' = opening balance + ALL transactions (including pending).
        """
        sql = """
            SELECT a.id, a.institution, a.acc_id,
                   a.balance + COALESCE(SUM(t.amount), 0) AS available
            FROM accounts a
            LEFT JOIN transactions t ON t.acc_id = a.id
            WHERE a.active <> 'NO'
            GROUP BY a.id, a.institution, a.acc_id, a.balance
            ORDER BY a.institution, a.acc_id
        """
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()

        groups: Dict[str, List[Tuple[int, str, Decimal]]] = {}
        for acc_id, inst, name, avail in rows:
            groups.setdefault(inst, []).append((int(acc_id), str(name), Decimal(avail)))
        return [(inst, items) for inst, items in groups.items()]

    def account_header(self, account_id: int) -> Tuple[str, str, Decimal, Decimal]:
        """
        Return (institution, account_name, posted_balance, available_balance).
        posted excludes pending=1; available includes all.
        """
        sql = """
            SELECT a.institution, a.acc_id,
                   a.balance + COALESCE(SUM(CASE WHEN t.pending = 0 THEN t.amount ELSE 0 END),0) AS posted,
                   a.balance + COALESCE(SUM(t.amount),0) AS available
            FROM accounts a
            LEFT JOIN transactions t ON t.acc_id = a.id
            WHERE a.id=%s
            GROUP BY a.institution, a.acc_id, a.balance
        """
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, (account_id,))
            inst, name, posted, available = cur.fetchone()
        return str(inst), str(name), Decimal(posted), Decimal(available)

    # ---------------- Transactions ----------------

    def list_transactions(self, account_id: int) -> List[Dict]:
        """
        List transactions for an account, including lookup labels AND raw IDs for inline editing.
        """
        sql = """
            SELECT
                t.id,
                t.pending,
                t.amount,
                t.date AS occurred_on,
                t.name,
                tt.type   AS ttype,
                tm.method AS method,
                tc.cat    AS cat,
                t.type    AS type_id,
                t.method  AS method_id,
                t.cat     AS cat_id
            FROM transactions t
            LEFT JOIN trans_type   tt ON tt.id = t.type
            LEFT JOIN trans_method tm ON tm.id = t.method
            LEFT JOIN trans_cat    tc ON tc.id = t.cat
            WHERE t.acc_id = %s
            ORDER BY t.c_id DESC, t.date DESC, t.id DESC
        """
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, (account_id,))
            cols = [c.name for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def next_order_index(self, account_id: int) -> int:
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT MAX(c_id) FROM transactions WHERE acc_id=%s", (account_id,))
            maxv = cur.fetchone()[0]
            return (int(maxv) if maxv is not None else 0) + 10

    def _normalized_amount_for_type(self, amount: Decimal, type_id: int) -> Decimal:
        """
        Enforce sign based on trans_type:
          - 'Expense'  => negative
          - 'Deposit'  => positive
          - otherwise  => positive (e.g., 'Transfer')
        Users may enter any sign; we ignore it and apply rule here.
        """
        amt = abs(Decimal(amount))
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT type FROM trans_type WHERE id=%s", (type_id,))
            row = cur.fetchone()
            ttxt = (row[0] if row else "").strip().lower()
        if ttxt.startswith("expense"):
            return -amt
        elif ttxt.startswith("deposit"):
            return +amt
        else:
            return +amt

    def add_transaction(
        self,
        account_id: int,
        type_id: int,
        name: str,
        method_id: Optional[int],
        cat_id: Optional[int],
        amount: Decimal,
        occurred_on: date,
        pending: bool,
    ) -> int:
        """
        Insert a transaction. Amount sign is normalized by type (see _normalized_amount_for_type).
        Also stamps day/month/year and assigns a c_id (manual ordering key).
        """
        order_index = self.next_order_index(account_id)
        day, month, year = occurred_on.day, occurred_on.month, occurred_on.year
        pend_i = 1 if pending else 0
        amt = self._normalized_amount_for_type(amount, type_id)

        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO transactions
                    (acc_id, c_id, pending, type, name, method, cat, amount, date, day, month, year)
                VALUES
                    (%s,     %s,   %s,      %s,   %s,   %s,     %s,  %s,     %s,   %s,  %s,    %s)
                RETURNING id
                """,
                (
                    account_id,
                    order_index,
                    pend_i,
                    type_id,
                    name,
                    (method_id or 0),
                    (cat_id or 0),
                    amt,
                    occurred_on,
                    day,
                    month,
                    year,
                ),
            )
            return int(cur.fetchone()[0])

    def update_transaction(
        self,
        txn_id: int,
        account_id: int,
        *,
        type_id: int,
        name: str,
        method_id: Optional[int],
        cat_id: Optional[int],
        amount: Decimal,
        occurred_on: date,
        pending: bool,
    ) -> None:
        """
        Update a transaction in place. Applies the same sign-normalization by type as add_transaction.
        """
        day, month, year = occurred_on.day, occurred_on.month, occurred_on.year
        pend_i = 1 if pending else 0
        amt = self._normalized_amount_for_type(amount, type_id)

        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE transactions
                   SET type=%s,
                       name=%s,
                       method=%s,
                       cat=%s,
                       amount=%s,
                       date=%s,
                       day=%s,
                       month=%s,
                       year=%s,
                       pending=%s
                 WHERE id=%s AND acc_id=%s
                """,
                (
                    type_id,
                    name,
                    (method_id or 0),
                    (cat_id or 0),
                    amt,
                    occurred_on,
                    day,
                    month,
                    year,
                    pend_i,
                    txn_id,
                    account_id,
                ),
            )

    def set_txn_pending(self, txn_id: int, pending: bool) -> None:
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute("UPDATE transactions SET pending=%s WHERE id=%s", (1 if pending else 0, txn_id))

    def move_txn_up(self, account_id: int, txn_id: int) -> None:
        """
        Swap c_id with the nearest previous row (by c_id) to move the txn up.
        """
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT c_id FROM transactions WHERE id=%s AND acc_id=%s", (txn_id, account_id))
            cur_idx = cur.fetchone()[0]

            cur.execute(
                """
                SELECT id, c_id FROM transactions
                WHERE acc_id=%s AND c_id > %s
                ORDER BY c_id ASC, id ASC
                LIMIT 1
                """,
                (account_id, cur_idx),
            )


            prev = cur.fetchone()
            if prev:
                prev_id, prev_idx = prev
                cur.execute("UPDATE transactions SET c_id=%s WHERE id=%s", (prev_idx, txn_id))
                cur.execute("UPDATE transactions SET c_id=%s WHERE id=%s", (cur_idx, prev_id))

    def move_txn_down(self, account_id: int, txn_id: int) -> None:
        """
        Swap c_id with the nearest next row (by c_id) to move the txn down.
        """
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT c_id FROM transactions WHERE id=%s AND acc_id=%s", (txn_id, account_id))
            cur_idx = cur.fetchone()[0]

            cur.execute(
                """
                SELECT id, c_id FROM transactions
                WHERE acc_id=%s AND c_id < %s
                ORDER BY c_id DESC, id DESC
                LIMIT 1
                """,
                (account_id, cur_idx),
            )

            nxt = cur.fetchone()
            if nxt:
                next_id, next_idx = nxt
                cur.execute("UPDATE transactions SET c_id=%s WHERE id=%s", (next_idx, txn_id))
                cur.execute("UPDATE transactions SET c_id=%s WHERE id=%s", (cur_idx, next_id))

    # ========= PAY SCHEDULE (pay_schedule) =========

    def upsert_pay_schedule(self, *, anchor_date: date) -> None:
        """Frequency is fixed to 'biweekly' per your migration; set/replace anchor_date."""
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO pay_schedule (id, frequency, anchor_date)
                VALUES (1, 'biweekly', %s)
                ON CONFLICT (id) DO UPDATE SET anchor_date = EXCLUDED.anchor_date
            """, (anchor_date,))

    def get_pay_window(self, today: date | None = None) -> tuple[date, date]:
        """
        Return (window_start, window_end) for the 14-day pay window that CONTAINS
        "today" (inclusive), based on the known bi-weekly anchor payday.

        - Includes the actual payday (window_start = payday)
        - Always 14 days long: [start, start+13]
        - If payday slips, this still returns the prior window covering today.
        """
        today = today or date.today()
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT anchor_date FROM pay_schedule WHERE id=1")
            row = cur.fetchone()
            anchor = row[0] if row else today

        step = 14
        # Compute the payday at or before today
        days = (today - anchor).days
        k = days // step  # floor division works for negatives too
        start = anchor + timedelta(days=step * k)
        end = start + timedelta(days=13)
        # If today somehow falls before the very first anchor (k<0), start is previous cycle
        return start, end

    # ========= BILLS (bills, bill_payments) =========

    def add_bill(
        self,
        *,
        payee: str,
        amount_due: Decimal,
        frequency: str,          # 'monthly' | 'yearly'
        due_day: int | None,     # for monthly
        due_month: int | None,   # for yearly (1..12)
        due_dom: int | None,     # for yearly (1..31)
        account_id: int | None,
        total_debt: Decimal | None = None,
        notes: str = "",
    ) -> int:
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO bills (payee, frequency, amount_due, total_debt, account_id,
                                due_day, due_month, due_dom, active, notes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s, TRUE, %s)
                RETURNING id
            """, (payee, frequency.lower(), amount_due, total_debt or Decimal("0"),
                account_id, due_day, due_month, due_dom, notes))
            return int(cur.fetchone()[0])

    def list_bills(self, *, active_only: bool = True) -> list[dict]:
        sql = """
            SELECT b.id, b.payee, b.frequency, b.amount_due, b.total_debt, b.account_id,
                b.due_day, b.due_month, b.due_dom, b.active, b.notes,
                a.acc_id AS account_name
            FROM bills b
            LEFT JOIN accounts a ON a.id = b.account_id
            WHERE (NOT %s) OR (b.active = TRUE)        -- ✅ if active_only True -> filter active; else -> all
            ORDER BY b.payee
        """
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, (active_only,))
            cols = [c.name for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


    def upcoming_bills(self, *, window_start: date, window_end: date) -> list[dict]:
        all_bills = self.list_bills(active_only=True)
        out: list[dict] = []
        for b in all_bills:
            freq = (b["frequency"] or "monthly").lower()
            if freq == "monthly" and b["due_day"]:
                due = _next_monthly_due(int(b["due_day"]), window_start)
            elif freq == "yearly" and b["due_month"] and b["due_dom"]:
                due = _next_yearly_due(int(b["due_month"]), int(b["due_dom"]), window_start)
            else:
                continue
            if window_start <= due <= window_end:
                paid = self._is_bill_paid(bill_id=int(b["id"]), due_date=due)
                ignored = self._is_bill_ignored(bill_id=int(b["id"]), due_date=due)
                x = dict(b)
                x["next_due"] = due
                x["paid"] = paid
                x["ignored"] = ignored
                out.append(x)
        out.sort(key=lambda r: (r["next_due"], r["payee"].lower()))
        return out

    def _is_bill_paid(self, *, bill_id: int, due_date: date) -> bool:
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM bill_payments WHERE bill_id=%s AND due_date=%s LIMIT 1",
                        (bill_id, due_date))
            return cur.fetchone() is not None

    def mark_bill_paid(self, *, bill_id: int, due_date: date) -> None:
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT payee, amount_due, account_id FROM bills WHERE id=%s", (bill_id,))
            row = cur.fetchone()
            if not row: return
            payee, amount_due, account_id = row

        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bill_payments (bill_id, due_date, amount, paid_at, ignored)
                VALUES (%s, %s, %s, NOW(), FALSE)
                ON CONFLICT (bill_id, due_date) DO UPDATE
                SET amount = EXCLUDED.amount,
                    paid_at = NOW(),
                    ignored = FALSE
                """,
                (bill_id, due_date, amount_due),
            )

        # Resolve lookups (best-effort)
        expense_id = self._lookup_id("SELECT id FROM trans_type WHERE LOWER(type) LIKE 'expense%'", default_val=1)
        method_id  = self._lookup_by_text("SELECT id FROM trans_method WHERE LOWER(method)=LOWER(%s)", "N/A")
        cat_id     = self._lookup_by_text("SELECT id FROM trans_cat WHERE LOWER(cat)=LOWER(%s)", "Bills")

        # Create transaction (unsigned; DB layer should enforce sign by type)
        self.add_transaction(
            account_id=int(account_id),
            type_id=int(expense_id),
            name=str(payee),
            method_id=method_id,
            cat_id=cat_id,
            amount=Decimal(amount_due),
            occurred_on=due_date,
            pending=False,
        )

    def _lookup_id(self, sql: str, default_val: int | None = None) -> int | None:
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
            return int(row[0]) if row else default_val

    def _lookup_by_text(self, sql: str, value: str) -> int | None:
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(sql, (value,))
            row = cur.fetchone()
            return int(row[0]) if row else None

    def _is_bill_ignored(self, *, bill_id: int, due_date: date) -> bool:
        """Return True if this specific bill occurrence is marked ignored."""
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM bill_payments WHERE bill_id=%s AND due_date=%s AND ignored=TRUE LIMIT 1",
                (bill_id, due_date),
            )
            return cur.fetchone() is not None

    def set_bill_ignored(self, *, bill_id: int, due_date: date, ignored: bool) -> None:
        """Upsert an ignore flag for a specific bill occurrence (per bill & due_date)."""
        with self.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bill_payments (bill_id, due_date, amount, ignored)
                VALUES (%s, %s, 0, %s)
                ON CONFLICT (bill_id, due_date) DO UPDATE
                SET ignored = EXCLUDED.ignored
                """,
                (bill_id, due_date, bool(ignored)),
            )

def _last_dom(y: int, m: int) -> int:
    if m in (1, 3, 5, 7, 8, 10, 12):
        return 31
    if m in (4, 6, 9, 11):
        return 30
    leap = (y % 400 == 0) or (y % 4 == 0 and y % 100 != 0)
    return 29 if leap else 28

def _next_monthly_due(dom: int, from_date: date) -> date:
    dom = max(1, min(31, int(dom)))
    if from_date.day <= dom:
        return date(from_date.year, from_date.month, min(dom, _last_dom(from_date.year, from_date.month)))
    # next month
    ny = from_date.year + (1 if from_date.month == 12 else 0)
    nm = 1 if from_date.month == 12 else from_date.month + 1
    return date(ny, nm, min(dom, _last_dom(ny, nm)))

def _next_yearly_due(month: int, dom: int, from_date: date) -> date:
    month = max(1, min(12, int(month)))
    dom = max(1, min(31, int(dom)))
    try_this = date(from_date.year, month, min(dom, _last_dom(from_date.year, month)))
    if try_this >= from_date:
        return try_this
    return date(from_date.year + 1, month, min(dom, _last_dom(from_date.year + 1, month)))
