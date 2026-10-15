"""Best-effort, append-only stage timings; never change media job outcomes."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time
import uuid

_lock = threading.Lock()


def _append(path, row):
    try:
        with _lock:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    except Exception:
        pass  # Observability must never interrupt generation or mask its error.


@contextmanager
def stage_timing(path, stage, **context):
    event_id = uuid.uuid4().hex
    start = time.monotonic()
    def emit(event, **extra):
        _append(path, {**context, 'stage': stage, 'event': event, 'event_id': event_id,
                       'timestamp': datetime.now(timezone.utc).isoformat(), **extra})
    emit('start')
    outcome = 'ok'
    try:
        yield
    except BaseException:
        outcome = 'error'
        raise
    finally:
        emit('end', outcome=outcome, elapsed_seconds=round(time.monotonic() - start, 6))
