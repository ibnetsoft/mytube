"""
AIR Worker 시스템 트레이 앱.

pystray를 사용하여 시스템 트레이 아이콘을 표시하고,
컨텍스트 메뉴를 통해 상태 확인, 알림 설정, 종료를 제어합니다.

이 모듈은 Manager 프로세스(main.py)와 같은 프로세스에서 daemon 스레드로 실행됩니다.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from logging_setup import get_logger

if TYPE_CHECKING:
    from manager import WorkerManager

logger = get_logger("tray_app")


def _find_icon_path() -> Optional[str]:
    """트레이 아이콘(.ico) 경로 탐색.

    PyInstaller frozen 빌드 → sys._MEIPASS/static/img/air_studio.ico
    소스 실행      → 프로젝트 루트/static/img/air_studio.ico
    """
    # frozen 빌드: PyInstaller가 --add-data로 번들한 경로
    if getattr(sys, "frozen", False):
        bundle = Path(sys._MEIPASS)
        ico = bundle / "static" / "img" / "air_studio.ico"
        if ico.exists():
            return str(ico)

    # 소스 실행: worker/의 부모가 프로젝트 루트
    from worker_config import PROJECT_ROOT
    ico = PROJECT_ROOT / "static" / "img" / "air_studio.ico"
    if ico.exists():
        return str(ico)

    # 데이터 디렉토리 (onedir 설치 시)
    from worker_config import BASE_DIR
    ico = BASE_DIR / "static" / "img" / "air_studio.ico"
    if ico.exists():
        return str(ico)

    return None


def _load_icon_image(icon_path: Optional[str]):
    """pystray용 아이콘 이미지 로드."""
    try:
        from PIL import Image
        if icon_path and os.path.exists(icon_path):
            return Image.open(icon_path)
    except Exception as e:
        logger.warning(f"아이콘 이미지 로드 실패: {e}")

    # 폴백: 기본 파란색 정사각형
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (64, 64), (0, 120, 215, 255))
        draw = ImageDraw.Draw(img)
        draw.text((16, 20), "AW", fill=(255, 255, 255, 255))
        return img
    except Exception:
        return None


class TrayApp:
    """AIR Worker 시스템 트레이 앱.

    Manager 프로세스에서 daemon 스레드로 실행됩니다.

    Usage:
        tray = TrayApp(manager)
        tray.start()
        ...
        tray.stop()
    """

    def __init__(self, manager: WorkerManager):
        self._manager = manager
        self._icon = None
        self._icon_thread: Optional[threading.Thread] = None
        self._icon_path = _find_icon_path()
        self._running = False
        self._menu_lock = threading.Lock()

        # 상태 수집기 + 알림
        from tray_status_collector import TrayStatusCollector
        from tray_notification import tray_notification

        self._collector = TrayStatusCollector(poll_interval=3.0)
        self._notification = tray_notification

    def _build_status_text(self) -> str:
        """상태 메뉴 항목 텍스트 생성."""
        snap = self._collector.latest
        parts = ["📊 AIR Worker"]

        # 렌더 워커
        rw = snap.processes.get("render_worker")
        if rw:
            if rw.status == "running" and rw.progress is not None:
                parts.append(f"  렌더: {rw.progress}%")
            elif rw.status == "running":
                parts.append("  렌더: 작업 중")
            elif rw.status == "disabled":
                parts.append(f"  렌더: 비활성 ({rw.disabled_reason or ''})")
            elif rw.status == "stopped":
                parts.append("  렌더: 정지")
            else:
                parts.append(f"  렌더: {rw.status}")

        # Hermes 워커
        hw = snap.processes.get("hermes_worker")
        if hw:
            if hw.status == "running":
                parts.append("  Hermes: 작업 중")
            elif hw.status == "disabled":
                parts.append(f"  Hermes: 비활성 ({hw.disabled_reason or ''})")
            elif hw.status == "stopped":
                parts.append("  Hermes: 정지")
            else:
                parts.append(f"  Hermes: {hw.status}")
            if snap.hermes_paused:
                parts.append("  Hermes: 일시정지 (렌더 중)")

        # Local API
        la = snap.processes.get("local_api")
        if la:
            if la.status == "running":
                parts.append("  API: 실행 중")
            else:
                parts.append(f"  API: {la.status}")

        # 대기 중인 작업
        queued = [j for j in snap.active_jobs if j.status == "QUEUED"]
        if queued:
            parts.append(f"  대기: {len(queued)}개")

        return "\n".join(parts)

    def _build_menu(self, icon):
        """컨텍스트 메뉴 구성."""
        import pystray

        # 상태 (읽기 전용)
        status_text = pystray.MenuItem(
            "상태",
            None,
            enabled=False,
        )

        # 구분선
        sep1 = pystray.Menu.SEPARATOR

        # 렌더 워커 상태
        render_status = pystray.MenuItem(
            "🎬 렌더 워커",
            None,
            enabled=False,
        )

        # Hermes 워커 상태
        hermes_status = pystray.MenuItem(
            "📊 Hermes 워커",
            None,
            enabled=False,
        )

        # Local API 상태
        api_status = pystray.MenuItem(
            "🌐 Local API",
            None,
            enabled=False,
        )

        # 구분선
        sep2 = pystray.Menu.SEPARATOR

        # 알림 설정 토글
        notify_render_complete = pystray.MenuItem(
            "✅ 렌더 완료 알림",
            self._toggle_notify_render_complete,
            checked=lambda item: self._notification.notify_render_complete_enabled,
        )
        notify_render_failed = pystray.MenuItem(
            "❌ 렌더 실패 알림",
            self._toggle_notify_render_failed,
            checked=lambda item: self._notification.notify_render_failed_enabled,
        )
        notify_hermes_complete = pystray.MenuItem(
            "✅ Hermes 완료 알림",
            self._toggle_notify_hermes_complete,
            checked=lambda item: self._notification.notify_hermes_complete_enabled,
        )
        notify_hermes_failed = pystray.MenuItem(
            "❌ Hermes 실패 알림",
            self._toggle_notify_hermes_failed,
            checked=lambda item: self._notification.notify_hermes_failed_enabled,
        )

        # 구분선
        sep3 = pystray.Menu.SEPARATOR

        # 종료
        quit_item = pystray.MenuItem(
            "종료",
            self._on_quit,
        )

        return pystray.Menu(
            status_text,
            sep1,
            render_status,
            hermes_status,
            api_status,
            sep2,
            notify_render_complete,
            notify_render_failed,
            notify_hermes_complete,
            notify_hermes_failed,
            sep3,
            quit_item,
        )

    def _toggle_notify_render_complete(self, icon, item):
        self._notification.notify_render_complete_enabled = not self._notification.notify_render_complete_enabled

    def _toggle_notify_render_failed(self, icon, item):
        self._notification.notify_render_failed_enabled = not self._notification.notify_render_failed_enabled

    def _toggle_notify_hermes_complete(self, icon, item):
        self._notification.notify_hermes_complete_enabled = not self._notification.notify_hermes_complete_enabled

    def _toggle_notify_hermes_failed(self, icon, item):
        self._notification.notify_hermes_failed_enabled = not self._notification.notify_hermes_failed_enabled

    def _on_quit(self, icon, item):
        """종료 메뉴 → Manager의 graceful_shutdown 트리거."""
        logger.info("트레이 '종료' 메뉴 선택 → graceful_shutdown 요청")
        manager = self._manager
        if not manager._shutdown_started.is_set():
            manager._shutdown_started.set()
            manager._shutdown_thread = threading.Thread(
                target=lambda: manager.graceful_shutdown("트레이 종료 요청"),
                daemon=False,
                name="graceful-shutdown-tray",
            )
            manager._shutdown_thread.start()

    def _update_menu(self, snap):
        """메뉴 항목 텍스트 + tooltip 갱신."""
        if not self._icon:
            return

        try:
            import pystray
            menu = self._icon.menu
            if not menu or not menu.items:
                return

            # 메뉴 항목 인덱스 매핑:
            # 0: 상태, 1: separator, 2: 렌더, 3: Hermes, 4: API,
            # 5: separator, 6-9: 알림 토글, 10: separator, 11: 종료
            items = list(menu.items)

            # 상태 텍스트 갱신
            rw = snap.processes.get("render_worker")
            hw = snap.processes.get("hermes_worker")
            la = snap.processes.get("local_api")

            # tooltip 갱신
            self._icon.title = snap.tooltip

            # 렌더 워커 텍스트
            if len(items) > 2 and rw:
                if rw.status == "running" and rw.progress is not None:
                    items[2].text = f"🎬 렌더: {rw.progress}%"
                elif rw.status == "running":
                    items[2].text = "🎬 렌더: 작업 중"
                elif rw.status == "disabled":
                    items[2].text = f"🎬 렌더: 비활성"
                else:
                    items[2].text = f"🎬 렌더: {rw.status}"

            # Hermes 워커 텍스트
            if len(items) > 3 and hw:
                if hw.status == "running":
                    paused_tag = " (일시정지)" if snap.hermes_paused else ""
                    items[3].text = f"📊 Hermes: 작업 중{paused_tag}"
                elif hw.status == "disabled":
                    items[3].text = "📊 Hermes: 비활성"
                else:
                    items[3].text = f"📊 Hermes: {hw.status}"

            # Local API 텍스트
            if len(items) > 4 and la:
                items[4].text = f"🌐 API: {la.status if la.status else '알 수 없음'}"

        except Exception as e:
            logger.debug(f"메뉴 갱신 오류: {e}")

    def _on_snapshot_change(self, snap):
        """상태 변경 콜백 — 알림 발송 + 메뉴 갱신."""
        # 완료/실패 알림
        for job in snap.completed_jobs:
            logger.info(f"작업 완료 감지: {job.job_id} ({job.job_type})")
            if job.job_type == "render_video":
                # 작업 이름 추출 (payload에서)
                try:
                    import job_store
                    full_job = job_store.get_job(job.job_id)
                    if full_job:
                        payload = full_job.get("payload", {})
                        name = payload.get("project_name") or payload.get("source_path", job.job_id)
                        self._notification.notify_render_complete(name)
                    else:
                        self._notification.notify_render_complete(job.job_id)
                except Exception:
                    self._notification.notify_render_complete(job.job_id)
            elif job.job_type.startswith("topic_") or job.job_type in ("script_plan_generate", "script_generate"):
                self._notification.notify_hermes_complete(job.job_type)

        for job in snap.failed_jobs:
            logger.info(f"작업 실패 감지: {job.job_id} ({job.job_type})")
            if job.job_type == "render_video":
                try:
                    import job_store
                    full_job = job_store.get_job(job.job_id)
                    if full_job:
                        payload = full_job.get("payload", {})
                        name = payload.get("project_name") or payload.get("source_path", job.job_id)
                        self._notification.notify_render_failed(name)
                    else:
                        self._notification.notify_render_failed(job.job_id)
                except Exception:
                    self._notification.notify_render_failed(job.job_id)
            elif job.job_type.startswith("topic_") or job.job_type in ("script_plan_generate", "script_generate"):
                self._notification.notify_hermes_failed(job.job_type)

        # 메뉴/tooltip 갱신
        self._update_menu(snap)

    def _run_icon(self):
        """pystray 아이콘 실행 (메인 스레드에서는 호출 금지, 반드시 별도 스레드)."""
        import pystray

        icon_image = _load_icon_image(self._icon_path)
        if icon_image is None:
            logger.error("아이콘 이미지를 로드할 수 없어 트레이를 시작할 수 없습니다")
            return

        from worker_config import TRAY_ICON_NAME
        initial_snap = self._collector.poll_once()

        self._icon = pystray.Icon(
            name="air_worker_tray",
            icon=icon_image,
            title=initial_snap.tooltip,
            menu=self._build_menu(self._icon),
        )

        try:
            self._icon.run()
        except Exception as e:
            logger.error(f"pystray 이벤트 루프 오류: {e}")

    def start(self):
        """트레이 + 상태 폴링 기동 (daemon 스레드)."""
        if self._running:
            return

        self._running = True

        # 상태 수집기 기동
        self._collector.start(on_change=self._on_snapshot_change)

        # pystray 아이콘을 별도 daemon 스레드에서 실행
        self._icon_thread = threading.Thread(
            target=self._run_icon,
            daemon=True,
            name="tray-icon",
        )
        self._icon_thread.start()
        logger.info("시스템 트레이 기동 완료")

    def stop(self):
        """트레이 정리 — 반드시 graceful_shutdown 완료 후 호출."""
        self._running = False

        # 상태 수집기 정지
        self._collector.stop()

        # pystray 이벤트 루프 종료
        if self._icon:
            try:
                self._icon.stop()
            except Exception as e:
                logger.debug(f"아이콘 stop 오류: {e}")
            self._icon = None

        # 아이콘 스레드 종료 대기
        if self._icon_thread is not None:
            self._icon_thread.join(timeout=3)
            self._icon_thread = None

        logger.info("시스템 트레이 정리 완료")
