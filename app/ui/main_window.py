# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Pango, Gdk, GLib

from decimal import Decimal
from datetime import date as _date, timedelta as _td

from app.util import fmt_money, CURRENCY_SYMBOL
from app.ui.dialogs import (
    AddAccountDialog,
    AddTransactionDialog,
    EditBillDialog,
    EditTransactionDialog,
    AddBillDialog,
    SetPayScheduleDialog,
)
# helpers used in the Bills screen (computed next due dates)
from app.db import _next_monthly_due, _next_yearly_due


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, db):
        super().__init__(application=app, title="MyLedger")
        self.set_default_size(1100, 680)
        self.db = db
        # Remember whether the user enabled Edit Order (sticky across refreshes)
        self._edit_order_active = False
        # Summary pay window offset (0 = current, +1 next, -1 previous)
        self._summary_window_offset = 0

        # Header
        header = Adw.HeaderBar()
        title = Adw.WindowTitle.new("MyLedger", "")
        header.set_title_widget(title)

        # About button (shows AI notice, license, etc.)
        about_btn = Gtk.Button.new_with_label("About")
        header.pack_start(about_btn)
        about_btn.connect("clicked", self._show_about)

        # Quick add account
        add_btn = Gtk.Button.new_with_label("Add account")
        header.pack_end(add_btn)

        # Sidebar (institutions/accounts)
        self.sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.sidebar_box.set_hexpand(True)
        self.sidebar_box.set_vexpand(True)
        sidebar_scroll = Gtk.ScrolledWindow(child=self.sidebar_box)
        sidebar_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_min_content_width(280)
        sidebar_scroll.set_hexpand(True)
        sidebar_scroll.set_vexpand(True)

        # Main content area (scrollable)
        self.main_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.main_area.set_hexpand(True)
        self.main_area.set_vexpand(True)
        main_scroll = Gtk.ScrolledWindow(child=self.main_area)
        main_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        main_scroll.set_hexpand(True)
        main_scroll.set_vexpand(True)

        # Split pane
        paned = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
        paned.set_start_child(sidebar_scroll)
        paned.set_end_child(main_scroll)
        paned.set_position(320)
        try:
            paned.set_wide_handle(True)
        except Exception:
            pass
        paned.set_hexpand(True)
        paned.set_vexpand(True)

        # Root layout
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        root.set_hexpand(True)
        root.set_vexpand(True)
        root.append(header)
        root.append(paned)
        self.set_content(root)

        # Wire actions
        add_btn.connect("clicked", self._on_add_account)

        # Initial UI
        self.reload_sidebar()
        self.show_summary()

    # ---------- UI helpers ----------

    def clear_box(self, box: Gtk.Box):
        child = box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            box.remove(child)
            child = nxt

    def reload_sidebar(self):
        self.clear_box(self.sidebar_box)

        # Summary
        summary_btn = Gtk.Button.new_with_label("Summary")
        summary_btn.get_style_context().add_class("suggested-action")
        summary_btn.set_hexpand(True)
        summary_btn.connect("clicked", lambda *_: self.show_summary())
        self.sidebar_box.append(summary_btn)

        # Bills
        bills_btn = Gtk.Button.new_with_label("Bills")
        bills_btn.set_hexpand(True)
        bills_btn.connect("clicked", lambda *_: self.show_bills())
        self.sidebar_box.append(bills_btn)

        # Institutions → accounts
        for inst, accounts in self.db.sidebar_accounts():
            exp = Gtk.Expander(label=inst)
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            for acc_id, name, avail in accounts:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                btn = Gtk.Button.new_with_label(
                    f"{name}  —  {fmt_money(Decimal(avail), CURRENCY_SYMBOL)}"
                )
                btn.set_hexpand(True)
                btn.connect("clicked", lambda _b, acc_id=acc_id: self.show_account(acc_id))
                row.append(btn)
                inner.append(row)
            exp.set_child(inner)
            self.sidebar_box.append(exp)

    # ---------- Summary (includes current pay-window bills) ----------

    def show_summary(self, *, window_offset: int | None = None):
        from app.util import fmt_money, CURRENCY_SYMBOL

        self.clear_box(self.main_area)

        # Accounts rollup
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

        title = Gtk.Label(label="Summary")
        title.get_style_context().add_class("title-1")
        title.set_xalign(0)

        tot = Gtk.Label(
            label=f"Total Available: {fmt_money(Decimal(total or 0), CURRENCY_SYMBOL)}"
        )
        tot.get_style_context().add_class("title-3")
        tot.set_xalign(0)

        cntl = Gtk.Label(label=f"Active accounts: {cnt}")
        cntl.get_style_context().add_class("dim-label")
        cntl.set_xalign(0)

        self.main_area.append(title)
        self.main_area.append(tot)
        self.main_area.append(cntl)

        # Determine pay window (with offset support for scrolling/navigating)
        if window_offset is not None:
            self._summary_window_offset = int(window_offset)
        # Shift "today" to the desired window by 14-day steps
        shifted_today = _date.today() + _td(days=14 * self._summary_window_offset)
        ws, we = self.db.get_pay_window(today=shifted_today)

        # Navigation controls for pay windows
        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        prev_btn = Gtk.Button.new_with_label("◀")
        next_btn = Gtk.Button.new_with_label("▶")
        cycle_lbl = Gtk.Label(label=f"Bills: {ws} → {we}")
        cycle_lbl.get_style_context().add_class("title-3")
        cycle_lbl.set_xalign(0)
        nav.append(prev_btn)
        nav.append(cycle_lbl)
        nav.append(next_btn)

        def _go_prev(_b):
            self.show_summary(window_offset=self._summary_window_offset - 1)
        def _go_next(_b):
            self.show_summary(window_offset=self._summary_window_offset + 1)
        prev_btn.connect("clicked", _go_prev)
        next_btn.connect("clicked", _go_next)

        # Add horizontal scroll gesture to switch windows
        scr = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.HORIZONTAL)
        def _on_scroll(_ctrl, dx, dy):
            # Right swipe/scroll (dx < 0) -> next; left (dx > 0) -> prev
            if dx < 0:
                _go_next(None)
            elif dx > 0:
                _go_prev(None)
            return True
        scr.connect("scroll", _on_scroll)
        nav.add_controller(scr)
        self.main_area.append(nav)

        rows = self.db.upcoming_bills(window_start=ws, window_end=we)
        # Exclude ignored bills from the Summary view entirely
        rows = [b for b in rows if not b.get("ignored", False)]

        # Total due = unpaid (ignored already filtered out; always Decimal)
        total_due = sum(
            (Decimal(str(b["amount_due"])) for b in rows if not b.get("paid", False)),
            Decimal("0"),
        )
        total_due_lbl = Gtk.Label(
            label=f"Total due this window: {fmt_money(total_due, CURRENCY_SYMBOL)}"
        )
        total_due_lbl.get_style_context().add_class("title-4")
        total_due_lbl.set_xalign(0)
        self.main_area.append(total_due_lbl)

        # Compact list
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        list_box.set_hexpand(True)
        list_box.set_vexpand(False)
        self.main_area.append(list_box)

        if not rows:
            list_box.append(Gtk.Label(label="No bills due in this pay window.", xalign=0))
        else:
            for b in rows:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                row.set_hexpand(True)

                left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                name = Gtk.Label(label=f"{b['payee']} — due {b['next_due']}", xalign=0)
                sub = Gtk.Label(label=(b.get("account_name") or ""), xalign=0)
                sub.get_style_context().add_class("dim-label")
                left.append(name)
                left.append(sub)

                amt = Gtk.Label(
                    label=fmt_money(Decimal(str(b["amount_due"])), CURRENCY_SYMBOL)
                )
                amt.set_xalign(1.0)

                row.append(left)
                row.append(amt)
                list_box.append(row)

        # Manage button
        manage = Gtk.Button.new_with_label("Manage all bills…")
        manage.connect("clicked", lambda *_: self.show_bills())
        self.main_area.append(manage)

        # AI notice (optional)
        note = Gtk.Label(
            label="Notice: This application was generated in part with the help of an AI LLM.",
            xalign=0,
        )
        note.get_style_context().add_class("dim-label")
        self.main_area.append(note)

    # ---------- Bills (ALL active bills with next due) ----------

    def show_bills(self):
        from app.util import fmt_money, CURRENCY_SYMBOL

        self.clear_box(self.main_area)

        # Header + controls
        title = Gtk.Label(label="Bills")
        title.get_style_context().add_class("title-2")
        title.set_xalign(0)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        add_btn = Gtk.Button.new_with_label("Add bill")
        sched_btn = Gtk.Button.new_with_label("Pay schedule…")
        controls.append(add_btn)
        controls.append(sched_btn)

        self.main_area.append(title)
        self.main_area.append(controls)

        # List area
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        list_box.set_vexpand(True)
        list_box.set_hexpand(True)
        self.main_area.append(list_box)

        def reload_view():
            self.show_bills()

        def load():
            self.clear_box(list_box)

            # Show ALL active bills, each with its computed next due date.
            rows = self.db.list_bills(active_only=True)

            if not rows:
                list_box.append(Gtk.Label(label="No active bills.", xalign=0))
                return

            today = _date.today()

            for b in rows:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                row.set_hexpand(True)

                left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                right = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                right.set_halign(Gtk.Align.END)
                right.set_hexpand(True)

                # Compute next due date for display and actions
                dd = None
                try:
                    freq = (b.get('frequency') or 'monthly').lower()
                    if freq == 'monthly' and b.get('due_day'):
                        dd = _next_monthly_due(int(b.get('due_day')), today)
                    elif freq == 'yearly' and b.get('due_month') and b.get('due_dom'):
                        dd = _next_yearly_due(int(b.get('due_month')), int(b.get('due_dom')), today)
                except Exception:
                    dd = None

                name_txt = f"{b['payee']} — next due {dd}" if dd else f"{b['payee']}"
                name = Gtk.Label(label=name_txt, xalign=0)
                sub = Gtk.Label(label=(b.get("account_name") or ""), xalign=0)
                sub.get_style_context().add_class("dim-label")
                left.append(name)
                left.append(sub)

                amt = Gtk.Label(label=fmt_money(Decimal(str(b["amount_due"])), CURRENCY_SYMBOL))
                right.append(amt)

                # Ignore/paid actions are tied to a specific occurrence (next due)
                # Only show when we can compute a due date.
                if dd is not None:
                    paid = self.db._is_bill_paid(bill_id=int(b["id"]), due_date=dd)
                    ignored = self.db._is_bill_ignored(bill_id=int(b["id"]), due_date=dd)

                    # Ignore toggle (per-occurrence)
                    ignore = Gtk.CheckButton(label="Ignore")
                    ignore.set_active(bool(ignored))
                    ignore.set_sensitive(not paid)

                    def on_ignore_toggled(w, bid=b["id"], due_d=dd):
                        self.db.set_bill_ignored(bill_id=bid, due_date=due_d, ignored=w.get_active())
                        reload_view()

                    ignore.connect("toggled", on_ignore_toggled)
                    right.append(ignore)

                    # Mark paid
                    pay = Gtk.Button.new_with_label("Mark paid")
                    pay.set_sensitive(not paid)
                    pay.connect(
                        "clicked",
                        lambda _w, bid=b["id"], due_d=dd: (
                            self.db.mark_bill_paid(bill_id=bid, due_date=due_d),
                            self.reload_sidebar(),
                            reload_view(),
                        ),
                    )
                    right.append(pay)

                # Double-click to edit bill details
                def _on_pressed(gesture, n_press, x, y, _bill=b):
                    if n_press == 2:
                        EditBillDialog(
                            self,
                            self.db,
                            _bill,
                            on_saved=reload_view,
                        ).show()
                click = Gtk.GestureClick()
                click.set_button(0)
                click.connect("pressed", _on_pressed)
                row.add_controller(click)

                row.append(left)
                row.append(right)
                list_box.append(row)

        add_btn.connect(
            "clicked",
            lambda *_: AddBillDialog(self, self.db, on_created=reload_view).show(),
        )
        sched_btn.connect(
            "clicked",
            lambda *_: SetPayScheduleDialog(self, self.db, on_saved=reload_view).show(),
        )
        load()

    # ---------- Accounts / Transactions ----------

    def show_account(self, account_id: int):
        self.clear_box(self.main_area)

        inst, name, posted, avail = self.db.account_header(account_id)

        title = Gtk.Label(label=f"{inst} · {name}")
        title.get_style_context().add_class("title-2")
        title.set_xalign(0)

        posted_lbl = Gtk.Label(
            label=f"Posted: {fmt_money(Decimal(posted), CURRENCY_SYMBOL)}"
        )
        posted_lbl.set_xalign(0)

        avail_lbl = Gtk.Label(
            label=f"Available: {fmt_money(Decimal(avail), CURRENCY_SYMBOL)}"
        )
        avail_lbl.get_style_context().add_class("title-4")
        avail_lbl.set_xalign(0)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        add_txn_btn = Gtk.Button.new_with_label("Add transaction")
        edit_toggle = Gtk.CheckButton(label="Edit order")
        toolbar.append(add_txn_btn)
        toolbar.append(edit_toggle)
        # Initialize from sticky state and keep it updated
        edit_toggle.set_active(self._edit_order_active)
        def _persist_toggle_state(w):
            self._edit_order_active = bool(w.get_active())
        edit_toggle.connect("toggled", _persist_toggle_state)

        txn_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        txn_list.set_hexpand(True)
        txn_list.set_vexpand(True)

        self.main_area.append(title)
        self.main_area.append(posted_lbl)
        self.main_area.append(avail_lbl)
        self.main_area.append(toolbar)
        self.main_area.append(txn_list)

        def load_txns():
            self.clear_box(txn_list)
            # Start running balance from current Available balance
            run_bal = Decimal(avail)
            for r in self.db.list_transactions(account_id):
                rowbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                rowbox.set_hexpand(True)
                # Attach drag source and drop target for drag-to-reorder
                tid = int(r.get("id"))

                def _drag_prepare(_src, _x, _y, _tid=tid):
                    # Provide the transaction id as a string payload
                    return Gdk.ContentProvider.new_for_value(str(_tid))

                src = Gtk.DragSource()
                src.set_actions(Gdk.DragAction.MOVE)
                src.connect("prepare", _drag_prepare)
                rowbox.add_controller(src)

                def _on_drop(_target, value, _x, _y, _drop_tid=tid, _aid=account_id):
                    # Only allow reordering when Edit order is active
                    # value is the source transaction id as a string
                    try:
                        src_tid = int(value)
                    except Exception:
                        return False
                    if not edit_toggle.get_active():
                        return False
                    if src_tid == _drop_tid:
                        return False
                    # Move src before the drop target
                    self.db.move_txn_before(_aid, src_tid, _drop_tid)
                    self.reload_sidebar()
                    self.show_account(_aid)
                    return True

                tgt = Gtk.DropTarget.new(str, Gdk.DragAction.MOVE)
                tgt.connect("drop", _on_drop)
                rowbox.add_controller(tgt)

                left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                right = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                right.set_halign(Gtk.Align.END)
                right.set_hexpand(True)

                date_s = (r.get("occurred_on") or "")
                nm = r.get("name") or ""

                title = Gtk.Label(label=f"{date_s} — {nm}")
                title.set_xalign(0)
                title.set_wrap(True)
                title.set_wrap_mode(Pango.WrapMode.WORD_CHAR)

                sub = Gtk.Label(label=f"{r.get('ttype') or ''} · {r.get('method') or ''}")
                sub.get_style_context().add_class("dim-label")
                sub.set_xalign(0)

                left.append(title)
                left.append(sub)

                amount = Decimal(r.get("amount") or 0)
                # Amount label
                amt = Gtk.Label(label=fmt_money(amount, CURRENCY_SYMBOL))
                amt.set_xalign(1.0)
                if amount < 0:
                    amt.get_style_context().add_class("error")
                else:
                    amt.get_style_context().add_class("success")
                # Running balance label (balance after this transaction)
                rb = Gtk.Label(label=f"{fmt_money(run_bal, CURRENCY_SYMBOL)}")
                rb.get_style_context().add_class("dim-label")
                rb.set_xalign(1.0)
                amt_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
                amt_box.append(amt)
                amt_box.append(rb)
                right.append(amt_box)

                pend = Gtk.CheckButton(label="Pending")
                pend.set_active(bool(int(r.get("pending") or 0)))

                def on_pend_toggled(w):
                    self.db.set_txn_pending(tid, w.get_active())
                    self.reload_sidebar()
                    self.show_account(account_id)

                pend.connect("toggled", on_pend_toggled)
                right.append(pend)

                up = Gtk.Button.new_with_label("▲")
                down = Gtk.Button.new_with_label("▼")
                up.connect(
                    "clicked",
                    lambda _b, aid=account_id, tid=tid: (
                        self.db.move_txn_up(aid, tid),
                        self.reload_sidebar(),
                        self.show_account(aid),
                    ),
                )
                down.connect(
                    "clicked",
                    lambda _b, aid=account_id, tid=tid: (
                        self.db.move_txn_down(aid, tid),
                        self.reload_sidebar(),
                        self.show_account(aid),
                    ),
                )

                def _toggle(_t, u=up, d=down):
                    vis = edit_toggle.get_active()
                    u.set_visible(vis)
                    d.set_visible(vis)

                edit_toggle.connect("toggled", _toggle)
                # Respect sticky state for initial visibility
                up.set_visible(edit_toggle.get_active())
                down.set_visible(edit_toggle.get_active())
                right.append(up)
                right.append(down)

                # Double-click to edit
                def _on_pressed(gesture, n_press, x, y, _txn=r):
                    if n_press == 2:
                        EditTransactionDialog(
                            self,
                            self.db,
                            account_id,
                            _txn,
                            on_saved=lambda: (self.reload_sidebar(), self.show_account(account_id)),
                        ).show()

                click = Gtk.GestureClick()
                click.set_button(0)  # any button; 0 means any
                click.connect("pressed", _on_pressed)
                rowbox.add_controller(click)

                rowbox.append(left)
                rowbox.append(right)
                txn_list.append(rowbox)

                # Move to next older transaction: remove current amount effect
                run_bal -= amount

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

    # ---------- Actions ----------

    def _on_add_account(self, *_):
        AddAccountDialog(
            self,
            self.db,
            on_created=lambda: (self.reload_sidebar(), self.show_summary()),
        ).show()

    def _show_about(self, *_):
        # Prefer Adw.AboutWindow when available; fallback to Gtk.AboutDialog for older libadwaita
        AboutWin = getattr(Adw, "AboutWindow", None)
        if AboutWin is not None:
            LicenseEnum = getattr(Adw, "License", None)
            license_type = getattr(LicenseEnum, "APACHE_2_0", None)
            if license_type is None:
                # Fallback to Gtk license enum if Adw.License is missing
                license_type = Gtk.License.APACHE_2_0
            about = AboutWin(
                application_name="MyLedger",
                version="0.1.0",
                developer_name="James McDermott",
                comments="This application was generated in part with the help of an AI LLM.",
                license_type=license_type,
                website="https://github.com/mcdz89/MyLedger_gpt",
            )
            about.set_transient_for(self)
            about.present()
            return

        # GTK fallback
        about = Gtk.AboutDialog(
            program_name="MyLedger",
            version="0.1.0",
            comments="This application was generated in part with the help of an AI LLM.",
            website="https://github.com/mcdz89/MyLedger_gpt",
            license_type=Gtk.License.APACHE_2_0,
            authors=["James McDermott"],
        )
        about.set_transient_for(self)
        about.present()
