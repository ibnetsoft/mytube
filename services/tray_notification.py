"""
AIR Studio OS 알림 래퍼
Windows 10/11 네이티브 알림(win10toast)을 우선 사용하고,
실패 시 pystray 내장 notify로 폴백합니다.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from typing import Optional

# 프로젝트 모듈 경로 확보
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)


class TrayNotification:
    """OS 수준 데스크탑 알림 관리자"""

    # 알림 표시 간 최소 간격 (초) — 연속 알림 스팸 방지
    MIN_INTERVAL = 3.0

    def __init__(self):
        self._notifier: Optional[object] = None
        self._last_notify_time: float = 0.0
        self._lock = threading.Lock()

        # 알림 설정 토글
        self.notify_render_complete = True
        self.notify_render_failed = True
        self.notify_hermes_complete = True
        self.notify_hermes_failed = True
        self.notify_autopilot_complete = True

        # win10toast 초기화 시도
        self._init_notifier()

    def _init_notifier(self):
        """가장 좋은 알림 백엔드 초기화"""
        # 1순위: win10toast (Windows 10/11 네이티브 알림)
        try:
            import win10toast
            self._notifier = win10toast.ToastNotifier()
            print("[TrayNotification] win10toast 초기화 성공")
            return
        except Exception:
            pass

        # 2순위: win10toast_persist (개선된 포크)
        try:
            import win10toast_persist
            self._notifier = win10toast_persist.ToastNotifier()
            print("[TrayNotification] win10toast_persist 초기화 성공")
            return
        except Exception:
            pass

        print("[TrayNotification] win10toast를 사용할 수 없습니다. "
              "pystray.notify를 폴백으로 사용합니다.")

    @property
    def has_native_notifier(self) -> bool:
        return self._notifier is not None

    def notify(
        self,
        title: str,
        message: str,
        icon_path: Optional[str] = None,
        duration: int = 5,
        threaded: bool = True,
    ):
        """
        데스크탑 알림 표시

        Args:
            title: 알림 제목
            message: 알림 본문
            icon_path: 알림 아이콘 파일 경로 (.ico)
            duration: 알림 표시 시간 (초)
            threaded: 비동기 표시 여부 (UI 스레드 블로킹 방지)
        """
        # 최소 간격 체크
        with self._lock:
            now = time.time()
            if now - self._last_notify_time < self.MIN_INTERVAL:
                return
            self._last_notify_time = now

        if threaded:
            threading.Thread(
                target=self._send_notification,
                args=(title, message, icon_path, duration),
                daemon=True,
            ).start()
        else:
            self._send_notification(title, message, icon_path, duration)

    def _send_notification(
        self,
        title: str,
        message: str,
        icon_path: Optional[str],
        duration: int,
    ):
        """실제 알림 발송 (워커 스레드에서 실행)"""
        try:
            if self.has_native_notifier:
                # win10toast 네이티브 알림
                kwargs = {
                    "title": title,
                    "msg": message,
                    "duration": duration,
                }
                if icon_path and os.path.exists(icon_path):
                    kwargs["icon_path"] = icon_path
                self._notifier.show_toast(**kwargs)
            else:
                # pystray 폴백 — pystray.notify()는 pystray.Icon이 필요하므로
                # 여기서는 간단히 콘솔 출력만 (실제 폴백은 tray_service에서 처리)
                print(f"[알림] {title}: {message}")
        except Exception as e:
            print(f"[TrayNotification] 알림 발송 실패: {e}")

    def notify_with_callback(
        self,
        title: str,
        message: str,
        callback: callable,
        icon_path: Optional[str] = None,
    ):
        """알림 표시 + 클릭 시 콜백 (win10toast만 지원)"""
        if self.has_native_notifier:
            try:
                kwargs = {
                    "title": title,
                    "msg": message,
                    "duration": 5,
                    "callback": callback,
                }
                if icon_path and os.path.exists(icon_path):
                    kwargs["icon_path"] = icon_path
                self._notifier.show_toast(**kwargs)
                return True
            except Exception as e:
                print(f"[TrayNotification] callback 알림 실패: {e}")
        return False

    # ── 편의 메서드 ──

    def notify_render_complete(self, project_name: str, callback=None):
        if not self.notify_render_complete:
            return
        title = "AIR Studio"
        msg = f'"{project_name}" 렌더링 완료'
        if callback:
            self.notify_with_callback(title, msg, callback)
        else:
            self.notify(title, msg)

    def notify_render_failed(self, project_name: str, callback=None):
        if not self.notify_render_failed:
            return
        title = "AIR Studio"
        msg = f'"{project_name}" 렌더링 실패'
        if callback:
            self.notify_with_callback(title, msg, callback)
        else:
            self.notify(title, msg)

    def notify_batch_render_complete(self, count: int):
        title = "AIR Studio"
        msg = f"{count}개 프로젝트 렌더링 완료"
        self.notify(title, msg)

    def notify_hermes_complete(self, job_type: str):
        if not self.notify_hermes_complete:
            return
        type_label = "토픽 리서치" if job_type == "topic_research" else "벤치마크 분석"
        title = "AIR Studio"
        msg = f"Hermes: {type_label} 완료"
        self.notify(title, msg)

    def notify_hermes_failed(self, job_type: str):
        if not self.notify_hermes_failed:
            return
        type_label = "토픽 리서치" if job_type == "topic_research" else "벤치마크 분석"
        title = "AIR Studio"
        msg = f"Hermes: {type_label} 실패"
        self.notify(title, msg)

    def notify_autopilot_complete(self, topic: str):
        if not self.notify_autopilot_complete:
            return
        title = "AIR Studio"
        msg = f'AutoPilot: "{topic}" 영상 제작 완료'
        self.notify(title, msg)


# ── 모듈 수준 싱글톤 ──

tray_notification = TrayNotification()
