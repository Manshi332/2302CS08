"""Exception types.

WalletError : base class (kept from Assignments 3/4 so the reused modules work as-is).
LedgerError : a rejected transaction (Assignment 4), with a stable ``code``.
BlockError  : a rejected block (Assignment 5), with a stable ``code``, a human
              reason and, when a transaction inside the block was the culprit,
              the ``inner`` ledger code (e.g. "bad_signature").
"""

from __future__ import annotations

from typing import Optional


class WalletError(Exception):
    """Raised for any rejected input; the CLI prints it and exits with status 1."""


class LedgerError(WalletError):
    def __init__(self, code: str, reason: str):
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason


class BlockError(WalletError):
    def __init__(self, code: str, reason: str, inner: Optional[str] = None):
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason
        self.inner = inner
