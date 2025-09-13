# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations
from gi.repository import Gtk, Adw, GLib
from decimal import Decimal
from datetime import date


class AddAccountDialog(Gtk.Dialog):
    def __init__(self, parent: Adw.ApplicationWindow, db, on_created):
        super().__init__(title="Add Account", transient_for=parent, modal=True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(12); box.set_margin_bottom(12)
        box.set_margin_start(12); box.set_margin_end(12)
        self.set_child(box)

        self.inst = Gtk.Entry(placeholder_text="Institution label")
        self.name_e = Gtk.Entry(placeholder_text="Account name")
        self.type_c = Gtk.ComboBoxText()
        self.start = Gtk.Entry(placeholder_text="Starting balance, e.g., 1000.00")
        self.int_chk = Gtk.CheckButton(label="This account earns interest")

        for w in (self.inst, self.name_e, self.type_c, self.start, self.int_chk):
            box.append(w)

        # fill acc_type (idempotent)
        with db.pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, type FROM acc_type ORDER BY id")
            rows = cur.fetchall()
            if not rows:
                cur.execute("INSERT INTO acc_type(type) VALUES ('Checking'),('Savings')")
                cur.execute("SELECT id, type FROM acc_type ORDER BY id")
                rows = cur.fetchall()
        for id_, label in rows:
            self.type_c.append(str(id_), str(label))
        self.type_c.set_active(0)

        # actions
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        cancel_btn = Gtk.Button.new_with_label("Cancel")
        submit_btn = Gtk.Button.new_with_label("Add Account")
        submit_btn.get_style_context().add_class("suggested-action")
        cancel_btn.connect("clicked", lambda *_: self.response(Gtk.ResponseType.CANCEL))
        submit_btn.connect("clicked", lambda *_: self.response(Gtk.ResponseType.OK))
        actions.append(cancel_btn); actions.append(submit_btn)
        box.append(actions)

        # Enter to submit
        for e in (self.inst, self.name_e, self.start):
            e.connect("activate", lambda *_: self.response(Gtk.ResponseType.OK))

        self.connect("response", self._on_response, db, on_created)

    def _on_response(self, _dialog, resp, db, on_created):
        if resp == Gtk.ResponseType.OK:
            inst = self.inst.get_text().strip()
            name = self.name_e.get_text().strip()
            type_id = int(self.type_c.get_active_id() or 1)
            try:
                start = Decimal(self.start.get_text() or "0")
            except Exception:
                start = Decimal("0")
            if inst and name:
                db.create_account(inst, type_id, name, start, self.int_chk.get_active())
                on_created()
        self.close()


class AddTransactionDialog(Gtk.Dialog):
    def __init__(self, parent: Adw.ApplicationWindow, db, account_id: int, on_created):
        super().__init__(title="Add Transaction", transient_for=parent, modal=True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(12); box.set_margin_bottom(12)
        box.set_margin_start(12); box.set_margin_end(12)
        self.set_child(box)

        # description + amount (unsigned; sign normalized by DB based on type)
        self.name_e = Gtk.Entry(placeholder_text="Description")
        self.amount_e = Gtk.Entry(placeholder_text="Amount (no sign)")
        box.append(self.name_e); box.append(self.amount_e)

        # date row with calendar popover
        date_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.date_e = Gtk.Entry(placeholder_text="YYYY-MM-DD (optional)")
        self.date_e.set_hexpand(True)
        cal_btn = Gtk.MenuButton(icon_name="calendar-symbolic")
        pop = Gtk.Popover()
        cal = Gtk.Calendar()
        pop.set_child(cal)
        cal_btn.set_popover(pop)

        def _set_date_from_calendar(_cal):
            # Gtk.Calendar on GTK4 returns GLib.DateTime
            dt: GLib.DateTime = cal.get_date()
            y = int(dt.get_year()); m = int(dt.get_month()); d = int(dt.get_day_of_month())
            self.date_e.set_text(f"{y:04d}-{m:02d}-{d:02d}")
            pop.popdown()

        cal.connect("day-selected", _set_date_from_calendar)
        date_row.append(self.date_e); date_row.append(cal_btn)
        box.append(date_row)

        # plain ComboBoxText pickers (no search)
        self.type_c   = Gtk.ComboBoxText()
        self.method_c = Gtk.ComboBoxText()
        self.cat_c    = Gtk.ComboBoxText()
        for w in (self.type_c, self.method_c, self.cat_c):
            box.append(w)

        # populate lookups
        with db.pool.connection() as conn, conn.cursor() as cur:
            for sql, combo in [
                ("SELECT id, type   FROM trans_type   ORDER BY id", self.type_c),
                ("SELECT id, method FROM trans_method ORDER BY id", self.method_c),
                ("SELECT id, cat    FROM trans_cat    ORDER BY id", self.cat_c),
            ]:
                combo.remove_all()
                cur.execute(sql)
                for id_, lbl in cur.fetchall():
                    combo.append(str(id_), str(lbl))
        self.type_c.set_active(0); self.method_c.set_active(0); self.cat_c.set_active(0)

        # pending toggle
        self.pending_c = Gtk.CheckButton(label="Pending")
        self.pending_c.set_active(True)
        box.append(self.pending_c)

        # actions
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        cancel_btn = Gtk.Button.new_with_label("Cancel")
        submit_btn = Gtk.Button.new_with_label("Add Transaction")
        submit_btn.get_style_context().add_class("suggested-action")
        cancel_btn.connect("clicked", lambda *_: self.response(Gtk.ResponseType.CANCEL))
        submit_btn.connect("clicked", lambda *_: self.response(Gtk.ResponseType.OK))
        actions.append(cancel_btn); actions.append(submit_btn)
        box.append(actions)

        # Enter to submit
        for e in (self.name_e, self.amount_e, self.date_e):
            e.connect("activate", lambda *_: self.response(Gtk.ResponseType.OK))

        self.connect("response", self._on_response, db, account_id, on_created)

    def _on_response(self, _dialog, resp, db, account_id: int, on_created):
        if resp == Gtk.ResponseType.OK:
            name = self.name_e.get_text().strip()
            if not name:
                self.close(); return
            # amount as unsigned; DB layer will normalize sign based on type
            try:
                amount = Decimal(self.amount_e.get_text() or "0")
            except Exception:
                amount = Decimal("0")

            when_s = self.date_e.get_text().strip()
            try:
                y, m, d = [int(p) for p in when_s.split("-")]
                when = date(y, m, d)
            except Exception:
                when = date.today()

            type_id   = int(self.type_c.get_active_id() or 1)
            method_id = int(self.method_c.get_active_id()) if self.method_c.get_active_id() else None
            cat_id    = int(self.cat_c.get_active_id())    if self.cat_c.get_active_id()    else None

            db.add_transaction(
                account_id=account_id,
                type_id=type_id,
                name=name,
                method_id=method_id,
                cat_id=cat_id,
                amount=amount,            # unsigned; DB normalizes sign
                occurred_on=when,
                pending=self.pending_c.get_active(),
            )
            on_created()
        self.close()
        
class AddBillDialog(Gtk.Dialog):
    def __init__(self, parent: Adw.ApplicationWindow, db, on_created):
        super().__init__(title="Add Bill", transient_for=parent, modal=True)
        self.db = db

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(12); box.set_margin_bottom(12)
        box.set_margin_start(12); box.set_margin_end(12)
        self.set_child(box)

        # Fields
        self.payee = Gtk.Entry(placeholder_text="Payee")
        self.amount = Gtk.Entry(placeholder_text="Amount due (e.g., 120.00)")
        self.total_debt = Gtk.Entry(placeholder_text="Total debt (optional)")
        self.freq = Gtk.ComboBoxText()
        self.freq.append("monthly", "Monthly")
        self.freq.append("yearly", "Yearly")
        self.freq.set_active_id("monthly")

        self.due_day = Gtk.SpinButton.new_with_range(1, 31, 1)     # monthly
        self.due_day.set_value(1)
        self.due_month = Gtk.SpinButton.new_with_range(1, 12, 1)   # yearly
        self.due_month.set_value(1)
        self.due_dom = Gtk.SpinButton.new_with_range(1, 31, 1)     # yearly
        self.due_dom.set_value(1)

        self.account = Gtk.ComboBoxText()
        with db.pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, acc_id FROM accounts WHERE active <> 'NO' ORDER BY institution, acc_id")
            for i, n in cur.fetchall():
                self.account.append(str(i), str(n))
        if self.account.get_active_id() is None:
            self.account.set_active(0)

        self.notes = Gtk.Entry(placeholder_text="Notes (optional)")

        # Layout grid
        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        r = 0
        def row(lbl, w):
            nonlocal r
            grid.attach(Gtk.Label(label=lbl, xalign=0), 0, r, 1, 1)
            grid.attach(w, 1, r, 1, 1)
            r += 1

        row("Payee", self.payee)
        row("Amount due", self.amount)
        row("Total debt", self.total_debt)
        row("Frequency", self.freq)
        row("Monthly: Day of month", self.due_day)
        row("Yearly: Month", self.due_month)
        row("Yearly: Day", self.due_dom)
        row("Default account", self.account)
        row("Notes", self.notes)
        box.append(grid)

        # Enable/disable date fields based on frequency
        def toggle_fields(*_):
            is_monthly = (self.freq.get_active_id() or "monthly") == "monthly"
            self.due_day.set_sensitive(is_monthly)
            self.due_month.set_sensitive(not is_monthly)
            self.due_dom.set_sensitive(not is_monthly)
        self.freq.connect("changed", toggle_fields)
        toggle_fields()

        # Actions
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        cancel = Gtk.Button.new_with_label("Cancel")
        ok = Gtk.Button.new_with_label("Add Bill")
        ok.get_style_context().add_class("suggested-action")
        cancel.connect("clicked", lambda *_: self.response(Gtk.ResponseType.CANCEL))
        ok.connect("clicked", lambda *_: self.response(Gtk.ResponseType.OK))
        actions.append(cancel); actions.append(ok)
        box.append(actions)

        self.connect("response", self._on_resp, on_created)

    def _on_resp(self, _d, resp, on_created):
        if resp != Gtk.ResponseType.OK:
            self.close(); return

        payee = self.payee.get_text().strip()
        if not payee:
            self.close(); return

        try:
            amount = Decimal(self.amount.get_text())
        except Exception:
            amount = Decimal("0")

        try:
            td = Decimal(self.total_debt.get_text() or "0")
        except Exception:
            td = Decimal("0")

        freq = (self.freq.get_active_id() or "monthly")
        due_day   = int(self.due_day.get_value())   if freq == "monthly" else None
        due_month = int(self.due_month.get_value()) if freq == "yearly"  else None
        due_dom   = int(self.due_dom.get_value())   if freq == "yearly"  else None
        acc_id    = int(self.account.get_active_id()) if self.account.get_active_id() else None

        self.db.add_bill(
            payee=payee,
            amount_due=amount,
            total_debt=td,
            frequency=freq,
            due_day=due_day,
            due_month=due_month,
            due_dom=due_dom,
            account_id=acc_id,
            notes=self.notes.get_text().strip(),
        )
        on_created()
        self.close()


class SetPayScheduleDialog(Gtk.Dialog):
    def __init__(self, parent: Adw.ApplicationWindow, db, on_saved):
        super().__init__(title="Pay Schedule", transient_for=parent, modal=True)
        self.db = db

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(12); box.set_margin_bottom(12)
        box.set_margin_start(12); box.set_margin_end(12)
        self.set_child(box)

        # Frequency is fixed to biweekly per your migration
        freq_lbl = Gtk.Label(label="Frequency: Bi-weekly (fixed)", xalign=0)

        # Anchor payday with calendar picker
        self.anchor = Gtk.Entry(placeholder_text="Anchor payday (YYYY-MM-DD)")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.append(self.anchor)
        mb = Gtk.MenuButton(icon_name="calendar-symbolic")
        pop = Gtk.Popover()
        cal = Gtk.Calendar()
        pop.set_child(cal)
        mb.set_popover(pop)

        def pick(_c):
            dt: GLib.DateTime = cal.get_date()
            self.anchor.set_text(f"{dt.get_year():04d}-{dt.get_month():02d}-{dt.get_day_of_month():02d}")
            pop.popdown()

        cal.connect("day-selected", pick)
        row.append(mb)

        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        grid.attach(freq_lbl, 0, 0, 2, 1)
        grid.attach(Gtk.Label(label="Anchor payday", xalign=0), 0, 1, 1, 1)
        grid.attach(row, 1, 1, 1, 1)
        box.append(grid)

        # Actions
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        cancel = Gtk.Button.new_with_label("Cancel")
        ok = Gtk.Button.new_with_label("Save")
        ok.get_style_context().add_class("suggested-action")
        cancel.connect("clicked", lambda *_: self.response(Gtk.ResponseType.CANCEL))
        ok.connect("clicked", lambda *_: self.response(Gtk.ResponseType.OK))
        actions.append(cancel); actions.append(ok)
        box.append(actions)

        self.connect("response", self._on_resp, on_saved)

    def _on_resp(self, _d, resp, on_saved):
        if resp != Gtk.ResponseType.OK:
            self.close(); return
        s = self.anchor.get_text().strip()
        try:
            y, m, d = [int(p) for p in s.split("-")]
            anchor = date(y, m, d)
        except Exception:
            anchor = date.today()
        self.db.upsert_pay_schedule(anchor_date=anchor)
        on_saved()
        self.close()
