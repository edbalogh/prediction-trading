from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from safety.types import OrphanEvent

_DEFAULT_LOG_PATH = "data/quarantine.jsonl"


class QuarantineBook:
    def __init__(self, log_path: str = _DEFAULT_LOG_PATH) -> None:
        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._quarantined_tickers: set[str] = set()
        self._events: list[OrphanEvent] = []
        self._load_existing()

    def append(self, event: OrphanEvent) -> None:
        self._events.append(event)
        self._quarantined_tickers.add(event.ticker)
        with self._path.open("a") as f:
            f.write(json.dumps(dataclasses.asdict(event)) + "\n")

    def get_all(self) -> list[OrphanEvent]:
        return list(self._events)

    def is_quarantined(self, ticker: str) -> bool:
        return ticker in self._quarantined_tickers

    def _load_existing(self) -> None:
        if not self._path.exists():
            return
        with self._path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    event = OrphanEvent(**data)
                    self._events.append(event)
                    self._quarantined_tickers.add(event.ticker)
                except Exception:
                    pass
