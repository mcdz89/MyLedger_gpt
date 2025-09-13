from __future__ import annotations
import os
from dotenv import load_dotenv
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

from app.db import Database
from app.ui.main_window import MainWindow

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set. Add it to .env")

def main():
    app = Adw.Application(application_id="com.example.fintrack.py")
    db = Database(DATABASE_URL)
    def on_activate(app: Adw.Application):
        win = MainWindow(app, db); win.present()
    app.connect("activate", on_activate)
    app.run()

if __name__ == "__main__":
    main()
