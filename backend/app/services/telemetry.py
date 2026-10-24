"""In-memory record of what this API process relayed or rejected.

Rejected UserOperations never reach the chain, so no wallet event exists for them. This ring buffer
is the dashboard's only view of blocked attempts and is lost on restart; it is not an audit log.
"""

import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    kind: str  # "blocked_operation" or "attack"
    timestamp: int
    title: str
    detail: str
    reason: str
    outcome: str  # "blocked" or "executed"


class TelemetryLog:
    def __init__(self, capacity: int = 200) -> None:
        self._events: deque[TelemetryEvent] = deque(maxlen=capacity)

    def record(self, kind: str, title: str, detail: str, reason: str, outcome: str = "blocked") -> None:
        self._events.append(TelemetryEvent(kind, int(time.time()), title, detail, reason, outcome))

    def list(self, kind: str | None = None) -> list[dict[str, Any]]:
        return [asdict(e) for e in reversed(self._events) if kind is None or e.kind == kind]
