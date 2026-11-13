"""merklelab: a from-scratch Merkle tree library (SHA-256, domain separated)."""

from .hashing import EMPTY_ROOT, MerkleError, hash_leaf, hash_node
from .proof import Proof, ProofError, ProofFormatError, Sibling, expected_sides, verify
from .tree import MerkleTree, merkle_root

__version__ = "1.0.0"
__all__ = [
    "EMPTY_ROOT", "MerkleError", "hash_leaf", "hash_node",
    "Proof", "ProofError", "ProofFormatError", "Sibling", "expected_sides", "verify",
    "MerkleTree", "merkle_root",
]
