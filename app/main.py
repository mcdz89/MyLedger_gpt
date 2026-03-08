# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations
import os
import gi
try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv() -> None:
        return

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

from app.db import Database
from app.ui.main_window import MainWindow

load_dotenv()

DATABASE_PATH = os.getenv("DATABASE_PATH", "db/myledger.sqlite3")

def main():
    app = Adw.Application(application_id="com.example.myledger.py")
    db = Database(DATABASE_PATH)
    def on_activate(app: Adw.Application):
        win = MainWindow(app, db); win.present()
    app.connect("activate", on_activate)
    app.run()

if __name__ == "__main__":
    main()
