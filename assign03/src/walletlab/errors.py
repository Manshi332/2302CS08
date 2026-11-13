"""One exception type for every user-facing failure."""


class WalletError(Exception):
    """Raised for any rejected input; the CLI prints it and exits with status 1."""
