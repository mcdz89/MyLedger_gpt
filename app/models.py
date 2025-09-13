from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from datetime import date

@dataclass(slots=True)
class Account:
    id: int
    institution: str
    type: int
    acc_id: str  # user-visible account name
    active: str  # 'YES'/'NO'
    balance: Decimal
    interest: str  # 'YES'/'NO'
    apy: int | None
    opened: date
    day: int
    month: int
    year: int

@dataclass(slots=True)
class Transaction:
    id: int
    c_id: int
    acc_id: int
    pending: int  # 1/0
    type: int
    name: str
    method: int
    cat: int
    amount: Decimal
    balance: Decimal
    date: date
    day: int
    month: int
    year: int
