from __future__ import annotations
from gi.repository import Gtk, Adw
from datetime import date
from decimal import Decimal
from app.util import fmt_money, CURRENCY_SYMBOL

class PayScheduleDialog(Gtk.Dialog):
    def __init__(self, parent, db, on_saved):
        super().__init__(title="Set Payday (bi-weekly)", transient_for=parent, modal=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(12); box.set_margin_bottom(12)
        box.set_margin_start(12); box.set_margin_end(12)
        self.set_child(box)

        self.date_e = Gtk.Entry(placeholder_text="YYYY-MM-DD (a known payday)")
        box.append(self.date_e)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8); actions.set_halign(Gtk.Align.END)
        cancel = Gtk.Button.new_with_label("Cancel"); ok = Gtk.Button.new_with_label("Save")
        ok.get_style_context().add_class("suggested-action")
        cancel.connect("clicked", lambda *_: self.response(Gtk.ResponseType.CANCEL))
        ok.connect("clicked", lambda *_: self.response(Gtk.ResponseType.OK))
        actions.append(cancel); actions.append(ok); box.append(actions)

        self.connect("response", self._on_response, db, on_saved)

    def _on_response(self, _d, resp, db, on_saved):
        if resp == Gtk.ResponseType.OK:
            try:
                y,m,d = [int(x) for x in self.date_e.get_text().strip().split("-")]
                db.set_pay_schedule(date(y,m,d))
                on_saved()
            except Exception:
                pass
        self.close()


class AddBillDialog(Gtk.Dialog):
    def __init__(self, parent, db, on_added):
        super().__init__(title="Add Bill", transient_for=parent, modal=True)
        self.db = db
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(12); box.set_margin_bottom(12)
        box.set_margin_start(12); box.set_margin_end(12)
        self.set_child(box)

        self.payee_e = Gtk.Entry(placeholder_text="Payee (e.g., Electric)")
        self.amount_e = Gtk.Entry(placeholder_text="Amount due (e.g., 120.00)")
        self.debt_e = Gtk.Entry(placeholder_text="Total debt (optional)")
        self.freq_c = Gtk.ComboBoxText()
        self.freq_c.append_text("monthly"); self.freq_c.append_text("yearly"); self.freq_c.set_active(0)

        # monthly inputs
        self.monthly_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.month_day = Gtk.SpinButton.new_with_range(1,31,1); self.month_day.set_value(1)
        self.monthly_row.append(Gtk.Label(label="Due day of month:")); self.monthly_row.append(self.month_day)

        # yearly inputs
        self.yearly_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.year_month = Gtk.SpinButton.new_with_range(1,12,1); self.year_month.set_value(1)
        self.year_dom   = Gtk.SpinButton.new_with_range(1,31,1); self.year_dom.set_value(1)
        self.yearly_row.append(Gtk.Label(label="Due month:")); self.yearly_row.append(self.year_month)
        self.yearly_row.append(Gtk.Label(label="Day:"));       self.yearly_row.append(self.year_dom)
        self.yearly_row.set_visible(False)

        # account pick (optional)
        self.acc_c = Gtk.ComboBoxText()
        self.acc_c.append_text("(no specific account)")
        with db.pool.connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, acc_id FROM accounts WHERE active<>'NO' ORDER BY acc_id")
            for id_, name in cur.fetchall():
                self.acc_c.append(str(id_), name)
        self.acc_c.set_active(0)

        for w in (self.payee_e, self.amount_e, self.debt_e, self.freq_c, self.monthly_row, self.yearly_row, self.acc_c):
            box.append(w)

        def on_freq_changed(_c):
            is_m = self.freq_c.get_active_text() == "monthly"
            self.monthly_row.set_visible(is_m)
            self.yearly_row.set_visible(not is_m)
        self.freq_c.connect("changed", on_freq_changed)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8); actions.set_halign(Gtk.Align.END)
        cancel = Gtk.Button.new_with_label("Cancel")
        ok = Gtk.Button.new_with_label("Add Bill"); ok.get_style_context().add_class("suggested-action")
        cancel.connect("clicked", lambda *_: self.response(Gtk.ResponseType.CANCEL))
        ok.connect("clicked", lambda *_: self.response(Gtk.ResponseType.OK))
        actions.append(cancel); actions.append(ok); box.append(actions)

        for e in (self.payee_e, self.amount_e, self.debt_e):
            e.connect("activate", lambda *_: self.response(Gtk.ResponseType.OK))

        self.connect("response", self._on_response, on_added)

    def _on_response(self, _d, resp, on_added):
        if resp == Gtk.ResponseType.OK:
            payee = self.payee_e.get_text().strip()
            if not payee:
                self.close(); return
            try:
                amount = Decimal(self.amount_e.get_text() or "0")
            except Exception:
                amount = Decimal("0")
            try:
                debt = Decimal(self.debt_e.get_text() or "0")
            except Exception:
                debt = Decimal("0")
            freq = self.freq_c.get_active_text()
            if freq == "monthly":
                due_day = int(self.month_day.get_value())
                due_month = None; due_dom = None
            else:
                due_day = None
                due_month = int(self.year_month.get_value())
                due_dom   = int(self.year_dom.get_value())
            acc_id = None
            if self.acc_c.get_active_id():
                acc_id = int(self.acc_c.get_active_id())

            self.db.add_bill(
                payee=payee,
                frequency=freq,
                amount_due=amount,
                total_debt=debt,
                account_id=acc_id,
                due_day=due_day,
                due_month=due_month,
                due_dom=due_dom,
            )
            on_added()
        self.close()


class BillsView(Gtk.Box):
    def __init__(self, parent_window: Adw.ApplicationWindow, db):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_hexpand(True); self.set_vexpand(True)
        self.db = db
        self.parent_window = parent_window

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.title = Gtk.Label(label="Bills — next pay window", xalign=0)
        self.title.get_style_context().add_class("title-2")
        header.append(self.title)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.set_anchor_btn = Gtk.Button.new_with_label("Set payday")
        self.add_bill_btn = Gtk.Button.new_with_label("Add bill")
        actions.append(self.set_anchor_btn); actions.append(self.add_bill_btn)
        header.append(actions)

        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        scroll = Gtk.ScrolledWindow(child=self.list_box); scroll.set_hexpand(True); scroll.set_vexpand(True)

        self.append(header); self.append(scroll)

        self.set_anchor_btn.connect("clicked", self._on_set_anchor)
        self.add_bill_btn.connect("clicked", self._on_add_bill)

        self.reload()

    def reload(self):
        # clear
        child = self.list_box.get_first_child()
        while child:
            nxt = child.get_next_sibling(); self.list_box.remove(child); child = nxt

        data = self.db.upcoming_bills_for_next_pay_window(date.today())
        start = data["window_start"]; end = data["window_end"]
        self.title.set_label(f"Bills — payday window {start.isoformat()} → {end.isoformat()}")

        if not data["items"]:
            self.list_box.append(Gtk.Label(label="No bills in this pay window.", xalign=0))
            return

        for item in data["items"]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

            top = Gtk.Label(xalign=0, label=f"{item['due_date'].isoformat()} — {item['payee']}")
            amt = Gtk.Label(xalign=0, label=f"Due {fmt_money(Decimal(item['amount_due']), CURRENCY_SYMBOL)}")
            debt = Decimal(item["total_debt"] or 0)
            sub = Gtk.Label(xalign=0, label=(f"Debt: {fmt_money(debt, CURRENCY_SYMBOL)}" if debt else ""))
            sub.get_style_context().add_class("dim-label")

            left.append(top); left.append(amt); left.append(sub)
            row.append(left)

            right = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            if item["paid"]:
                paid_l = Gtk.Label(label="PAID"); paid_l.get_style_context().add_class("success")
                right.append(paid_l)
            else:
                btn = Gtk.Button.new_with_label("Mark paid")
                def _mark(_b, bill_id=item["bill_id"], due_dt=item["due_date"], amt_v=item["amount_due"]):
                    self.db.mark_bill_paid(bill_id, due_dt, amt_v); self.reload()
                btn.connect("clicked", _mark)
                right.append(btn)

            row.append(right)
            self.list_box.append(row)

    def _on_set_anchor(self, *_):
        dlg = PayScheduleDialog(self.parent_window, self.db, on_saved=lambda: self.reload())
        dlg.show()

    def _on_add_bill(self, *_):
        dlg = AddBillDialog(self.parent_window, self.db, on_added=lambda: self.reload())
        dlg.show()
