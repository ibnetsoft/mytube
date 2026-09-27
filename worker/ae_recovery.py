"""Handle After Effects' known crash-recovery dialog in interactive sessions."""
from __future__ import annotations

import os


class AeRecoveryError(RuntimeError):
    pass


def _is_afterfx_process(pid: int) -> bool:
    import win32api
    import win32con
    import win32process

    try:
        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        try:
            return os.path.basename(win32process.GetModuleFileNameEx(handle, 0)).lower() == 'afterfx.exe'
        finally:
            handle.Close()
    except Exception:
        return False


def continue_crash_recovery() -> bool:
    """Click AE's exact recovery Continue button, leaving other dialogs alone."""
    if os.name != 'nt':
        return False
    try:
        from pywinauto import Desktop
    except ImportError as exc:
        raise AeRecoveryError('pywinauto is required for unattended AE recovery') from exc

    try:
        windows = Desktop(backend='uia').windows()
    except Exception as exc:
        raise AeRecoveryError('Could not inspect the interactive Windows desktop for AE recovery') from exc

    for window in windows:
        try:
            pid = window.process_id()
        except Exception:
            continue
        if not _is_afterfx_process(pid):
            continue
        try:
            descendants = window.descendants()
            labels = [window.window_text().strip()]
            labels.extend(item.window_text().strip() for item in descendants)
        except Exception:
            continue
        if not any('충돌 복구 옵션' in label or 'Crash Recovery Options' in label for label in labels):
            continue
        buttons = [item for item in descendants
                   if item.element_info.control_type == 'Button'
                   and item.window_text().strip() in {'계속', 'Continue'}]
        if len(buttons) != 1:
            raise AeRecoveryError(
                f'AE crash-recovery dialog (pid={pid}) is open but its Continue button is unavailable'
            )
        try:
            buttons[0].invoke()
        except Exception as exc:
            raise AeRecoveryError(f'Could not continue the AE crash-recovery dialog (pid={pid})') from exc
        return True
    return False
