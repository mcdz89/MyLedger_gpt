from __future__ import annotations
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Pango
from decimal import Decimal
from datetime import date as _date
from app.util import fmt_money, CURRENCY_SYMBOL
from app.ui.dialogs import AddAccountDialog, AddTransactionDialog, AddBillDialog, SetPayScheduleDialog
from app.ui.bills import BillsView


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, db):
        super().__init__(application=app, title="MyLedger")
        self.set_default_size(1100, 680)
        self.db = db

        # Header
        header = Adw.HeaderBar()
        title = Adw.WindowTitle.new("MyLedger", "")
        header.set_title_widget(title)
        add_btn = Gtk.Button.new_with_label("Add account")
        header.pack_end(add_btn)

        # Sidebar (institutions/accounts)
        self.sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.sidebar_box.set_hexpand(True); self.sidebar_box.set_vexpand(True)
        sidebar_scroll = Gtk.ScrolledWindow(child=self.sidebar_box)
        sidebar_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_min_content_width(280)
        sidebar_scroll.set_hexpand(True); sidebar_scroll.set_vexpand(True)

        # Main area (summary / account view)
        self.main_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.main_area.set_hexpand(True); self.main_area.set_vexpand(True)
        main_scroll = Gtk.ScrolledWindow(child=self.main_area)
        main_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        main_scroll.set_hexpand(True); main_scroll.set_vexpand(True)

        # Split pane
        paned = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        paned.set_start_child(sidebar_scroll)
        paned.set_end_child(main_scroll)
        paned.set_position(320)
        try:
            paned.set_wide_handle(True)
        except Exception:
            pass
        paned.set_hexpand(True); paned.set_vexpand(True)

        # Root
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.set_hexpand(True); root.set_vexpand(True)
        root.append(header); root.append(paned)
        self.set_content(root)

        # Events
        add_btn.connect("clicked", self._on_add_account)

        # Initial content
        self.reload_sidebar()
        self.show_summary()

    # ---------- helpers ----------

    def clear_box(self, box: Gtk.Box):
        child = box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            box.remove(child)
            child = nxt

    # ---------- sidebar & summary ----------

    def reload_sidebar(self):
        self.clear_box(self.sidebar_box)

        summary_btn = Gtk.Button.new_with_label("Summary")
        summary_btn.get_style_context().add_class("suggested-action")
        summary_btn.set_hexpand(True)
        summary_btn.connect("clicked", lambda *_: self.show_summary())
        self.sidebar_box.append(summary_btn)

        for inst, accounts in self.db.sidebar_accounts():
            exp = Gtk.Expander(label=inst)
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            for acc_id, name, avail in accounts:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                btn = Gtk.Button.new_with_label(f"{name}  —  {fmt_money(Decimal(avail), CURRENCY_SYMBOL)}")
                btn.set_hexpand(True)
                btn.connect("clicked", lambda _b, acc_id=acc_id: self.show_account(acc_id))
                row.append(btn)
                inner.append(row)
            exp.set_child(inner)
            self.sidebar_box.append(exp)

        bills_btn = Gtk.Button.new_with_label("Bills")
        bills_btn.set_hexpand(True)
        bills_btn.connect("clicked", lambda *_: self.show_bills())
        self.sidebar_box.append(bills_btn)


    def show_summary(self):
        from decimal import Decimal
        from app.util import fmt_money, CURRENCY_SYMBOL

        self.clear_box(self.main_area)

        # Top-level account summary
        sql = """
            SELECT COUNT(*) AS cnt,
                COALESCE(SUM(a.balance + COALESCE(t.sum_all,0)),0) AS total
            FROM accounts a
            LEFT JOIN (
            SELECT acc_id, SUM(amount) AS sum_all FROM transactions GROUP BY acc_id
            ) t ON t.acc_id = a.id
            WHERE a.active <> 'NO'
        """
        with self.db.pool.connection() as conn, conn.cursor() as cur:
            cur.execute(sql)
            cnt, total = cur.fetchone()

        title = Gtk.Label(label="Summary"); title.get_style_context().add_class("title-1"); title.set_xalign(0)
        tot = Gtk.Label(label=f"Total Available: {fmt_money(Decimal(total or 0), CURRENCY_SYMBOL)}"); tot.get_style_context().add_class("title-3"); tot.set_xalign(0)
        cntl = Gtk.Label(label=f"Active accounts: {cnt}"); cntl.get_style_context().add_class("dim-label"); cntl.set_xalign(0)

        self.main_area.append(title)
        self.main_area.append(tot)
        self.main_area.append(cntl)

        # --- Bills for the current pay cycle ---
        ws, we = self.db.get_pay_window()
        cycle_lbl = Gtk.Label(label=f"Bills due this pay window: {ws} → {we}")
        cycle_lbl.get_style_context().add_class("title-3")
        cycle_lbl.set_xalign(0)

        rows = self.db.upcoming_bills(window_start=ws, window_end=we)

        # Total due = unpaid & not ignored
        total_due = sum(
            (Decimal(str(b["amount_due"])) for b in rows if not b.get("paid", False) and not b.get("ignored", False)),
            Decimal("0"),
        )
        total_due_lbl = Gtk.Label(label=f"Total due this window: {fmt_money(total_due, CURRENCY_SYMBOL)}")
        total_due_lbl.get_style_context().add_class("title-4")
        total_due_lbl.set_xalign(0)

        self.main_area.append(cycle_lbl)
        self.main_area.append(total_due_lbl)

        # Compact list (no controls here; manage in the Bills view)
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        list_box.set_hexpand(True); list_box.set_vexpand(False)
        self.main_area.append(list_box)

        if not rows:
            list_box.append(Gtk.Label(label="No bills due in this pay window.", xalign=0))
        else:
            for b in rows:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8); row.set_hexpand(True)
                left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

                name = Gtk.Label(label=f"{b['payee']} — due {b['next_due']}", xalign=0)
                sub = Gtk.Label(label=(b.get('account_name') or ""), xalign=0); sub.get_style_context().add_class("dim-label")
                left.append(name); left.append(sub)

                from decimal import Decimal as _D
                amt = Gtk.Label(label=fmt_money(_D(str(b['amount_due'])), CURRENCY_SYMBOL)); amt.set_xalign(1.0)

                row.append(left); row.append(amt)
                list_box.append(row)

        # Action to manage full list
        manage = Gtk.Button.new_with_label("Manage all bills…")
        manage.connect("clicked", lambda *_: self.show_bills())
        self.main_area.append(manage)


    # ---------- account view (with inline editing) ----------

    def show_account(self, account_id: int):
        self.clear_box(self.main_area)

        inst, name, posted, avail = self.db.account_header(account_id)

        title = Gtk.Label(label=f"{inst} · {name}")
        title.get_style_context().add_class("title-2")
        title.set_xalign(0)

        posted_lbl = Gtk.Label(label=f"Posted: {fmt_money(Decimal(posted), CURRENCY_SYMBOL)}")
        posted_lbl.set_xalign(0)

        avail_lbl = Gtk.Label(label=f"Available: {fmt_money(Decimal(avail), CURRENCY_SYMBOL)}")
        avail_lbl.get_style_context().add_class("title-4")
        avail_lbl.set_xalign(0)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        add_txn_btn = Gtk.Button.new_with_label("Add transaction")
        edit_toggle = Gtk.CheckButton(label="Edit order")
        toolbar.append(add_txn_btn)
        toolbar.append(edit_toggle)

        txn_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        txn_list.set_hexpand(True); txn_list.set_vexpand(True)

        self.main_area.append(title)
        self.main_area.append(posted_lbl)
        self.main_area.append(avail_lbl)
        self.main_area.append(toolbar)
        self.main_area.append(txn_list)

        def reload_account_view():
            self.reload_sidebar()
            self.show_account(account_id)

        def load_txns():
            self.clear_box(txn_list)

            # ---- UI row builders ----

            def make_display_row(r: dict) -> Gtk.Box:
                rowbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                rowbox.set_hexpand(True)

                left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                right = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                right.set_halign(Gtk.Align.END)
                right.set_hexpand(True)

                date_s = (r.get("occurred_on") or "")
                name_s = r.get("name") or ""

                title = Gtk.Label(label=f"{date_s} — {name_s}")
                title.set_xalign(0)
                title.set_wrap(True)
                title.set_wrap_mode(Pango.WrapMode.WORD_CHAR)

                sub = Gtk.Label(label=f"{r.get('ttype') or ''} · {r.get('method') or ''}")
                sub.get_style_context().add_class("dim-label")
                sub.set_xalign(0)

                left.append(title)
                left.append(sub)

                amount = Decimal(r.get("amount") or 0)
                amt = Gtk.Label(label=fmt_money(amount, CURRENCY_SYMBOL))
                amt.set_xalign(1.0)
                if amount < 0:
                    amt.get_style_context().add_class("error")
                else:
                    amt.get_style_context().add_class("success")
                right.append(amt)

                pend = Gtk.CheckButton(label="Pending")
                pend.set_active(bool(int(r.get("pending") or 0)))
                tid = int(r["id"])

                def on_pend_toggled(w):
                    self.db.set_txn_pending(tid, w.get_active())
                    reload_account_view()

                pend.connect("toggled", on_pend_toggled)
                right.append(pend)

                up = Gtk.Button.new_with_label("▲")
                down = Gtk.Button.new_with_label("▼")
                up.connect("clicked",
                           lambda _b, aid=account_id, tid=tid: (self.db.move_txn_up(aid, tid), reload_account_view()))
                down.connect("clicked",
                             lambda _b, aid=account_id, tid=tid: (self.db.move_txn_down(aid, tid), reload_account_view()))

                def _toggle(_t, u=up, d=down):
                    vis = edit_toggle.get_active()
                    u.set_visible(vis); d.set_visible(vis)

                edit_toggle.connect("toggled", _toggle)
                up.set_visible(edit_toggle.get_active())
                down.set_visible(edit_toggle.get_active())
                right.append(up)
                right.append(down)

                # Double-click to edit
                gesture = Gtk.GestureClick()
                gesture.set_button(0)  # any button
                def on_release(gest, n_press, x, y, _r=r, _rb=rowbox):
                    if n_press == 2:
                        enter_edit_mode(_rb, _r)
                gesture.connect("released", on_release)
                rowbox.add_controller(gesture)

                rowbox.append(left)
                rowbox.append(right)
                return rowbox

            def enter_edit_mode(rowbox: Gtk.Box, r: dict):
                # wipe row content
                ch = rowbox.get_first_child()
                while ch is not None:
                    nxt = ch.get_next_sibling()
                    rowbox.remove(ch)
                    ch = nxt

                editor = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                editor.set_hexpand(True)

                # Top line: name + amount + pending
                top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                name_e = Gtk.Entry(text=r.get("name") or "")
                name_e.set_hexpand(True)
                amount_e = Gtk.Entry(text=str(r.get("amount") or "0"))
                pending_c = Gtk.CheckButton(label="Pending")
                pending_c.set_active(bool(int(r.get("pending") or 0)))
                top.append(name_e)
                top.append(amount_e)
                top.append(pending_c)
                editor.append(top)

                # Second: date + type/method/cat
                second = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                date_e = Gtk.Entry(text=str(r.get("occurred_on") or ""), placeholder_text="YYYY-MM-DD")
                date_e.set_hexpand(True)

                type_c = Gtk.ComboBoxText()
                method_c = Gtk.ComboBoxText()
                cat_c = Gtk.ComboBoxText()

                second.append(date_e)
                second.append(type_c)
                second.append(method_c)
                second.append(cat_c)

                editor.append(second)

                # Actions
                actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                actions.set_halign(Gtk.Align.END)
                cancel_b = Gtk.Button.new_with_label("Cancel")
                save_b = Gtk.Button.new_with_label("Save")
                save_b.get_style_context().add_class("suggested-action")
                actions.append(cancel_b)
                actions.append(save_b)
                editor.append(actions)

                rowbox.append(editor)

                # Populate combos, preselect current IDs
                with self.db.pool.connection() as conn, conn.cursor() as cur:
                    for sql, combo, current_id in [
                        ("SELECT id, type   FROM trans_type   ORDER BY id", type_c,   r.get("type_id")   or None),
                        ("SELECT id, method FROM trans_method ORDER BY id", method_c, r.get("method_id") or None),
                        ("SELECT id, cat    FROM trans_cat    ORDER BY id", cat_c,    r.get("cat_id")    or None),
                    ]:
                        combo.remove_all()
                        cur.execute(sql)
                        rows = cur.fetchall()
                        for id_, lbl in rows:
                            combo.append(str(id_), str(lbl))
                        if current_id:
                            combo.set_active_id(str(int(current_id)))
                        else:
                            combo.set_active(0)

                tid = int(r["id"])

                def do_cancel(*_):
                    # Rebuild full list (simple & robust)
                    load_txns()

                def do_save(*_):
                    name = name_e.get_text().strip()
                    if not name:
                        do_cancel()
                        return
                    try:
                        amt = Decimal(amount_e.get_text() or "0")
                    except Exception:
                        amt = Decimal("0")
                    when_s = date_e.get_text().strip()
                    try:
                        y, m, d = [int(p) for p in when_s.split("-")]
                        when = _date(y, m, d)
                    except Exception:
                        when = _date.today()

                    type_id   = int(type_c.get_active_id() or 1)
                    method_id = int(method_c.get_active_id()) if method_c.get_active_id() else None
                    cat_id    = int(cat_c.get_active_id())    if cat_c.get_active_id()    else None

                    self.db.update_transaction(
                        tid, account_id,
                        type_id=type_id,
                        name=name,
                        method_id=method_id,
                        cat_id=cat_id,
                        amount=amt,                # DB layer normalizes sign by type
                        occurred_on=when,
                        pending=pending_c.get_active(),
                    )
                    reload_account_view()

                cancel_b.connect("clicked", do_cancel)
                save_b.connect("clicked", do_save)
                for e in (name_e, amount_e, date_e):
                    e.connect("activate", do_save)

            # Render all rows
            for r in self.db.list_transactions(account_id):
                txn_list.append(make_display_row(r))

        # Hook up Add Transaction
        add_txn_btn.connect(
            "clicked",
            lambda *_: AddTransactionDialog(
                self,
                self.db,
                account_id,
                on_created=lambda: (self.reload_sidebar(), self.show_account(account_id)),
            ).show()
        )

        load_txns()

    # ---------- actions ----------

    def _on_add_account(self, *_):
        AddAccountDialog(
            self,
            self.db,
            on_created=lambda: (self.reload_sidebar(), self.show_summary())
        ).show()

    def show_bills(self):
        from decimal import Decimal
        from datetime import date as _date
        from app.util import fmt_money, CURRENCY_SYMBOL
        from app.db import _next_monthly_due, _next_yearly_due

        self.clear_box(self.main_area)

        # Header + controls
        title = Gtk.Label(label="Bills"); title.get_style_context().add_class("title-2"); title.set_xalign(0)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        add_btn = Gtk.Button.new_with_label("Add bill")
        sched_btn = Gtk.Button.new_with_label("Pay schedule…")
        controls.append(add_btn); controls.append(sched_btn)

        self.main_area.append(title)
        self.main_area.append(controls)

        # List area
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        list_box.set_vexpand(True); list_box.set_hexpand(True)
        self.main_area.append(list_box)

        def reload_view(): self.show_bills()

        def load():
            self.clear_box(list_box)

            # Show ALL active bills with their computed next due (from "today")
            base = _date.today()
            bills = self.db.list_bills(active_only=True)

            rows = []
            for b in bills:
                freq = (b["frequency"] or "monthly").lower()
                if freq == "monthly" and b["due_day"]:
                    due = _next_monthly_due(int(b["due_day"]), base)
                elif freq == "yearly" and b["due_month"] and b["due_dom"]:
                    due = _next_yearly_due(int(b["due_month"]), int(b["due_dom"]), base)
                else:
                    continue

                b2 = dict(b)
                b2["next_due"] = due
                b2["paid"] = self.db._is_bill_paid(bill_id=int(b["id"]), due_date=due)
                b2["ignored"] = self.db._is_bill_ignored(bill_id=int(b["id"]), due_date=due)
                rows.append(b2)

            rows.sort(key=lambda r: (r["next_due"], r["payee"].lower()))

            if not rows:
                list_box.append(Gtk.Label(label="No active bills.", xalign=0))
                return

            for b in rows:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8); row.set_hexpand(True)

                left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                right = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6); right.set_halign(Gtk.Align.END); right.set_hexpand(True)

                name = Gtk.Label(label=f"{b['payee']} — next due {b['next_due']}", xalign=0)
                sub = Gtk.Label(label=(b.get('account_name') or ""), xalign=0); sub.get_style_context().add_class("dim-label")
                left.append(name); left.append(sub)

                amt = Gtk.Label(label=fmt_money(Decimal(str(b['amount_due'])), CURRENCY_SYMBOL)); right.append(amt)

                # Ignore toggle (per-occurrence)
                ignore = Gtk.CheckButton(label="Ignore")
                ignore.set_active(bool(b.get("ignored", False)))
                ignore.set_sensitive(not b.get("paid", False))
                def on_ignore_toggled(w, bid=b['id'], dd=b['next_due']):
                    self.db.set_bill_ignored(bill_id=bid, due_date=dd, ignored=w.get_active())
                    reload_view()
                ignore.connect("toggled", on_ignore_toggled)
                right.append(ignore)

                # Mark paid
                pay = Gtk.Button.new_with_label("Mark paid")
                pay.set_sensitive(not b.get("paid", False))
                pay.connect("clicked", lambda _w, bid=b['id'], dd=b['next_due']: (
                    self.db.mark_bill_paid(bill_id=bid, due_date=dd),
                    self.reload_sidebar(),
                    reload_view()
                ))
                right.append(pay)

                row.append(left); row.append(right); list_box.append(row)

        add_btn.connect("clicked", lambda *_: AddBillDialog(self, self.db, on_created=reload_view).show())
        sched_btn.connect("clicked", lambda *_: SetPayScheduleDialog(self, self.db, on_saved=reload_view).show())
        load()
