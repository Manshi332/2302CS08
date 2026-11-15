import argparse
import asyncio
import sys

from chainlab import ChainParams

from .experiment import run
from .log import EventLog
from .node import Node


async def _serve(args) -> None:
    node = Node(args.id, ChainParams(bits=args.bits), port=args.port, log=EventLog(args.log, echo=True))
    await node.start()
    for s in args.seed:
        host, port = s.rsplit(":", 1)
        node.seeds.append((host, int(port)))
        await node.connect(host, int(port))
    while True:
        await asyncio.sleep(args.mine_every or 3600)
        if args.mine_every and args.mine_address:
            node.mine(args.mine_address)


def main() -> None:
    ap = argparse.ArgumentParser(prog="p2plab")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("experiment", help="run the partition / heal experiment with 5 nodes")
    e.add_argument("--out", default="logs/experiment.jsonl")
    n = sub.add_parser("node", help="run one node")
    n.add_argument("--id", required=True)
    n.add_argument("--port", type=int, default=0)
    n.add_argument("--bits", type=int, default=4)
    n.add_argument("--seed", action="append", default=[], help="host:port of a peer to bootstrap from")
    n.add_argument("--log", default=None)
    n.add_argument("--mine-every", type=float, default=0, help="mine a block every N seconds")
    n.add_argument("--mine-address", default=None)
    args = ap.parse_args()
    try:
        if args.cmd == "experiment":
            asyncio.run(run(args.out))
        else:
            asyncio.run(_serve(args))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
