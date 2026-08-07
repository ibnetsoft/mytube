"""
AIR Worker OS 알림 래퍼.

Windows 10/11 네이티브 알림(win10toast)을 우선 사용하고,
실패 시 pystray 내장 notify로 폴백합니다.

worker/ 전용 — services/tray_notification.py(메인 앱용)과는 독립적입니다.
"""
from __future__ import annotations

import os
import threading
import time
from logging_setup import get_logger
from typing import Optional

logger = get_logger("tray_notification")


class TrayNotification:
    """OS 수준 데스크탑 알림 관리자 (Worker 전용)."""

    MIN_INTERVAL = 3.0

    def __init__(self):
        self._notifier: Optional[object] = None
        self._last_notify_time: float = 0.0
        self._lock = threading.Lock()

        # 알림 설정 토글
        self.notify_render_complete_enabled = True
        self.notify_render_failed_enabled = True
        self.notify_hermes_complete_enabled = True
        self.notify_hermes_failed_enabled = True
        self.notify_batch_render_complete_enabled = True
        self.notify_autopilot_complete_enabled = True

        self._init_notifier()

    def _init_notifier(self):
        """가장 좋은 알림 백엔드 초기화."""
        try:
            import win10toast
            self._notifier = win10toast.ToastNotifier()
            logger.info("win10toast 초기화 성공")
            return
        except Exception:
            pass

        try:
            import win10toast_persist
            self._notifier = win10toast_persist.ToastNotifier()
            logger.info("win10toast_persist 초기화 성공")
            return
        except Exception:
            pass

        logger.info("win10toast를 사용할 수 없습니다. pystray.notify를 폴백으로 사용합니다.")

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
        """데스크탑 알림 표시."""
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
        """실제 알림 발송 (워커 스레드에서 실행)."""
        try:
            if self.has_native_notifier:
                kwargs = {
                    "title": title,
                    "msg": message,
                    "duration": duration,
                }
                if icon_path and os.path.exists(icon_path):
                    kwargs["icon_path"] = icon_path
                self._notifier.show_toast(**kwargs)
            else:
                logger.info(f"[알림] {title}: {message}")
        except Exception as e:
            logger.error(f"알림 발송 실패: {e}")

    def notify_with_callback(
        self,
        title: str,
        message: str,
        callback: callable,
        icon_path: Optional[str] = None,
    ):
        """알림 표시 + 클릭 시 콜백 (win10toast만 지원)."""
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
                logger.error(f"callback 알림 실패: {e}")
        return False

    # ── 편의 메서드 ──

    def notify_render_complete(self, project_name: str, callback=None):
        if not self.notify_render_complete_enabled:
            return
        title = "AIR Worker"
        msg = f'"{project_name}" 렌더링 완료'
        if callback:
            self.notify_with_callback(title, msg, callback)
        else:
            self.notify(title, msg)

    def notify_render_failed(self, project_name: str, callback=None):
        if not self.notify_render_failed_enabled:
            return
        title = "AIR Worker"
        msg = f'"{project_name}" 렌더링 실패'
        if callback:
            self.notify_with_callback(title, msg, callback)
        else:
            self.notify(title, msg)

    def notify_batch_render_complete(self, count: int):
        if not self.notify_batch_render_complete_enabled:
            return
        title = "AIR Worker"
        msg = f"{count}개 프로젝트 렌더링 완료"
        self.notify(title, msg)

    def notify_hermes_complete(self, job_type: str):
        if not self.notify_hermes_complete_enabled:
            return
        type_label = {
            "topic_research": "토픽 리서치",
            "topic_benchmark_analyze": "벤치마크 분석",
            "script_plan_generate": "스크립트 기획",
            "script_generate": "스크립트 생성",
        }.get(job_type, job_type)
        title = "AIR Worker"
        msg = f"Hermes: {type_label} 완료"
        self.notify(title, msg)

    def notify_hermes_failed(self, job_type: str):
        if not self.notify_hermes_failed_enabled:
            return
        type_label = {
            "topic_research": "토픽 리서치",
            "topic_benchmark_analyze": "벤치마크 분석",
            "script_plan_generate": "스크립트 기획",
            "script_generate": "스크립트 생성",
        }.get(job_type, job_type)
        title = "AIR Worker"
        msg = f"Hermes: {type_label} 실패"
        self.notify(title, msg)

    def notify_autopilot_complete(self, topic: str):
        if not self.notify_autopilot_complete_enabled:
            return
        title = "AIR Worker"
        msg = f'AutoPilot: "{topic}" 영상 제작 완료'
        self.notify(title, msg)


# ── 모듈 수준 싱글톤 ──

tray_notification = TrayNotification()
