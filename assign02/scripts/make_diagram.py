"""Generate docs/proof_path_5_tx.svg: the exact proof path for leaf 2 of 5 transactions.

All hashes come from the merklelab library (and are asserted against the proof),
so the picture cannot drift from the code.   Run:  PYTHONPATH=src python scripts/make_diagram.py
"""
import pathlib
from xml.sax.saxutils import escape

from merklelab import MerkleTree, hash_leaf, hash_node, verify

ROOT = pathlib.Path(__file__).resolve().parent.parent
TX = [l.encode() for l in (ROOT / "examples" / "transactions.txt").read_text().splitlines()]
TARGET = 2

tree = MerkleTree(TX)
proof = tree.prove(TARGET)
L = [hash_leaf(t) for t in TX]
N01, N23 = hash_node(L[0], L[1]), hash_node(L[2], L[3])
N0123 = hash_node(N01, N23)
ROOTH = hash_node(N0123, L[4])
assert ROOTH == tree.root and verify(TX[TARGET], proof, tree.root)
assert [s.side for s in proof.siblings] == ["right", "left", "right"]
assert [s.hash for s in proof.siblings] == [L[3], N01, L[4]]
h1 = hash_node(L[2], L[3]); h2 = hash_node(N01, h1); h3 = hash_node(h2, L[4])
assert h1 == N23 and h2 == N0123 and h3 == ROOTH

P = lambda b: b.hex()[:8]
W, H = 1240, 700
BW, BH = 142, 46
STY = {
    "target": ("#d1fae5", "#059669", "2.5"),
    "sibling": ("#ffedd5", "#ea580c", "2.5"),
    "path": ("#dbeafe", "#2563eb", "2.5"),
    "root": ("#bfdbfe", "#1d4ed8", "3.5"),
    "plain": ("#f3f4f6", "#9ca3af", "1.2"),
    "promoted": ("#fafafa", "#9ca3af", "1.2"),
}
out = []
a = out.append
a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
  f'font-family="Helvetica, Arial, sans-serif">')
a(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
a('<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
  'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#2563eb"/></marker></defs>')
a('<text x="30" y="36" font-size="22" font-weight="bold" fill="#111827">Merkle inclusion proof for transaction #2 '
  '(leaf_index = 2) in a tree of 5 transactions</text>')
a('<text x="30" y="60" font-size="14" fill="#4b5563">SHA-256, Hleaf = H(0x00 || data), Hnode = H(0x01 || left || right). '
  'Odd node out is promoted unchanged. Hash fragments are the first 8 hex digits.</text>')

X = [100, 265, 430, 595, 760]
Y = {0: 470, 1: 340, 2: 210, 3: 100}
pos = {
    "L0": (X[0], Y[0]), "L1": (X[1], Y[0]), "L2": (X[2], Y[0]), "L3": (X[3], Y[0]), "L4": (X[4], Y[0]),
    "N01": ((X[0] + X[1]) / 2, Y[1]), "N23": ((X[2] + X[3]) / 2, Y[1]), "P4a": (X[4], Y[1]),
}
pos["N0123"] = ((pos["N01"][0] + pos["N23"][0]) / 2, Y[2])
pos["P4b"] = (X[4], Y[2])
pos["ROOT"] = ((pos["N0123"][0] + X[4]) / 2, Y[3])


def edge(c, p, style="plain"):
    (x1, y1), (x2, y2) = pos[c], pos[p]
    y1 -= BH / 2
    y2 += BH / 2
    if style == "path":
        a(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#2563eb" stroke-width="3.5" marker-end="url(#arr)"/>')
    elif style == "promo":
        a(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#9ca3af" stroke-width="1.5" stroke-dasharray="6 5"/>')
    else:
        a(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#9ca3af" stroke-width="1.5"/>')


edge("L0", "N01"); edge("L1", "N01"); edge("L3", "N23"); edge("N01", "N0123")
edge("L4", "P4a", "promo"); edge("P4a", "P4b", "promo"); edge("P4b", "ROOT")
edge("L2", "N23", "path"); edge("N23", "N0123", "path"); edge("N0123", "ROOT", "path")


def box(key, line1, line2, kind):
    x, y = pos[key]
    fill, stroke, sw = STY[kind]
    dash = ' stroke-dasharray="6 4"' if kind == "promoted" else ""
    a(f'<rect x="{x - BW / 2}" y="{y - BH / 2}" width="{BW}" height="{BH}" rx="9" fill="{fill}" '
      f'stroke="{stroke}" stroke-width="{sw}"{dash}/>')
    a(f'<text x="{x}" y="{y - 4}" font-size="14" font-weight="bold" text-anchor="middle" fill="#111827">{escape(line1)}</text>')
    a(f'<text x="{x}" y="{y + 14}" font-size="13" text-anchor="middle" fill="#374151" '
      f'font-family="Menlo, Consolas, monospace">{escape(line2)}</text>')


box("L0", "H(tx0)", P(L[0]), "plain"); box("L1", "H(tx1)", P(L[1]), "plain")
box("L2", "H(tx2)  target", P(L[2]), "target"); box("L3", "H(tx3)", P(L[3]), "sibling")
box("L4", "H(tx4)", P(L[4]), "plain")
box("N01", "N01", P(N01), "sibling"); box("N23", "N23", P(N23), "path"); box("P4a", "H(tx4) promoted", P(L[4]), "promoted")
box("N0123", "N0123", P(N0123), "path"); box("P4b", "H(tx4) promoted", P(L[4]), "sibling")
box("ROOT", "ROOT", P(ROOTH), "root")

# transaction text under leaves
for i, t in enumerate(TX):
    x = X[i]
    a(f'<text x="{x}" y="{Y[0] + 44}" font-size="13" text-anchor="middle" fill="#111827">tx{i}</text>')
    a(f'<text x="{x}" y="{Y[0] + 61}" font-size="12" text-anchor="middle" fill="#4b5563">"{escape(t.decode())}"</text>')


def badge(key, n, dx=BW / 2 - 4, dy=-BH / 2 + 2):
    x, y = pos[key]
    a(f'<circle cx="{x + dx}" cy="{y + dy}" r="13" fill="#2563eb"/>')
    a(f'<text x="{x + dx}" y="{y + dy + 5}" font-size="14" font-weight="bold" text-anchor="middle" fill="#ffffff">{n}</text>')


badge("N23", 1); badge("N0123", 2); badge("ROOT", 3)

# side tags for the sibling boxes
def tag(key, text, dx, anchor):
    x, y = pos[key]
    a(f'<text x="{x + dx}" y="{y + 5}" font-size="13" font-weight="bold" fill="#c2410c" text-anchor="{anchor}">{escape(text)}</text>')


a(f'<text x="{pos["L3"][0]}" y="{Y[0] - 36}" font-size="13" font-weight="bold" fill="#c2410c" text-anchor="middle">siblings[0] = right</text>')
a(f'<text x="{pos["N01"][0]}" y="{Y[1] - 36}" font-size="13" font-weight="bold" fill="#c2410c" text-anchor="middle">siblings[1] = left</text>')
a(f'<text x="{pos["P4b"][0]}" y="{Y[2] - 36}" font-size="13" font-weight="bold" fill="#c2410c" text-anchor="middle">siblings[2] = right</text>')
a(f'<text x="{pos["P4a"][0] - 78}" y="{Y[1] - 2}" font-size="11" fill="#6b7280" text-anchor="end">promoted up,</text>')
a(f'<text x="{pos["P4a"][0] - 78}" y="{Y[1] + 12}" font-size="11" fill="#6b7280" text-anchor="end">not re-hashed</text>')

# right panel: verification steps
px = 905
a(f'<rect x="{px - 15}" y="85" width="335" height="420" rx="10" fill="#f9fafb" stroke="#d1d5db"/>')
lines = [
    ("Verifier input: leaf bytes, proof, expected root", "b", "#111827"),
    ("", "n", ""),
    ('h0 = Hleaf("Carol pays Dave 7")', "m", "#111827"),
    (f"   = {P(L[2])}...", "m", "#374151"),
    ("", "n", ""),
    ("1  siblings[0] is RIGHT:", "b", "#2563eb"),
    (f"   h1 = Hnode(h0, H(tx3)) = {P(h1)}", "m", "#374151"),
    ("2  siblings[1] is LEFT:", "b", "#2563eb"),
    (f"   h2 = Hnode(N01, h1)   = {P(h2)}", "m", "#374151"),
    ("3  siblings[2] is RIGHT:", "b", "#2563eb"),
    (f"   h3 = Hnode(h2, H(tx4)) = {P(h3)}", "m", "#374151"),
    ("", "n", ""),
    (f"Accept iff h3 == expected root", "b", "#111827"),
    (f"             {P(ROOTH)}... == {P(ROOTH)}...  VALID", "m", "#059669"),
]
y = 112
for text, kind, color in lines:
    if kind != "n":
        fam = ' font-family="Menlo, Consolas, monospace"' if kind == "m" else ""
        wt = ' font-weight="bold"' if kind == "b" else ""
        a(f'<text x="{px}" y="{y}" font-size="13"{fam}{wt} fill="{color}" xml:space="preserve">{escape(text)}</text>')
    y += 21

a(f'<text x="{px}" y="{y + 12}" font-size="13" font-weight="bold" fill="#111827">Proof JSON (3 siblings, not 2)</text>')
y += 32
for t in ['{"leaf_index": 2, "tree_size": 5, "siblings": [',
          f'  {{"side":"right","hash":"{P(L[3])}..."}},',
          f'  {{"side":"left", "hash":"{P(N01)}..."}},',
          f'  {{"side":"right","hash":"{P(L[4])}..."}} ]}}']:
    a(f'<text x="{px}" y="{y}" font-size="12" font-family="Menlo, Consolas, monospace" fill="#374151" xml:space="preserve">{escape(t)}</text>')
    y += 18

# legend
ly = 600
items = [("target", "leaf being proven"), ("sibling", "proof sibling (given in proof)"),
         ("path", "hash the verifier recomputes"), ("root", "root to compare with"),
         ("promoted", "unpaired node passed up unchanged")]
lx = 30
for kind, label in items:
    fill, stroke, sw = STY[kind]
    dash = ' stroke-dasharray="6 4"' if kind == "promoted" else ""
    a(f'<rect x="{lx}" y="{ly}" width="26" height="18" rx="4" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{dash}/>')
    a(f'<text x="{lx + 34}" y="{ly + 14}" font-size="13" fill="#374151">{escape(label)}</text>')
    lx += 34 + 7.2 * len(label) + 22
a(f'<text x="30" y="{ly + 46}" font-size="13" fill="#4b5563">Blue arrows and numbers 1-3 show the order in which the verifier folds the leaf upward.</text>')
a(f'<text x="30" y="{ly + 64}" font-size="13" fill="#4b5563">Gray nodes are not needed: H(tx0) and H(tx1) are summarized by sibling N01; the bottom H(tx4) is the same hash as its promoted copy.</text>')
a("</svg>")

dest = ROOT / "docs" / "proof_path_5_tx.svg"
dest.parent.mkdir(exist_ok=True)
dest.write_text("\n".join(out), encoding="utf-8")
print("wrote", dest)
