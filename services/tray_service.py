"""
AIR Studio 시스템 트레이 서비스
pystray 기반 트레이 아이콘, 컨텍스트 메뉴, 상태 폴링 스레드,
알림 발송을 통합 관리합니다.
"""
from __future__ import annotations

import os
import sys
import threading
import webbrowser
from typing import Optional

# 프로젝트 모듈 경로 확보
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from config import config

# ── 전역 참조 (main.py에서 설정) ──

_icon: Optional[object] = None       # pystray.Icon 인스턴스
_icon_path: Optional[str] = None     # 트레이 아이콘 이미지 경로


def _open_webapp(icon=None, item=None):
    """웹앱 메인 페이지 열기"""
    url = f"http://{config.HOST}:{config.PORT}"
    webbrowser.open(url)


def _open_render_page(icon=None, item=None):
    """렌더링 상태 페이지 열기"""
    url = f"http://{config.HOST}:{config.PORT}/render"
    webbrowser.open(url)


def _open_autopilot_page(icon=None, item=None):
    """AutoPilot 페이지 열기"""
    url = f"http://{config.HOST}:{config.PORT}/autopilot"
    webbrowser.open(url)


def _quit_app(icon=None, item=None):
    """앱 종료 (서버 + 트레이)"""
    print("[TrayService] 사용자 요청으로 종료합니다...")
    try:
        import requests
        # FastAPI 서버 종료 엔드포인트 호출
        requests.post(
            f"http://{config.HOST}:{config.PORT}/api/shutdown",
            timeout=3,
        )
    except Exception:
        pass
    if _icon:
        _icon.stop()


def _build_menu(icon_ref) -> list:
    """
    동적 컨텍스트 메뉴 구성.
    상태에 따라 메뉴 항목 텍스트가 업데이트됩니다.
    """
    from pystray import Menu, MenuItem

    # 현재 스냅샷에서 상태 텍스트 생성
    snapshot = _get_snapshot()
    render_count = len(snapshot.active_renders) if snapshot else 0
    hermes_count = len(snapshot.active_hermes) if snapshot else 0

    # 렌더링 상태 서브메뉴
    render_items = []
    if snapshot:
        for job in snapshot.render_jobs:
            status_icon = _status_to_icon(job.status)
            label = f"{status_icon} {job.project_name} ({job.progress}%)"
            render_items.append(MenuItem(label, enabled=False))
    if not render_items:
        render_items.append(MenuItem("활성 렌더 없음", enabled=False))

    # Hermes 상태 서브메뉴
    hermes_items = []
    if snapshot:
        for job in snapshot.hermes_jobs:
            status_icon = _status_to_icon(job.status)
            label = f"{status_icon} {job.job_type} ({job.status})"
            hermes_items.append(MenuItem(label, enabled=False))
    if not hermes_items:
        hermes_items.append(MenuItem("활성 Hermes 없음", enabled=False))

    # 알림 설정 서브메뉴
    from services.tray_notification import tray_notification
    notification = tray_notification

    def _toggle_render_complete(icon=None, item=None):
        notification.notify_render_complete = not notification.notify_render_complete

    def _toggle_render_failed(icon=None, item=None):
        notification.notify_render_failed = not notification.notify_render_failed

    def _toggle_hermes_complete(icon=None, item=None):
        notification.notify_hermes_complete = not notification.notify_hermes_complete

    def _toggle_hermes_failed(icon=None, item=None):
        notification.notify_hermes_failed = not notification.notify_hermes_failed

    def _checked_attr(flag):
        """pystray Menu.checked 대신 text로 표시하는 토글 항목"""
        return lambda icon, item: setattr(notification, 'temp', True)

    notification_items = [
        MenuItem(
            _toggle_label("렌더 완료 알림", notification.notify_render_complete),
            _toggle_render_complete,
        ),
        MenuItem(
            _toggle_label("렌더 실패 알림", notification.notify_render_failed),
            _toggle_render_failed,
        ),
        MenuItem(
            _toggle_label("Hermes 완료 알림", notification.notify_hermes_complete),
            _toggle_hermes_complete,
        ),
        MenuItem(
            _toggle_label("Hermes 실패 알림", notification.notify_hermes_failed),
            _toggle_hermes_failed,
        ),
    ]

    # 전체 메뉴 구성
    menu = Menu(
        MenuItem("상태 보기 (렌더링)", _open_render_page),
        MenuItem("AutoPilot 열기", _open_autopilot_page),
        MenuItem("웹앱 열기", _open_webapp),
        Menu.SEPARATOR,
        MenuItem(
            f"렌더링 ({render_count} 활성)",
            Menu(*render_items),
        ),
        MenuItem(
            f"Hermes ({hermes_count} 활성)",
            Menu(*hermes_items),
        ),
        Menu.SEPARATOR,
        MenuItem("알림 설정", Menu(*notification_items)),
        Menu.SEPARATOR,
        MenuItem("종료", _quit_app),
    )
    return menu


def _toggle_label(text: str, enabled: bool) -> str:
    """토글 항목에 체크 표시 추가"""
    return f"{'✅' if enabled else '⬜'} {text}"


def _status_to_icon(status: str) -> str:
    """상태를 아이콘 문자로 변환"""
    mapping = {
        "rendering": "🔄",
        "completed": "✅",
        "failed": "❌",
        "pending": "⏳",
        "claimed": "🔄",
        "unknown": "❓",
    }
    return mapping.get(status, "❓")


def _get_snapshot():
    """현재 상태 스냅샷 반환"""
    try:
        from services.tray_status_collector import tray_status_collector
        return tray_status_collector.get_current_snapshot()
    except Exception:
        return None


def _on_status_change(old_snapshot, new_snapshot, changes):
    """
    상태 변경 감지 콜백.
    변경 이벤트에 따라 알림 발송 및 트레이 업데이트.
    """
    from services.tray_notification import tray_notification
    notification = tray_notification

    # ── 렌더 완료 알림 ──
    for job in changes.get("render_completed", []):
        notification.notify_render_complete(job.project_name)

    # ── 렌더 실패 알림 ──
    for job in changes.get("render_failed", []):
        notification.notify_render_failed(job.project_name)

    # ── 배치 렌더 완료 ──
    completed = changes.get("render_completed", [])
    if len(completed) >= 2:
        notification.notify_batch_render_complete(len(completed))

    # ── Hermes 완료 알림 ──
    for job in changes.get("hermes_completed", []):
        notification.notify_hermes_complete(job.job_type)

    # ── Hermes 실패 알림 ──
    for job in changes.get("hermes_failed", []):
        notification.notify_hermes_failed(job.job_type)

    # ── 트레이 아이콘 툴팁 업데이트 ──
    global _icon
    if _icon and hasattr(_icon, 'title'):
        try:
            _icon.title = new_snapshot.tooltip_text
        except Exception:
            pass

    # ── 트레이 메뉴 갱신 (다음 폴링 반영) ──
    if _icon and hasattr(_icon, 'menu'):
        try:
            _icon.menu = _build_menu(_icon)
        except Exception:
            pass


def _load_icon_image():
    """트레이 아이콘 이미지 로드 (PIL Image)"""
    global _icon_path

    # 아이콘 경로 결정
    candidates = [
        os.path.join(_BASE_DIR, "static", "img", "air_studio.ico"),
    ]
    if getattr(sys, "frozen", False):
        candidates.insert(0, os.path.join(
            getattr(sys, "_MEIPASS", ""), "static", "img", "air_studio.ico"
        ))

    for path in candidates:
        if os.path.exists(path):
            _icon_path = path
            break

    # PIL로 ICO를 열거나, 기본 이미지 생성
    try:
        from PIL import Image
        if _icon_path and os.path.exists(_icon_path):
            img = Image.open(_icon_path)
            # pystray는 RGBA 이미지를 요구
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            return img.resize((64, 64), Image.Resampling.LANCZOS)
    except Exception:
        pass

    # 기본 파란색 원 아이콘 폴백
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=(59, 130, 246, 255))  # blue
    draw.text((18, 22), "A", fill="white")
    return img


def start_system_tray():
    """
    시스템 트레이 아이콘 시작.
    main.py에서 백그라운드 스레드로 호출됩니다.

    이 함수는 블로킹 호출입니다 — pystray.run()이
    메인 스레드에서 실행되어야 하므로,
    호출부에서 daemon 스레드로 감싸야 합니다.
    """
    global _icon

    try:
        import pystray
    except ImportError:
        print("[TrayService] pystray 미설치 — 시스템 트레이 비활성화")
        print("[TrayService] 설치: pip install pystray Pillow")
        return

    try:
        from services.tray_status_collector import tray_status_collector
        from services.tray_notification import tray_notification

        # 상태 변경 콜백 등록
        tray_status_collector.set_on_change(_on_status_change)

        # 상태 수집기 시작
        tray_status_collector.start()

        # 아이콘 이미지 로드
        icon_image = _load_icon_image()

        # 초기 스냅샷으로 툴팁 설정
        snapshot = tray_status_collector.get_current_snapshot()
        initial_tooltip = snapshot.tooltip_text if snapshot else "AIR Studio - 대기 중"

        # 트레이 아이콘 생성
        _icon = pystray.Icon(
            name="AIR Studio",
            icon=icon_image,
            title=initial_tooltip,
            menu=_build_menu(_icon),
            hover_text=initial_tooltip,
        )

        print("[TrayService] 시스템 트레이 시작됨")

        # pystray 이벤트 루프 실행 (블로킹)
        _icon.run()

    except Exception as e:
        print(f"[TrayService] 시스템 트레이 시작 실패: {e}")
        import traceback
        traceback.print_exc()


def update_tray():
    """
    외부에서 트레이 상태를 수동 갱신할 때 호출.
    status_collector의 폴링 외에 즉시 업데이트가 필요한 경우.
    """
    global _icon
    if _icon is None:
        return

    try:
        snapshot = _get_snapshot()
        if snapshot and hasattr(_icon, 'title'):
            _icon.title = snapshot.tooltip_text
        if _icon and hasattr(_icon, 'menu'):
            _icon.menu = _build_menu(_icon)
    except Exception as e:
        print(f"[TrayService] 트레이 업데이트 실패: {e}")
