"""Render an isolated action probe at the next idle native-worker slot.

Never stops an existing worker or bypasses its mutex; uses the normal actual
AfterFX/aerender probe path and preserves its source/hash/decode receipts.
"""
import contextlib
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'worker'),str(ROOT/'scripts')]
import verify_wuxia_cinematic_ae as probe
from ae_mouth_runtime import instance_lock

@contextlib.contextmanager
def wait_for_native_slot(path):
    started=time.monotonic();last=-30
    while True:
        context=instance_lock(path)
        try:
            context.__enter__()
            break
        except (PermissionError,BlockingIOError):
            elapsed=time.monotonic()-started
            if elapsed>1800:
                raise TimeoutError('Existing worker kept its native slot; no render completion claimed')
            if elapsed-last>=30:
                print('ATTACK_PROBE_WAITING_EXISTING_WORKER',round(elapsed),flush=True);last=elapsed
            time.sleep(5)
    try:
        print('ATTACK_PROBE_NATIVE_SLOT_ACQUIRED',flush=True)
        yield
    finally:
        context.__exit__(None,None,None)

if __name__=='__main__':
    probe.instance_lock=wait_for_native_slot
    deadline=time.monotonic()+1800
    while True:
        try:
            probe.main()
            break
        except RuntimeError as error:
            if str(error)!='Existing aerender active; preserve it and retry':raise
            if time.monotonic()>=deadline:raise TimeoutError('Existing aerender remained active; no render completion claimed') from error
            print('ATTACK_PROBE_WAITING_EXISTING_AERENDER',flush=True)
            time.sleep(10)
