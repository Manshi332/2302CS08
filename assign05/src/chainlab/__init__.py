"""chainlab: blocks, toy Proof of Work, fork choice by cumulative work, reorganisation (Assignment 5).

Builds on utxolab (Assignment 4): the transaction validator, wallet and ledger are reused
unchanged; this package adds block headers, mining, a chain manager and reorgs.
"""

__version__ = "1.0.0"

from .block import Block, BlockHeader, hexdump_header  # noqa: F401
from .chain import AddResult, Chain  # noqa: F401
from .consensus import ChainParams  # noqa: F401
from .errors import BlockError, LedgerError, WalletError  # noqa: F401
from .miner import make_block, mine_block, solve_block  # noqa: F401
from .state import ChainLedger  # noqa: F401
from .wallet import Wallet  # noqa: F401
