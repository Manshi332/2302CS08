"""Structured JSON-lines event log: node ID, peer ID, object ID, event, timestamp."""

from __future__ import annotations

import json
import time
from typing import Callable, Optional


class EventLog:
    def __init__(self, path: Optional[str] = None, clock: Callable[[], float] = time.time, echo: bool = False):
        self.clock, self.echo = clock, echo
        self.events: list[dict] = []
        self._fh = open(path, "w", encoding="utf-8") if path else None

    def log(self, node: str, event: str, peer: Optional[str] = None, obj: Optional[str] = None, **extra) -> None:
        rec = {"ts": round(self.clock(), 4), "node": node, "peer": peer, "object_id": obj, "event": event}
        rec.update(extra)
        self.events.append(rec)
        line = json.dumps(rec, sort_keys=True)
        if self._fh:
            self._fh.write(line + "\n")
            self._fh.flush()
        if self.echo:
            print(line)

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None
