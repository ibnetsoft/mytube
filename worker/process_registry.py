"""
[AIR-0227A Stage 12] PID/status tracking + bounded auto-restart.

docs/AIR_WORKER_PROCESS_MODEL.md §3.
"""
import time
from dataclasses import dataclass, field
from typing import Optional

from worker_config import CRASH_WINDOW_SECONDS, MAX_CRASHES_IN_WINDOW


@dataclass
class ProcessRecord:
    name: str
    pid: Optional[int] = None
    status: str = "stopped"          # stopped|starting|running|crashed|disabled
    started_at: Optional[float] = None
    last_heartbeat_at: Optional[float] = None
    crash_timestamps: list = field(default_factory=list)
    restart_count_total: int = 0
    disabled_reason: Optional[str] = None
    last_error: Optional[str] = None

    def record_crash(self, error: str = "") -> bool:
        """Records a crash. Returns True if the process should still be
        allowed to auto-restart, False if it must be disabled
        (docs/AIR_WORKER_PROCESS_MODEL.md §3: 'repeated crashes -> disable
        only that module, report status')."""
        now = time.time()
        self.crash_timestamps = [t for t in self.crash_timestamps if now - t < CRASH_WINDOW_SECONDS]
        self.crash_timestamps.append(now)
        self.last_error = error
        self.status = "crashed"
        if len(self.crash_timestamps) >= MAX_CRASHES_IN_WINDOW:
            self.status = "disabled"
            self.disabled_reason = (
                f"{len(self.crash_timestamps)} crashes within "
                f"{CRASH_WINDOW_SECONDS}s (limit {MAX_CRASHES_IN_WINDOW})"
            )
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "pid": self.pid,
            "status": self.status,
            "started_at": self.started_at,
            "last_heartbeat_at": self.last_heartbeat_at,
            "crash_count_window": len(self.crash_timestamps),
            "restart_count_total": self.restart_count_total,
            "disabled_reason": self.disabled_reason,
            "last_error": self.last_error,
        }


class ProcessRegistry:
    """In-memory registry of all managed processes. Not persisted across
    Manager restarts in this skeleton (docs/AIR_WORKER_PROCESS_MODEL.md §3
    notes a local state file as a future enhancement for post-restart
    history - out of scope for this pass)."""

    def __init__(self):
        self._records: dict[str, ProcessRecord] = {}

    def register(self, name: str) -> ProcessRecord:
        if name not in self._records:
            self._records[name] = ProcessRecord(name=name)
        return self._records[name]

    def get(self, name: str) -> Optional[ProcessRecord]:
        return self._records.get(name)

    def all(self) -> dict[str, ProcessRecord]:
        return dict(self._records)

    def to_dict(self) -> dict:
        return {name: rec.to_dict() for name, rec in self._records.items()}
