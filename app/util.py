from __future__ import annotations
from decimal import Decimal
import os

CURRENCY_SYMBOL = os.getenv("CURRENCY_SYMBOL", "$")

def fmt_money(val: Decimal, symbol: str | None = None) -> str:
    symbol = symbol or CURRENCY_SYMBOL
    if not isinstance(val, Decimal):
        val = Decimal(str(val))
    q = val.quantize(Decimal("0.01"))
    s = f"{abs(q):.2f}"
    int_part, frac = s.split(".")
    grouped = "".join(reversed([ ("," if i and i%3==0 else "") + c for i,c in enumerate(reversed(int_part)) ]))
    sign = "-" if q < 0 else ""
    return f"{sign}{symbol}{grouped}.{frac}"
