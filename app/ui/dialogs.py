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
        self._db = db
        self._account_id = account_id

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(12); box.set_margin_bottom(12)
        box.set_margin_start(12); box.set_margin_end(12)
        self.set_child(box)

        # description + amount (unsigned; sign normalized by DB based on type)
        self.name_e = Gtk.Entry(placeholder_text="Description")
        self.amount_e = Gtk.Entry(placeholder_text="Amount (no sign)")
        box.append(self.name_e)

        # Suggestions list (appears under the name entry when typing)
        self._sugg_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._sugg_box.set_visible(False)
        self._sugg_list = Gtk.ListBox()
        self._sugg_box.append(self._sugg_list)
        box.append(self._sugg_box)

        box.append(self.amount_e)

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

        # Wire name suggestions (type-ahead)
        self.name_e.connect("changed", self._on_name_changed)
        # Seed recent suggestions on focus enter (GTK4 event controller)
        foc = Gtk.EventControllerFocus()
        foc.connect("enter", lambda *_: self._on_name_focus())
        self.name_e.add_controller(foc)

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

    # ---- Name suggestions helpers ----
    def _fill_suggestions(self, items: list[str]):
        # Clear existing
        child = self._sugg_list.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._sugg_list.remove(child)
            child = nxt
        # Refill
        for s in items:
            row = Gtk.ListBoxRow()
            btn = Gtk.Button.new_with_label(s)
            btn.set_halign(Gtk.Align.START)
            btn.connect("clicked", self._on_suggestion_clicked, s)
            row.set_child(btn)
            self._sugg_list.append(row)
        self._sugg_box.set_visible(len(items) > 0)

    def _on_suggestion_clicked(self, _btn, text: str):
        self.name_e.set_text(text)
        self._sugg_box.set_visible(False)
        # Advance focus to amount for quick entry
        self.amount_e.grab_focus()

    def _on_name_changed(self, _entry):
        txt = (self.name_e.get_text() or "").strip()
        if len(txt) < 2:
            self._sugg_box.set_visible(False)
            return
        items = self._db.suggest_transaction_names(account_id=self._account_id, prefix=txt, limit=8)
        self._fill_suggestions(items)

    def _on_name_focus(self, *_):
        # Show most recent suggestions when focusing, if field is empty
        if (self.name_e.get_text() or "").strip():
            return False
        items = self._db.suggest_transaction_names(account_id=self._account_id, prefix=None, limit=8)
        self._fill_suggestions(items)
        return False
        
class EditTransactionDialog(Gtk.Dialog):
    def __init__(self, parent: Adw.ApplicationWindow, db, account_id: int, txn: dict, on_saved):
        super().__init__(title="Edit Transaction", transient_for=parent, modal=True)
        self._db = db
        self._account_id = account_id
        self._txn = txn

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(12); box.set_margin_bottom(12)
        box.set_margin_start(12); box.set_margin_end(12)
        self.set_child(box)

        # description + amount (unsigned; DB normalizes on save)
        self.name_e = Gtk.Entry(placeholder_text="Description")
        self.amount_e = Gtk.Entry(placeholder_text="Amount (no sign)")
        box.append(self.name_e)

        # Suggestions list for edit dialog as well
        self._sugg_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._sugg_box.set_visible(False)
        self._sugg_list = Gtk.ListBox()
        self._sugg_box.append(self._sugg_list)
        box.append(self._sugg_box)

        box.append(self.amount_e)

        # date row with calendar popover
        date_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.date_e = Gtk.Entry(placeholder_text="YYYY-MM-DD")
        self.date_e.set_hexpand(True)
        cal_btn = Gtk.MenuButton(icon_name="calendar-symbolic")
        pop = Gtk.Popover()
        cal = Gtk.Calendar()
        pop.set_child(cal)
        cal_btn.set_popover(pop)

        def _set_date_from_calendar(_cal):
            dt: GLib.DateTime = cal.get_date()
            y = int(dt.get_year()); m = int(dt.get_month()); d = int(dt.get_day_of_month())
            self.date_e.set_text(f"{y:04d}-{m:02d}-{d:02d}")
            pop.popdown()

        cal.connect("day-selected", _set_date_from_calendar)
        date_row.append(self.date_e); date_row.append(cal_btn)
        box.append(date_row)

        # Combo pickers
        self.type_c   = Gtk.ComboBoxText()
        self.method_c = Gtk.ComboBoxText()
        self.cat_c    = Gtk.ComboBoxText()
        for w in (self.type_c, self.method_c, self.cat_c):
            box.append(w)

        # Pending toggle
        self.pending_c = Gtk.CheckButton(label="Pending")
        box.append(self.pending_c)

        # actions
        actions_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions_row.set_hexpand(True)

        # Delete (destructive)
        del_btn = Gtk.Button.new_with_label("Delete")
        del_btn.get_style_context().add_class("destructive-action")
        def _confirm_delete(_w):
            MsgDlg = getattr(Adw, "MessageDialog", None)
            if MsgDlg is not None:
                md = MsgDlg(
                    transient_for=self,
                    modal=True,
                    heading="Delete transaction?",
                    body="This cannot be undone.",
                )
                md.add_response("cancel", "Cancel")
                md.add_response("delete", "Delete")
                try:
                    md.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
                except Exception:
                    pass
                def _on_resp(_d, resp):
                    if resp == "delete":
                        self._db.delete_transaction(int(self._txn.get("id")), self._account_id)
                        on_saved()
                        self.close()
                md.connect("response", _on_resp)
                md.present()
            else:
                # Fallback: delete directly
                self._db.delete_transaction(int(self._txn.get("id")), self._account_id)
                on_saved()
                self.close()
        del_btn.connect("clicked", _confirm_delete)

        # Right-aligned Cancel/Save
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        cancel_btn = Gtk.Button.new_with_label("Cancel")
        submit_btn = Gtk.Button.new_with_label("Save")
        submit_btn.get_style_context().add_class("suggested-action")
        cancel_btn.connect("clicked", lambda *_: self.response(Gtk.ResponseType.CANCEL))
        submit_btn.connect("clicked", lambda *_: self.response(Gtk.ResponseType.OK))

        actions.append(cancel_btn); actions.append(submit_btn)
        actions_row.append(del_btn)
        _sp = Gtk.Box(); _sp.set_hexpand(True)
        actions_row.append(_sp)  # spacer expands
        actions_row.append(actions)
        box.append(actions_row)

        # Enter to submit
        for e in (self.name_e, self.amount_e, self.date_e):
            e.connect("activate", lambda *_: self.response(Gtk.ResponseType.OK))

        # Fill combos
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

        # Pre-fill from txn dict
        self.name_e.set_text(str(txn.get("name") or ""))
        try:
            amt = abs(Decimal(txn.get("amount") or 0))
        except Exception:
            amt = Decimal("0")
        self.amount_e.set_text(str(amt))
        self.date_e.set_text(str(txn.get("occurred_on") or ""))
        # Select by ids when available
        if txn.get("type_id"):
            self.type_c.set_active_id(str(int(txn.get("type_id"))))
        else:
            self.type_c.set_active(0)
        if txn.get("method_id") and int(txn.get("method_id") or 0) > 0:
            self.method_c.set_active_id(str(int(txn.get("method_id"))))
        else:
            self.method_c.set_active(0)
        if txn.get("cat_id") and int(txn.get("cat_id") or 0) > 0:
            self.cat_c.set_active_id(str(int(txn.get("cat_id"))))
        else:
            self.cat_c.set_active(0)
        self.pending_c.set_active(bool(int(txn.get("pending") or 0)))

        # Wire response
        self.connect("response", self._on_response, db, account_id, txn, on_saved)

        # Wire name suggestions (type-ahead)
        self.name_e.connect("changed", self._on_name_changed)
        foc = Gtk.EventControllerFocus()
        foc.connect("enter", lambda *_: self._on_name_focus())
        self.name_e.add_controller(foc)

    def _on_response(self, _dialog, resp, db, account_id: int, txn: dict, on_saved):
        if resp == Gtk.ResponseType.OK:
            name = self.name_e.get_text().strip()
            if not name:
                self.close(); return
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

            db.update_transaction(
                txn_id=int(txn.get("id")),
                account_id=account_id,
                type_id=type_id,
                name=name,
                method_id=method_id,
                cat_id=cat_id,
                amount=amount,
                occurred_on=when,
                pending=self.pending_c.get_active(),
            )
            on_saved()
        self.close()

    # ---- Name suggestions (Edit) ----
    def _fill_suggestions(self, items: list[str]):
        child = self._sugg_list.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._sugg_list.remove(child)
            child = nxt
        for s in items:
            row = Gtk.ListBoxRow()
            btn = Gtk.Button.new_with_label(s)
            btn.set_halign(Gtk.Align.START)
            btn.connect("clicked", self._on_suggestion_clicked, s)
            row.set_child(btn)
            self._sugg_list.append(row)
        self._sugg_box.set_visible(len(items) > 0)

    def _on_suggestion_clicked(self, _btn, text: str):
        self.name_e.set_text(text)
        self._sugg_box.set_visible(False)
        self.amount_e.grab_focus()

    def _on_name_changed(self, _entry):
        txt = (self.name_e.get_text() or "").strip()
        if len(txt) < 2:
            self._sugg_box.set_visible(False)
            return
        items = self._db.suggest_transaction_names(account_id=self._account_id, prefix=txt, limit=8)
        self._fill_suggestions(items)

    def _on_name_focus(self, *_):
        if (self.name_e.get_text() or "").strip():
            return False
        items = self._db.suggest_transaction_names(account_id=self._account_id, prefix=None, limit=8)
        self._fill_suggestions(items)
        return False
        
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

class EditBillDialog(Gtk.Dialog):
    def __init__(self, parent: Adw.ApplicationWindow, db, bill: dict, on_saved):
        super().__init__(title="Edit Bill", transient_for=parent, modal=True)
        self.db = db
        self._bill = bill

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

        self.due_day = Gtk.SpinButton.new_with_range(1, 31, 1)
        self.due_month = Gtk.SpinButton.new_with_range(1, 12, 1)
        self.due_dom = Gtk.SpinButton.new_with_range(1, 31, 1)

        self.account = Gtk.ComboBoxText()
        with db.pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, acc_id FROM accounts WHERE active <> 'NO' ORDER BY institution, acc_id")
            for i, n in cur.fetchall():
                self.account.append(str(i), str(n))

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

        # Prefill
        self.payee.set_text(str(bill.get("payee") or ""))
        self.amount.set_text(str(bill.get("amount_due") or ""))
        self.total_debt.set_text(str(bill.get("total_debt") or ""))
        freqv = (bill.get("frequency") or "monthly").lower()
        self.freq.set_active_id("monthly" if freqv == "monthly" else "yearly")
        self.due_day.set_value(float(bill.get("due_day") or 1))
        self.due_month.set_value(float(bill.get("due_month") or 1))
        self.due_dom.set_value(float(bill.get("due_dom") or 1))
        if bill.get("account_id"):
            self.account.set_active_id(str(int(bill.get("account_id"))))
        elif self.account.get_active_id() is None and self.account.get_row_count() > 0:
            self.account.set_active(0)
        self.notes.set_text(str(bill.get("notes") or ""))
        toggle_fields()

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
        try:
            amount = Decimal(self.amount.get_text() or "0")
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

        self.db.update_bill(
            bill_id=int(self._bill.get("id")),
            payee=self.payee.get_text().strip(),
            amount_due=amount,
            frequency=freq,
            due_day=due_day,
            due_month=due_month,
            due_dom=due_dom,
            account_id=acc_id,
            total_debt=td,
            notes=self.notes.get_text().strip(),
        )
        on_saved()
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
