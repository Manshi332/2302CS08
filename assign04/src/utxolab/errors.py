"""Exception types.

WalletError  : base class (kept from Assignment 3 so the reused modules work as-is).
LedgerError  : a rejected transaction / snapshot. Carries a stable machine-readable
               ``code`` plus a human-readable reason, so a trace can show *why*.
"""


class WalletError(Exception):
    """Raised for any rejected input; the CLI prints it and exits with status 1."""


class LedgerError(WalletError):
    def __init__(self, code: str, reason: str):
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason
