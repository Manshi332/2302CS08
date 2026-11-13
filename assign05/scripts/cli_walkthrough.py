"""End-to-end CLI session (cross-platform). Writes everything into examples/walkthrough/.

    python scripts/cli_walkthrough.py

It creates a chain, mines two blocks, pays Bob, mines the payment, then mines a competing
two-block branch from block 2 and shows the reorganisation, the tree, and a header dump.
"""

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "examples", "walkthrough")
ENV = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"), PYTHONIOENCODING="utf-8")


def run(*args: str) -> str:
    print("$ chainlab " + " ".join(os.path.basename(a) if os.sep in a else a for a in args))
    proc = subprocess.run([sys.executable, "-m", "chainlab", *args], capture_output=True, text=True,
                          env=ENV, cwd=OUT)
    for stream in (proc.stdout, proc.stderr):
        if stream.strip():
            print("  " + stream.strip().replace("\n", "\n  "))
    if proc.returncode:
        sys.exit(f"command failed with exit code {proc.returncode}")
    print()
    return proc.stdout


def main() -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    alice = run("address", "alice").strip()
    bob = run("address", "bob").strip()
    carol = run("address", "carol").strip()
    run("init", "chain.json", "--bits", "6")
    run("mine", "--chain", "chain.json", "--address", alice, "--timestamp", "1700000600")
    run("mine", "--chain", "chain.json", "--address", alice, "--timestamp", "1700001200")
    run("pay", "--chain", "chain.json", "--from", "alice", "--to", bob, "--amount", "30", "--fee", "1",
        "--out", "pay.json")
    out = run("mine", "--chain", "chain.json", "--address", carol, "--tx", "pay.json",
              "--timestamp", "1700001800", "--out", "block3_main.json")
    run("info", "--chain", "chain.json", "--names", "alice", "bob", "carol", "--tree")
    parent = subprocess.run([sys.executable, "-c",
        "import sys; sys.path.insert(0, sys.argv[1]); from chainlab import Chain; "
        "print(Chain.load('chain.json').block_at(2).hash.hex())", os.path.join(ROOT, "src")],
        capture_output=True, text=True, cwd=OUT, env=ENV).stdout.strip()
    out = run("mine", "--chain", "chain.json", "--address", bob, "--parent", parent,
              "--timestamp", "1700001801", "--out", "block3_rival.json")
    rival = out.split("mined block ")[1].split()[0]
    run("mine", "--chain", "chain.json", "--address", bob, "--parent", rival, "--out", "block4_rival.json")
    run("info", "--chain", "chain.json", "--names", "alice", "bob", "carol", "--tree")
    run("dump-header", "block3_main.json")
    print(f"everything was written to {OUT}")


if __name__ == "__main__":
    main()
