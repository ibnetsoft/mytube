# database.py - SQLite 로컬 데이터베이스
import sqlite3
import json
import os
import shutil
import sys
import threading
import time as _time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

try:
    from config import config
except Exception:
    config = None

LEGACY_DB_PATH = Path(__file__).parent / "data" / "wingsai.db"
DB_PATH = Path(getattr(config, "DB_PATH", LEGACY_DB_PATH))

# 스레드별 연결 캐시 (매 호출마다 새 연결 생성하는 오버헤드 제거)
_local = threading.local()
_migration_lock = threading.Lock()
_migration_checked = False


def get_db_path() -> Path:
    """현재 앱이 사용할 canonical SQLite DB 경로."""
    return Path(getattr(config, "DB_PATH", DB_PATH))


def close_db_connections():
    """스레드 로컬 SQLite 연결을 실제로 닫고 캐시를 비운다."""
    wrapper = getattr(_local, "conn", None)
    if wrapper is not None:
        try:
            wrapper._conn.close()
        except Exception:
            pass
        try:
            delattr(_local, "conn")
        except Exception:
            pass


def _legacy_db_candidates() -> List[Path]:
    candidates = [LEGACY_DB_PATH]
    try:
        if getattr(sys, "frozen", False):
            candidates.append(Path(sys.executable).parent / "data" / "wingsai.db")
        elif config is not None:
            candidates.append(Path(getattr(config, "BASE_DIR", Path(__file__).parent)) / "data" / "wingsai.db")
        local_appdata = os.getenv("LOCALAPPDATA")
        userprofile = os.getenv("USERPROFILE")
        if local_appdata:
            candidates.append(Path(local_appdata) / "picadilly" / "data" / "wingsai.db")
        elif userprofile:
            candidates.append(Path(userprofile) / "AppData" / "Local" / "picadilly" / "data" / "wingsai.db")
    except Exception:
        pass

    target = get_db_path().resolve()
    unique = []
    seen = set()
    for path in candidates:
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path
        key = str(resolved).lower()
        if key not in seen and key != str(target).lower():
            seen.add(key)
            unique.append(path)
    return unique


def _count_projects(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='projects'").fetchone()
        if not row or not row[0]:
            return 0
        row = conn.execute("SELECT COUNT(*) FROM projects").fetchone()
        return int(row[0] or 0)
    except Exception:
        return 0
    finally:
        conn.close()


def ensure_local_db_migrated():
    """기존 repo/exe 옆 DB를 AppData canonical DB로 1회 안전 이전."""
    global _migration_checked
    if _migration_checked:
        return
    with _migration_lock:
        if _migration_checked:
            return

        target = get_db_path()
        target.parent.mkdir(parents=True, exist_ok=True)

        if not target.exists():
            for source in _legacy_db_candidates():
                if source.exists():
                    try:
                        source_conn = sqlite3.connect(str(source))
                        try:
                            target_conn = sqlite3.connect(str(target))
                            try:
                                source_conn.backup(target_conn)
                            finally:
                                target_conn.close()
                        finally:
                            source_conn.close()
                        print(f"[DB] Migrated local DB to AppData: {source} -> {target}")
                    except Exception as e:
                        print(f"[DB] SQLite backup migration failed ({e}); trying file copy")
                        shutil.copy2(str(source), str(target))
                        print(f"[DB] Copied local DB to AppData: {source} -> {target}")
                    break
        else:
            target_count = _count_projects(target)
            for source in _legacy_db_candidates():
                source_count = _count_projects(source)
                if source_count and target_count == 0:
                    try:
                        backup = target.with_name(f"{target.stem}.empty-before-migration-{datetime.now().strftime('%Y%m%d-%H%M%S')}{target.suffix}")
                        shutil.copy2(str(target), str(backup))
                    except Exception:
                        pass
                    try:
                        close_db_connections()
                        source_conn = sqlite3.connect(str(source))
                        try:
                            target_conn = sqlite3.connect(str(target))
                            try:
                                source_conn.backup(target_conn)
                            finally:
                                target_conn.close()
                        finally:
                            source_conn.close()
                        print(f"[DB] Replaced empty AppData DB from legacy DB: {source} -> {target}")
                    except Exception as e:
                        print(f"[DB] Empty-target migration skipped: {e}")
                    break
                if source_count and target_count:
                    print(
                        f"[DB] AppData DB already exists ({target_count} projects); "
                        f"legacy DB not merged ({source_count} projects at {source})"
                    )
                    break

        _migration_checked = True


def record_local_db_migration_marker():
    """마이그레이션 출처를 global_settings에 기록 (테이블 생성 후 호출)."""
    try:
        legacy_source = next((str(p) for p in _legacy_db_candidates() if p.exists()), "")
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS global_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        markers = {
            "local_db_path_migrated_v1": "true",
            "local_db_current_path": str(get_db_path()),
            "local_db_legacy_source": legacy_source,
            "local_db_migrated_at": datetime.utcnow().isoformat(),
        }
        for key, value in markers.items():
            cursor.execute("""
                INSERT INTO global_settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
            """, (key, value))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[DB] Failed to record DB migration marker: {e}")

class _ReuseConn:
    """conn.close() 호출 시 실제로 닫지 않고 연결을 유지하는 래퍼"""
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def close(self):
        # 기존 코드가 conn.close()를 호출해도 연결을 유지
        # 단, uncommitted 트랜잭션은 rollback해서 다음 호출이 깨끗하게 시작
        try:
            self._conn.rollback()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._conn, name)

def get_db() -> _ReuseConn:
    """스레드별 DB 연결 반환 (재사용)"""
    ensure_local_db_migrated()
    db_path = get_db_path()
    wrapper = getattr(_local, "conn", None)
    if wrapper is not None and getattr(wrapper, "_db_path", None) != str(db_path):
        close_db_connections()
        wrapper = None
    if wrapper is None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        raw = sqlite3.connect(str(db_path), timeout=60.0, check_same_thread=False)
        raw.row_factory = sqlite3.Row
        # WAL 모드는 연결 생성 시 한 번만 설정
        try:
            raw.execute("PRAGMA journal_mode=WAL;")
            raw.execute("PRAGMA synchronous=NORMAL;")
            raw.execute("PRAGMA cache_size=-8000;")  # 8MB 캐시
        except Exception:
            pass
        wrapper = _ReuseConn(raw)
        wrapper._db_path = str(db_path)
        _local.conn = wrapper
    return wrapper

def reset_rendering_status():
    """서버 시작 시 렌더링 중이던 상태를 초기화"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE projects SET status = 'failed' WHERE status = 'rendering'")
        if cursor.rowcount > 0:
            print(f"[DB] Reset {cursor.rowcount} stuck rendering projects to 'failed'")
        conn.commit()
    except Exception as e:
        print(f"[DB] Failed to reset rendering status: {e}")
    finally:
        conn.close()

def init_db():
    """테이블 초기화"""
    conn = get_db()
    cursor = conn.cursor()

    # [MIGRATION] withdrawals 테이블 생성
    try:
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_email TEXT NOT NULL,
            amount REAL NOT NULL,
            dest_address TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
    except Exception:
        pass

    # 프로젝트 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            topic TEXT,
            status TEXT DEFAULT 'draft',
            language TEXT DEFAULT 'ko',
            employee_email TEXT,
            sync_id TEXT,
            last_synced_at TEXT,
            sync_dirty INTEGER DEFAULT 1,
            remote_deleted_at TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # [MIGRATION] Add language column if not exists
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN language TEXT DEFAULT 'ko'")
    except Exception:
        pass # Already exists

    # [MIGRATION] Add Vietnamese translation columns
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN name_vi TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN topic_vi TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN title_vi TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE image_prompts ADD COLUMN scene_text_vi TEXT")
    except Exception:
        pass

    # [MIGRATION] Add English translation columns
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN name_en TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN topic_en TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN title_en TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE image_prompts ADD COLUMN scene_text_en TEXT")
    except Exception:
        pass

    # [MIGRATION] Add Thai UI translation columns (UI display only; production languages remain ko/en/ja)
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN name_th TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN topic_th TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN title_th TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE image_prompts ADD COLUMN scene_text_th TEXT")
    except Exception:
        pass

    # [NEW] 웹툰 수동 처리 학습 시스템
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS webtoon_learning_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            condition_type TEXT, 
            condition_value TEXT, 
            action_type TEXT,
            description TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 프로젝트 핵심 설정 (10가지 요소)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER UNIQUE,
            title TEXT,
            description TEXT,
            thumbnail_text TEXT,
            thumbnail_url TEXT,
            duration_seconds INTEGER DEFAULT 60,
            aspect_ratio TEXT DEFAULT '16:9',
            script TEXT,
            hashtags TEXT,
            voice_tone TEXT DEFAULT 'neutral',
            voice_name TEXT DEFAULT 'Puck',
            voice_language TEXT DEFAULT 'ko-KR',
            voice_style_prompt TEXT,
            voice_provider TEXT DEFAULT 'elevenlabs',
            voice_speed REAL DEFAULT 1.0,
            voice_multi_enabled INTEGER DEFAULT 0,
            voice_mapping_json TEXT, -- 인물별 성우 매핑 (JSON)
            video_command TEXT,
            video_path TEXT,
            subtitle_style_enum TEXT DEFAULT 'Basic_White',
            subtitle_font_size INTEGER DEFAULT 10,
            subtitle_stroke_color TEXT DEFAULT 'black',
            subtitle_stroke_width REAL DEFAULT 0.15,
            subtitle_position_y INTEGER,
            background_video_url TEXT,
            is_uploaded INTEGER DEFAULT 0,
            all_video INTEGER DEFAULT 0,
            motion_method TEXT DEFAULT 'standard',
            video_scene_count INTEGER DEFAULT 0,
            upload_privacy TEXT DEFAULT 'private',
            upload_schedule_at TEXT,
            youtube_channel_id INTEGER,
            creation_mode TEXT DEFAULT 'default',
            product_url TEXT,
            topview_task_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS music_track_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            track_index INTEGER NOT NULL,
            title TEXT,
            genre TEXT,
            mood TEXT,
            instruments TEXT,
            lyrics TEXT,
            vocalist_gender TEXT,
            vocal_mode TEXT,
            duration_seconds INTEGER DEFAULT 240,
            prompt TEXT,
            status TEXT DEFAULT 'planned',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(project_id, track_index),
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    # [MIGRATION] Add video options columns if not exists
    for col, col_type in [("all_video", "INTEGER DEFAULT 0"), ("motion_method", "TEXT DEFAULT 'standard'"), ("video_scene_count", "INTEGER DEFAULT 0")]:
        try:
            cursor.execute(f"ALTER TABLE project_settings ADD COLUMN {col} {col_type}")
        except Exception:
            pass # Already exists

    for col, col_type in [
        ("actual_payout", "INTEGER DEFAULT 0"),
        ("asset_mix_summary_json", "TEXT"),
        ("video_clip_ratio", "TEXT"),
        ("total_scenes", "INTEGER DEFAULT 0"),
        ("video_scenes", "INTEGER DEFAULT 0"),
        ("image_scenes", "INTEGER DEFAULT 0"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE project_settings ADD COLUMN {col} {col_type}")
        except Exception:
            pass

    for col, col_type in [
        ("qa_status", "TEXT"),
        ("qa_hold_upload", "TEXT DEFAULT '0'"),
        ("qa_checked_at", "TEXT"),
        ("qa_result_json", "TEXT"),
        ("qa_normalized_video_path", "TEXT"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE project_settings ADD COLUMN {col} {col_type}")
        except Exception:
            pass

    # 학습형 제작 시스템: 제작 이벤트/스냅샷 로그
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_learning_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            stage TEXT,
            source TEXT DEFAULT 'system',
            payload_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_project_learning_events_project_created
        ON project_learning_events(project_id, created_at)
    """)
    for col, col_type in [
        ("remote_synced_at", "TEXT"),
        ("remote_sync_error", "TEXT"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE project_learning_events ADD COLUMN {col} {col_type}")
        except Exception:
            pass
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_learning_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            snapshot_type TEXT NOT NULL,
            reference_json TEXT,
            style_json TEXT,
            script_json TEXT,
            thumbnail_json TEXT,
            tts_json TEXT,
            video_json TEXT,
            qa_json TEXT,
            upload_json TEXT,
            remote_synced_at TEXT,
            remote_sync_error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_project_learning_snapshots_project_type
        ON project_learning_snapshots(project_id, snapshot_type, created_at)
    """)
    for col, col_type in [
        ("remote_synced_at", "TEXT"),
        ("remote_sync_error", "TEXT"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE project_learning_snapshots ADD COLUMN {col} {col_type}")
        except Exception:
            pass

    # 분석 데이터 (주제 찾기 결과)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            video_id TEXT,
            video_title TEXT,
            channel_title TEXT,
            thumbnail_url TEXT,
            view_count INTEGER,
            like_count INTEGER,
            comment_count INTEGER,
            viral_score INTEGER,
            analysis_result TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    # 대본 구조 (기획 단계)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS script_structure (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            hook TEXT,
            sections TEXT,
            cta TEXT,
            style TEXT,
            duration INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    # [NEW] 프로젝트 학습 자료 (Sources)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            source_type TEXT, -- url, txt, pdf
            title TEXT,
            content TEXT,
            url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    # 채널 관리 (설정)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            handle TEXT,
            description TEXT,
            credentials_path TEXT,
            proxy TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # [MIGRATION] Add proxy column to channels table if not exists
    try:
        cursor.execute("ALTER TABLE channels ADD COLUMN proxy TEXT")
    except Exception:
        pass

    # 생성된 대본
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            full_script TEXT,
            word_count INTEGER,
            estimated_duration INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    # 이미지 프롬프트
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS image_prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            scene_number INTEGER,
            scene_text TEXT,
            prompt_ko TEXT,
            prompt_en TEXT,
            image_url TEXT,
            focal_point_y REAL DEFAULT 0.5,
            script_start TEXT,
            script_end TEXT,
            video_url TEXT,
            scene_title TEXT,
            motion_desc TEXT,
            sfx_prompt TEXT,
            sfx_url TEXT,
            bgm_prompt TEXT,
            bgm_url TEXT,
            fade_in TEXT,
            engine TEXT,
            prompt_char TEXT DEFAULT '',
            prompt_bg TEXT DEFAULT '',
            flow_prompt TEXT,
            scene_type TEXT,
            is_dual BOOLEAN DEFAULT 0,
            start_frame TEXT,
            end_frame TEXT,
            prompt_en_start TEXT,
            prompt_en_end TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    # TTS 오디오
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tts_audio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            voice_id TEXT,
            voice_name TEXT,
            audio_path TEXT,
            duration REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    # 메타데이터 (제목/설명/태그)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            titles TEXT,
            description TEXT,
            tags TEXT,
            hashtags TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    # 썸네일 아이디어 및 상세 설정
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS thumbnails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            ideas TEXT,
            texts TEXT,
            full_settings TEXT, -- 상세 설정 (JSON)
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    # 쇼츠
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shorts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            shorts_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    # [NEW] 이미지 스타일 프롬프트 프리셋
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS style_presets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            style_key TEXT UNIQUE,
            prompt_value TEXT,
            image_url TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # [NEW] 대본 스타일 프롬프트 프리셋
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS script_style_presets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            style_key TEXT UNIQUE,
            prompt_value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # [NEW] 썸네일 스타일 프롬프트 프리셋
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS thumbnail_style_presets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            style_key TEXT UNIQUE,
            prompt_value TEXT,
            image_url TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # [NEW] 오토파일럿 프리셋
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS autopilot_presets (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             name TEXT NOT NULL,
             settings_json TEXT NOT NULL,
             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # [NEW] 캐릭터 프롬프트 및 이미지 관리
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            name TEXT,
            role TEXT,
            description_ko TEXT,
            prompt_en TEXT,
            image_url TEXT,
            dna_yaml TEXT,
            seed INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    # [NEW] 프로젝트 소스 (NotebookLM 기능을 위한 학습 데이터)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            type TEXT, -- 'url', 'pdf', 'txt'
            title TEXT,
            url TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)



    # [NEW] 자막 스타일 프리셋
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subtitle_style_presets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            settings_json TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # [NEW] 숏폼 템플릿 스타일 프리셋
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shorts_template_presets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            settings_json TEXT,
            image_path TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    
    # AI 생성 로그 테이블 [NEW]
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_generation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            task_type TEXT,
            model_id TEXT,
            provider TEXT,
            status TEXT,
            prompt_summary TEXT,
            error_msg TEXT,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            thinking_tokens INTEGER DEFAULT 0,
            balance_after INTEGER,
            elapsed_time REAL,
            worker_email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

def migrate_db():
    """기존 테이블에 새 컬럼 추가 (마이그레이션)"""
    conn = get_db()
    cursor = conn.cursor()

    # [NEW] Subtitle Style Presets Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subtitle_style_presets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            settings_json TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # [NEW] Shorts Template Style Presets Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shorts_template_presets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            settings_json TEXT,
            image_path TEXT,
            category TEXT DEFAULT 'shorts',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # [MIGRATION] Add category column if not exists
    try:
        cursor.execute("ALTER TABLE shorts_template_presets ADD COLUMN category TEXT DEFAULT 'shorts'")
    except Exception:
        pass

    # [NEW] Global Settings Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS global_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # [NEW] AI Style System Tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_style_prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            type TEXT NOT NULL, -- 'image' or 'script'
            version REAL DEFAULT 1.0,
            prompt_content TEXT NOT NULL,
            performance_score REAL DEFAULT 0.0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            category TEXT,
            rating INTEGER NOT NULL, -- e.g., 1 (bad), 5 (good)
            comments TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


    # projects에 employee_email 컬럼 추가 (없으면)
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN employee_email TEXT")
    except sqlite3.OperationalError:
        pass

    # project_settings에 thumbnail_url 컬럼 추가 (없으면)
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN thumbnail_url TEXT")
    except sqlite3.OperationalError:
        pass

    # Voice Settings 컬럼 추가
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN voice_name TEXT DEFAULT 'Puck'")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN voice_language TEXT DEFAULT 'ko-KR'")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN voice_style_prompt TEXT")
    except sqlite3.OperationalError:
        pass

    # New Style Columns
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN subtitle_path TEXT")
    except sqlite3.OperationalError: pass
    
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN image_timings_path TEXT")
    except sqlite3.OperationalError: pass

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN timeline_images_path TEXT")
    except sqlite3.OperationalError: pass

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN image_style_prompt TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN subtitle_font TEXT DEFAULT 'Malgun Gothic'")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN subtitle_color TEXT DEFAULT 'white'")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN target_language TEXT DEFAULT 'ko'")
    except sqlite3.OperationalError:
        pass
        
    # Subtitle Style Column
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN subtitle_style_enum TEXT DEFAULT 'Basic_White'")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN subtitle_font_size INTEGER DEFAULT 10")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN subtitle_path TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN is_published INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN youtube_video_id TEXT")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN subtitle_stroke_color TEXT DEFAULT 'black'")
    except sqlite3.OperationalError:
        pass
        
    # 마이그레이션: project_settings 테이블에 template_image_url 컬럼 추가
    cursor.execute("PRAGMA table_info(project_settings)")
    columns = [info[1] for info in cursor.fetchall()]
    if 'template_image_url' not in columns:
        print("[Migration] Adding template_image_url column to project_settings table...")
        cursor.execute("ALTER TABLE project_settings ADD COLUMN template_image_url TEXT")

    # 마이그레이션: project_settings 테이블에 subtitle_position_y 컬럼 추가
    if 'subtitle_position_y' not in columns:
        print("[Migration] Adding subtitle_position_y column to project_settings table...")
        cursor.execute("ALTER TABLE project_settings ADD COLUMN subtitle_position_y INTEGER")

    # 마이그레이션: project_settings 테이블에 background_video_url 컬럼 추가
    if 'background_video_url' not in columns:
        print("[Migration] Adding background_video_url column to project_settings table...")
        cursor.execute("ALTER TABLE project_settings ADD COLUMN background_video_url TEXT")

    # Webtoon & Video Engine Options
    for col, col_type in [
        ("video_engine", "TEXT DEFAULT 'wan'"),
        ("use_lipsync", "INTEGER DEFAULT 1"),
        ("use_subtitles", "INTEGER DEFAULT 1"),
        ("webtoon_scenes_json", "TEXT")
    ]:
        try:
            cursor.execute(f"ALTER TABLE project_settings ADD COLUMN {col} {col_type}")
            print(f"[Migration] Added {col} to project_settings")
        except sqlite3.OperationalError:
            pass

    # [NEW] Webtoon Focal Point
    try:
        cursor.execute("ALTER TABLE image_prompts ADD COLUMN focal_point_y REAL DEFAULT 0.5")
    except sqlite3.OperationalError: pass

    # 마이그레이션: project_settings 테이블에 is_uploaded 컬럼 추가
    if 'is_uploaded' not in columns:
        print("[Migration] Adding is_uploaded column to project_settings table...")
        cursor.execute("ALTER TABLE project_settings ADD COLUMN is_uploaded INTEGER DEFAULT 0")

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN subtitle_stroke_width REAL DEFAULT 0.15")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN subtitle_position_y INTEGER")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN background_video_url TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN script_style TEXT")
    except sqlite3.OperationalError:
        pass
    
    # 마이그레이션: image_prompts 테이블에 video_url 컬럼 추가 (Wan 2.2 Motion)
    cursor.execute("PRAGMA table_info(image_prompts)")
    image_prompts_columns = [info[1] for info in cursor.fetchall()]
    if 'video_url' not in image_prompts_columns:
        print("[Migration] Adding video_url column to image_prompts table...")
        try:
            cursor.execute("ALTER TABLE image_prompts ADD COLUMN video_url TEXT")
        except sqlite3.OperationalError:
            pass

    # [NEW] 마이그레이션: style_presets 테이블에 image_url 컬럼 추가
    cursor.execute("PRAGMA table_info(style_presets)")
    style_presets_columns = [info[1] for info in cursor.fetchall()]
    if 'image_url' not in style_presets_columns:
        print("[Migration] Adding image_url column to style_presets table...")
        try:
           cursor.execute("ALTER TABLE style_presets ADD COLUMN image_url TEXT")
        except sqlite3.OperationalError:
           pass
    # [Migration] style_presets 테이블에 gemini_instruction 컬럼 추가
    cursor.execute("PRAGMA table_info(style_presets)")
    style_presets_columns2 = [info[1] for info in cursor.fetchall()]
    if 'gemini_instruction' not in style_presets_columns2:
        print("[Migration] Adding gemini_instruction column to style_presets table...")
        try:
            cursor.execute("ALTER TABLE style_presets ADD COLUMN gemini_instruction TEXT")
        except sqlite3.OperationalError:
            pass
    # [Migration] style_presets 테이블에 mode 컬럼 추가 (image | blog | all)
    cursor.execute("PRAGMA table_info(style_presets)")
    style_presets_columns3 = [info[1] for info in cursor.fetchall()]
    if 'mode' not in style_presets_columns3:
        print("[Migration] Adding mode column to style_presets table...")
        try:
            cursor.execute("ALTER TABLE style_presets ADD COLUMN mode TEXT DEFAULT 'image'")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # [Migration] style_presets, script_style_presets, thumbnail_style_presets 테이블에 display_name_ko/vi 추가
    for table in ['style_presets', 'script_style_presets', 'thumbnail_style_presets']:
        cursor.execute(f"PRAGMA table_info({table})")
        cols = [info[1] for info in cursor.fetchall()]
        if 'display_name_ko' not in cols:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN display_name_ko TEXT")
            except Exception: pass
        if 'display_name_vi' not in cols:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN display_name_vi TEXT")
            except Exception: pass
    conn.commit()
    # [Migration] project_sources 테이블에 type 컬럼 추가 (source_type 과 통일)
    cursor.execute("PRAGMA table_info(project_sources)")
    ps_cols = [info[1] for info in cursor.fetchall()]
    if 'type' not in ps_cols:
        print("[Migration] Adding 'type' column to project_sources table...")
        try:
            cursor.execute("ALTER TABLE project_sources ADD COLUMN type TEXT")
            # 기존 source_type 값을 type 으로 복사
            cursor.execute("UPDATE project_sources SET type = source_type WHERE type IS NULL")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # [NURSERY] Nursery Rhyme Style Preset
    try:
        # Only insert if the table is completely empty (clean DB)
        cursor.execute("SELECT COUNT(*) FROM style_presets")
        if cursor.fetchone()[0] == 0:
            print("[Migration] Adding nursery_rhyme style preset (clean db)...")
            cursor.execute("""
                INSERT INTO style_presets (style_key, prompt_value, image_url, mode, gemini_instruction) 
                VALUES (?, ?, ?, ?, ?)
            """, (
                'nursery_rhyme', 
                'Cute 3D animation style, Pixar/Disney inspired, vibrant colors, child-friendly environment, no text.',
                '/static/img/styles/style_nursery.png',
                'all',
                'Focus on creating a magical, educational, and safe environment for children. Use soft lighting and rounded shapes.'
            ))
            conn.commit()
    except Exception as e:
        print(f"[Migration Warning] Failed to add nursery_rhyme style: {e}")

    # [NURSERY] Script Style Preset
    try:
        # Only insert if the table is completely empty (clean DB)
        cursor.execute("SELECT COUNT(*) FROM script_style_presets")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO script_style_presets (style_key, prompt_value) VALUES (?, ?)", 
                           ('nursery_rhyme', 'Educational and fun nursery rhyme for children aged 2-6.'))
            conn.commit()
    except Exception as e:
        print(f"[Migration Warning] Failed to add nursery_rhyme script style: {e}")

    # wimpy 프리셋의 gemini_instruction 초기값/업데이트 설정
    _wimpy_default_instruction = """[졸라맨 스타일 전용 - 필수 준수]
이 영상은 졸라맨/윔피 스타일입니다. 모든 씬에 캐릭터가 나올 필요는 없습니다.
각 씬마다 scene_type을 먼저 결정하고, 그에 맞게 프롬프트를 작성하세요.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【STEP 1: scene_type 결정 (필수)】
대본 내용을 분석하여 아래 3가지 중 하나를 선택합니다:

● "character_main" — 내레이터가 시청자에게 직접 설명하는 씬
  신호어: 나, 우리, 여러분, 안녕하세요, 오늘, 알아봅시다, 살펴봅시다, 말씀드리겠습니다
  → 캐릭터가 화면 중앙에 크게 등장

● "character_support" — 데이터/수치/통계를 설명하는 씬. 캐릭터는 보조 역할
  신호어: 수치, 통계, %, 억, 조, 분석, 지표, 기록, 나타났습니다, 달했습니다, 하락, 상승
  → 캐릭터가 화면 우하단에 작게, 데이터를 가리키는 포즈

● "infographic" — 추상 개념·거시경제·시장 전체를 다루는 씬. 캐릭터 불필요
  신호어: GDP, 시장, 전 세계, 글로벌, 산업, 수출, 수입, 무역, 부동산, 반도체, 공급망, 금융
  → 캐릭터 없음. 인포그래픽/데이터 시각화 중심

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【STEP 2: prompt_char 작성 (scene_type에 따라 조건부)】

■ character_main (캐릭터 중앙 크게):
1단계: "A full-body minimalist cartoon illustration of a cute stick-figure style character with bold black outlines, standing on a pure white background. Flat 2D vector graphic style. Perfectly bald and smooth round white circular head (strictly NO hair, NO hairstyle, NO wig). The face MUST HAVE a pair of black dot eyes and a simple black arc smile. Strictly two arms and two hands. No extra limbs, no extra hands."
2단계: "The character has a simple perfectly bald white circular head with NO hair, simple dot eyes, and a wide cheerful arc smile. Face must never be blank. The hands are small rounded fists with black outlines (NOT white balls, NOT white circles). The character wears a vibrant solid teal-blue hoodie with a front pocket and FULL-LENGTH TEAL-BLUE SLEEVES that cover the entire arm down to the wrist. NO ROLLED-UP SLEEVES, NO BLACK SKIN VISIBLE ON ARMS. Solid black trousers, and white sneakers with black trim and laces."
3단계: 씬에 맞는 포즈 선택:
  ❌ 금지: holding, carrying, gripping, fists raised, arms raised, punching, flexing
  ✅ SAFE-A: "The character is standing with both arms hanging naturally at its sides. It has black eyes and a small mouth. Its full-length teal-blue sleeves cover its arms completely."
  ✅ SAFE-B: "The character is standing and pointing at [대상] with its right hand. Its left arm hangs at its side. It has black eyes and a small mouth. Its full-length teal-blue sleeves cover its arms completely."
  ✅ SAFE-C: "The character is standing and looking down at a small book resting on a stand. Its two hands are clasped tightly together in front of its chest in a deep thought gesture, not touching the book. Its face shows a thoughtful expression with dot eyes. Its full-length teal-blue sleeves cover its arms completely."
  ✅ SAFE-D: "The character sits at a wooden table, resting both its hands firmly under its chin, looking down thoughtfully with dot eyes and a small mouth. Its full-length teal-blue sleeves cover its arms completely."
마지막: "Isolated on a pure white background. No background elements. no text, no words, no letters"

■ character_support (캐릭터 작게 구석에):
"A small full-body minimalist cartoon stick-figure in the lower-right corner of the frame, pointing toward the center-left with its right hand. Its left arm hangs at its side. Perfectly bald and smooth white circular head with strictly NO hair. THE FACE MUST HAVE a pair of black dot eyes and a simple mouth. Vibrant teal-blue hoodie with FULL-LENGTH TEAL-BLUE SLEEVES covering the entire arm down to the wrist, NO ROLLED-UP SLEEVES, NO BLACK SKIN VISIBLE ON ARMS. Black trousers, white sneakers. Bold black outlines, flat 2D vector. Strictly two arms and two hands. Isolated on a pure white background. No background elements. no text, no words, no letters"

■ infographic (캐릭터 없음):
""  ← 반드시 빈 문자열. 캐릭터 프롬프트 생성 금지.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【STEP 3: prompt_bg 작성 (항상 풍부하게)】
- 스타일: Korean webtoon manhwa illustration style, clean detailed linework, vibrant color grading, dynamic lighting, cinematic depth
- 5개 이상의 구체적 소품/오브젝트/환경 요소 반드시 포함. 풍부한 원근감과 레이어드 뎁스.
- scene_type별:
  ● character_main/support: 캐릭터가 서 있는 실감나는 공간 묘사. 정교한 실내/실외 배경. 배경 인물 실루엣 자유 추가.
  ● infographic: 한국 웹툰 감성 인포그래픽 (세계 지도, 차트, 그래프, 통계, 아이콘을 웹툰 컬러 팔레트로)
마지막 고정 문구: "Korean webtoon manhwa style, clean linework, vibrant colors, no main protagonist, no text, no words, no letters"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【STEP 4: prompt_en 작성 (scene_type별 통합 씬)】
고정 스타일 키워드 (문장 맨 앞 필수): "Korean webtoon manhwa illustration, vibrant colors, clean detailed linework, dynamic lighting,"
※ 캐릭터는 졸라맨 stick-figure이고, 배경은 한국 웹툰 스타일 — 두 요소가 합성됩니다.

scene_type별 구조:
● character_main: "...[minimalist stick-figure character, teal-blue hoodie, bald smooth white head, center-front], [한국 웹툰 스타일 배경 환경+소품 5개+], cinematic depth, layered scene, no text, no words, no letters"
● character_support: "...[한국 웹툰 스타일 인포그래픽/차트 화면 중앙 크게], [small stick-figure lower-right corner pointing], Korean webtoon background, no text, no words, no letters"
● infographic: "...[인포그래픽 5개+ 한국 웹툰 스타일], NO character, NO person, vibrant colors, no text, no words, no letters"

■ 예시 (character_main): "Korean webtoon manhwa illustration, vibrant colors, clean detailed linework, dynamic lighting, minimalist stick-figure character with teal-blue hoodie and bald smooth white head standing center-front facing viewer, bright modern TV news studio with large monitors showing economic charts, anchor desk, dramatic studio lighting, background staff silhouettes, layered scene depth, no text, no words, no letters"
■ 예시 (character_support): "Korean webtoon manhwa illustration, vibrant colors, clean detailed linework, dynamic lighting, large central bar chart showing China GDP decline with red arrows, small stick-figure in lower-right corner pointing at chart, glowing data dashboard background, grid lines, statistical icons, no text, no words, no letters"
■ 예시 (infographic): "Korean webtoon manhwa illustration, vibrant colors, clean detailed linework, dynamic lighting, detailed world map with glowing trade route arrows between continents, cargo ship icons on ocean, rising and falling bar charts, country flag color blocks, red warning triangles, NO character, NO person, vibrant colors, no text, no words, no letters"
"""
    cursor.execute("SELECT gemini_instruction FROM style_presets WHERE style_key = 'wimpy'")
    _wimpy_row = cursor.fetchone()
    # 비어있거나 구버전이면 업데이트 (simple shapes / 하위 호환용 / YouTube educational 미포함)
    _needs_update = (
        not _wimpy_row or
        not _wimpy_row[0] or
        "simple shapes" in (_wimpy_row[0] or "").lower() or
        "clean simple illustration" in (_wimpy_row[0] or "").lower() or
        "하위 호환용" in (_wimpy_row[0] or "") or
        "youtube educational" not in (_wimpy_row[0] or "").lower() or
        "swept-back black hair" in (_wimpy_row[0] or "").lower() or
        "infographic" not in (_wimpy_row[0] or "").lower() or  # scene_type 미포함 구버전
        "korean webtoon" not in (_wimpy_row[0] or "").lower()  # flat 2D vector 구버전 (한국웹툰 미적용)
    )
    if _wimpy_row and _needs_update:
        cursor.execute(
            "UPDATE style_presets SET gemini_instruction = ? WHERE style_key = 'wimpy'",
            (_wimpy_default_instruction,)
        )
        conn.commit()
        print("[Migration] wimpy gemini_instruction updated to v2 (richer backgrounds)")

    # [NEW] 마이그레이션: thumbnail_style_presets 테이블에 image_url 컬럼 추가
    cursor.execute("PRAGMA table_info(thumbnail_style_presets)")
    thumb_style_presets_columns = [info[1] for info in cursor.fetchall()]
    if 'image_url' not in thumb_style_presets_columns:
        print("[Migration] Adding image_url column to thumbnail_style_presets table...")
        try:
           cursor.execute("ALTER TABLE thumbnail_style_presets ADD COLUMN image_url TEXT")
        except sqlite3.OperationalError:
           pass



    # Intro video path
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN intro_video_path TEXT")
    except sqlite3.OperationalError:
        pass
    
    # External video path (for uploaded videos)
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN external_video_path TEXT")
    except sqlite3.OperationalError:
        pass

    # Channel Auth Migration
    try:
        cursor.execute("ALTER TABLE channels ADD COLUMN credentials_path TEXT")
    except sqlite3.OperationalError:
        pass

    # [NEW] Upload options
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN upload_privacy TEXT DEFAULT 'private'")
    except sqlite3.OperationalError: pass
    try:
        cursor.execute("ALTER TABLE ai_generation_logs ADD COLUMN balance_after INTEGER")
    except sqlite3.OperationalError: pass
    try:
        cursor.execute("ALTER TABLE ai_generation_logs ADD COLUMN worker_email TEXT")
    except sqlite3.OperationalError: pass
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN upload_schedule_at TEXT")
    except sqlite3.OperationalError: pass
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN youtube_channel_id INTEGER")
    except sqlite3.OperationalError: pass

    # AI 로그 토큰 마이그레이션
    try:
        cursor.execute("ALTER TABLE ai_generation_logs ADD COLUMN input_tokens INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass
    try:
        cursor.execute("ALTER TABLE ai_generation_logs ADD COLUMN output_tokens INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass
    try:
        cursor.execute("ALTER TABLE ai_generation_logs ADD COLUMN thinking_tokens INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN creation_mode TEXT DEFAULT 'default'")
    except sqlite3.OperationalError: pass
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN product_url TEXT")
    except sqlite3.OperationalError: pass
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN topview_task_id TEXT")
    except sqlite3.OperationalError: pass
    except sqlite3.OperationalError:
        pass
        
    # [NEW] Character Consistency Persistence
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN character_ref_image_path TEXT")
    except sqlite3.OperationalError:
        pass


        
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN image_style TEXT")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN thumbnail_style TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN character_ref_text TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN character_ref_image_path TEXT")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN app_mode TEXT DEFAULT 'longform'")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN shorts_template_preset TEXT")
    except sqlite3.OperationalError:
        pass

    for col in ['webtoon_source_dir', 'psd_exclude_layer']:
        try:
            cursor.execute(f"ALTER TABLE project_settings ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
        
    # [NEW] Migration for script start/end in image_prompts
    cursor.execute("PRAGMA table_info(image_prompts)")
    image_prompts_columns = [info[1] for info in cursor.fetchall()]
    
    if 'script_start' not in image_prompts_columns:
        print("[Migration] Adding script_start to image_prompts...")
        try: cursor.execute("ALTER TABLE image_prompts ADD COLUMN script_start TEXT")
        except Exception: pass
        
    if 'script_end' not in image_prompts_columns:
        print("[Migration] Adding script_end to image_prompts...")
        try: cursor.execute("ALTER TABLE image_prompts ADD COLUMN script_end TEXT")
        except Exception: pass
        
    if 'scene_title' not in image_prompts_columns:
        print("[Migration] Adding scene_title to image_prompts...")
        try: cursor.execute("ALTER TABLE image_prompts ADD COLUMN scene_title TEXT")
        except Exception: pass

    # [NEW] Audio & Effects Columns migration
    for col in ['video_url', 'sfx_prompt', 'bgm_prompt', 'sfx_url', 'bgm_url', 'fade_in', 'motion_desc', 'engine', 'prompt_en_start', 'prompt_en_end']:
        if col not in image_prompts_columns:
            print(f"[Migration] Adding {col} to image_prompts...")
            try: cursor.execute(f"ALTER TABLE image_prompts ADD COLUMN {col} TEXT")
            except Exception: pass

    # [NEW] Two-prompt compositing columns (prompt_char: character-only, prompt_bg: background-only)
    for col in ['prompt_char', 'prompt_bg']:
        if col not in image_prompts_columns:
            print(f"[Migration] Adding {col} to image_prompts...")
            try: cursor.execute(f"ALTER TABLE image_prompts ADD COLUMN {col} TEXT DEFAULT ''")
            except Exception: pass

    # [FIX] Missing subtitle columns migration
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN subtitle_font_size INTEGER DEFAULT 5")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN subtitle_base_color TEXT DEFAULT 'white'")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN subtitle_pos_x TEXT DEFAULT 'center'")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN subtitle_pos_y TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN subtitle_pos_y TEXT")
    except sqlite3.OperationalError:
        pass

    # [FIX] Missing timeline/effects paths (Critical for Editor Persistence)
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN timeline_images_path TEXT")
    except sqlite3.OperationalError: pass
    
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN image_timings_path TEXT")
    except sqlite3.OperationalError: pass

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN image_effects_path TEXT")
    except sqlite3.OperationalError: pass

    # 마이그레이션: image_prompts 테이블에 script_start, script_end 추가
    # [NEW] Subtitle Toggle Columns
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN subtitle_bg_enabled INTEGER DEFAULT 1")
    except sqlite3.OperationalError: pass

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN subtitle_stroke_enabled INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN subtitle_line_spacing REAL DEFAULT 0.1")
    except sqlite3.OperationalError: pass

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN subtitle_bg_color TEXT DEFAULT '#000000'")
    except sqlite3.OperationalError: pass

    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN subtitle_bg_opacity REAL DEFAULT 0.5")
    except sqlite3.OperationalError: pass

    # [NEW] Webtoon Settings Persistence
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN webtoon_auto_split TEXT DEFAULT 'true'")
    except sqlite3.OperationalError: pass
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN webtoon_plan_json TEXT")
    except sqlite3.OperationalError: pass
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN webtoon_smart_pan TEXT DEFAULT 'true'")
    except sqlite3.OperationalError: pass
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN webtoon_convert_zoom TEXT DEFAULT 'true'")
    except sqlite3.OperationalError: pass

    cursor.execute("PRAGMA table_info(image_prompts)")
    img_columns = [info[1] for info in cursor.fetchall()]
    
    if 'script_start' not in img_columns:
        print("[Migration] Adding script_start to image_prompts...")
        cursor.execute("ALTER TABLE image_prompts ADD COLUMN script_start TEXT")
        
    if 'script_end' not in img_columns:
        print("[Migration] Adding script_end to image_prompts...")
        cursor.execute("ALTER TABLE image_prompts ADD COLUMN script_end TEXT")

    # [NEW] TTS Persistence Columns
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN voice_provider TEXT DEFAULT 'elevenlabs'")
    except sqlite3.OperationalError: pass
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN voice_speed REAL DEFAULT 1.0")
    except sqlite3.OperationalError: pass
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN voice_multi_enabled INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN voice_mapping_json TEXT")
    except sqlite3.OperationalError: pass
    
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN sfx_mapping_json TEXT")
    except sqlite3.OperationalError: pass

    # [NEW] AI가 배정한 대본/이미지 스타일을 워커가 변경하지 못하도록 잠그는 플래그
    try:
        cursor.execute("ALTER TABLE project_settings ADD COLUMN style_locked INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass

    # [NEW] Thumbnail Style Persistence
    # [NEW] Thumbnail Full Settings Persistence
    cursor.execute("PRAGMA table_info(thumbnails)")
    thumb_cols = [info[1] for info in cursor.fetchall()]
    if 'full_settings' not in thumb_cols:
        try:
            cursor.execute("ALTER TABLE thumbnails ADD COLUMN full_settings TEXT")
        except sqlite3.OperationalError: pass

    # [MIGRATION] Add image_url to style preset tables
    try:
        cursor.execute("ALTER TABLE style_presets ADD COLUMN image_url TEXT")
        print("[Migration] Added image_url to style_presets")
    except sqlite3.OperationalError:
        pass  # Already exists
    
    try:
        cursor.execute("ALTER TABLE thumbnail_style_presets ADD COLUMN image_url TEXT")
        print("[Migration] Added image_url to thumbnail_style_presets")
    except sqlite3.OperationalError:
        pass  # Already exists

    # [NEW] Thumbnail Preference Migration for Project Settings
    for col, col_type in [
        ("thumbnail_style", "TEXT"),
        ("thumbnail_font", "TEXT"),
        ("thumbnail_font_size", "INTEGER"),
        ("thumbnail_color", "TEXT"),
        ("thumbnail_full_state", "TEXT"),
        ("template_full_state", "TEXT"),
        ("longform_music", "TEXT"),
        ("longform_music_plan_json", "TEXT"),
        ("longform_music_generated_tracks_json", "TEXT")
    ]:
        try:
            cursor.execute(f"ALTER TABLE project_settings ADD COLUMN {col} {col_type}")
            print(f"[Migration] Added {col} to project_settings")
        except sqlite3.OperationalError:
            pass

    try:
        cursor.execute("PRAGMA table_info(music_track_plans)")
        music_plan_columns = [info[1] for info in cursor.fetchall()]
        if "instruments" not in music_plan_columns:
            cursor.execute("ALTER TABLE music_track_plans ADD COLUMN instruments TEXT")
        if "lyrics" not in music_plan_columns:
            cursor.execute("ALTER TABLE music_track_plans ADD COLUMN lyrics TEXT")
        if "vocalist_gender" not in music_plan_columns:
            cursor.execute("ALTER TABLE music_track_plans ADD COLUMN vocalist_gender TEXT")
        if "vocal_mode" not in music_plan_columns:
            cursor.execute("ALTER TABLE music_track_plans ADD COLUMN vocal_mode TEXT")
        if "duration_seconds" not in music_plan_columns:
            cursor.execute("ALTER TABLE music_track_plans ADD COLUMN duration_seconds INTEGER DEFAULT 240")
        if "prompt" not in music_plan_columns:
            cursor.execute("ALTER TABLE music_track_plans ADD COLUMN prompt TEXT")
        if "status" not in music_plan_columns:
            cursor.execute("ALTER TABLE music_track_plans ADD COLUMN status TEXT DEFAULT 'planned'")
    except Exception:
        pass

    # [NEW] Character DNA Migration
    cursor.execute("PRAGMA table_info(project_characters)")
    char_columns = [info[1] for info in cursor.fetchall()]
    if 'dna_yaml' not in char_columns:
        print("[Migration] Adding dna_yaml to project_characters...")
        try: cursor.execute("ALTER TABLE project_characters ADD COLUMN dna_yaml TEXT")
        except Exception: pass
    if 'seed' not in char_columns:
        print("[Migration] Adding seed to project_characters...")
        try: cursor.execute("ALTER TABLE project_characters ADD COLUMN seed INTEGER")
        except Exception: pass

    # [NEW] Admin publish columns for get_projects_with_status query
    for col, col_type in [
        ("admin_publish_ready", "TEXT DEFAULT '0'"),
        ("admin_publish_status", "TEXT"),
        ("is_published", "INTEGER DEFAULT 0"),
        ("youtube_video_id", "TEXT"),
        ("app_mode", "TEXT DEFAULT 'longform'"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE project_settings ADD COLUMN {col} {col_type}")
            print(f"[Migration] Added {col} to project_settings")
        except sqlite3.OperationalError:
            pass  # Already exists

    # [SYNC] Supabase project metadata sync state
    for col, col_type in [
        ("sync_id", "TEXT"),
        ("last_synced_at", "TEXT"),
        ("sync_dirty", "INTEGER DEFAULT 1"),
        ("remote_deleted_at", "TEXT"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE projects ADD COLUMN {col} {col_type}")
            print(f"[Migration] Added {col} to projects")
        except sqlite3.OperationalError:
            pass  # Already exists

    try:
        cursor.execute("SELECT id FROM projects WHERE sync_id IS NULL OR sync_id = ''")
        for row in cursor.fetchall():
            cursor.execute(
                "UPDATE projects SET sync_id = ?, sync_dirty = 1 WHERE id = ?",
                (str(uuid.uuid4()), row[0]),
            )
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_sync_id ON projects(sync_id)")
    except Exception as e:
        print(f"[Migration] Project sync backfill warning: {e}")

    conn.commit()
    print("[DB] Migration completed")

    conn.close()
    record_local_db_migration_marker()

# ============ 프로젝트 CRUD ============

def create_project(name: str, topic: str = None, app_mode: str = 'longform', language: str = 'ko', employee_email: str = None, script_style: str = None, image_style: str = None) -> int:
    """새 프로젝트 생성 + 기본 설정 초기화"""
    # DB 연결 전에 외부 설정값 미리 조회 (트랜잭션 중 별도 connection 방지)
    from services.settings_service import settings_service
    from services.tts_service import default_voice_name_for_language, language_code_for_tts
    defaults = settings_service.get_gemini_tts_settings()
    sub_defaults = get_subtitle_defaults()
    language = (str(language or 'ko').strip().lower() or 'ko')
    if language.startswith('en'):
        language = 'en'
    elif language.startswith('ja') or language.startswith('jp'):
        language = 'ja'
    elif not language.startswith('ko'):
        language = 'ko'
    else:
        language = 'ko'
    default_voice_name = default_voice_name_for_language(language)
    default_voice_language = language_code_for_tts(language)
    settings_language = str(defaults.get("language_code") or "").lower()
    settings_voice_name = defaults.get("voice_name") if settings_language.startswith(language) else None
    default_voice_provider = 'elevenlabs' if language == 'ko' else 'gemini'

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO projects (name, topic, language, employee_email, sync_id, sync_dirty) VALUES (?, ?, ?, ?, ?, 1)",
        (name, topic, language, employee_email, str(uuid.uuid4()))
    )
    project_id = cursor.lastrowid
    
    # 언어별 기본 폰트 자동 설정
    # (video_service.py의 font_mapping과 일치해야 함)
    lang_fonts = {
        'ko': 'GmarketSansBold',
        'en': 'Impact',
        'ja': 'NotoSansJP',
        'vi': 'Roboto',
        'es': 'Roboto'
    }
    initial_font = lang_fonts.get(language, 'GmarketSansBold')

    cursor.execute(
        """INSERT OR IGNORE INTO project_settings
           (project_id, title, voice_name, voice_language, voice_style_prompt,
            subtitle_font, subtitle_font_size, subtitle_color, subtitle_style_enum, subtitle_stroke_color, subtitle_stroke_width,
            subtitle_bg_enabled, subtitle_stroke_enabled, voice_provider, voice_speed, voice_multi_enabled, app_mode,
            target_language, script_style, image_style)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (project_id, name, settings_voice_name or default_voice_name,
         default_voice_language, defaults.get("style_prompt", ""),
         initial_font, sub_defaults.get("subtitle_font_size"),
         sub_defaults.get("subtitle_color"), sub_defaults.get("subtitle_style_enum"),
         sub_defaults.get("subtitle_stroke_color"), sub_defaults.get("subtitle_stroke_width"),
         1, 0, default_voice_provider, 1.0, 0, app_mode,
         language, script_style or 'default', image_style or 'realistic') # Default styles if not provided
    )

    conn.commit()
    conn.close()
    return project_id


def get_all_projects(employee_email: str = None) -> List[Dict]:
    """모든 프로젝트 목록 (이메일 필터링 지원)"""
    conn = get_db()
    cursor = conn.cursor()
    if employee_email:
        cursor.execute(
            """
            SELECT * FROM projects
            WHERE employee_email = ? OR employee_email IS NULL OR employee_email = ''
            ORDER BY updated_at DESC
            """,
            (employee_email,),
        )
    else:
        cursor.execute("SELECT * FROM projects ORDER BY updated_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_projects_with_status(employee_email: str = None) -> List[Dict]:
    """프로젝트 목록과 각 단계별 진행 상태 조회 (이메일 필터링 지원)"""
    conn = get_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 각 테이블의 존재 여부를 확인하여 진행 상태 파악
    # LEFT JOIN을 사용하여 데이터가 없더라도 프로젝트는 조회되도록 함
    query = """
    SELECT 
        p.id, p.name, p.topic, p.status as project_status, p.created_at, p.updated_at,
        ps.title as video_title,
        p.name_vi, p.topic_vi, ps.title_vi as video_title_vi,
        p.name_en, p.topic_en, ps.title_en as video_title_en,
        p.name_th, p.topic_th, ps.title_th as video_title_th,
        CASE WHEN s.id IS NOT NULL THEN 1 ELSE 0 END as has_script,
        CASE WHEN ss.id IS NOT NULL THEN 1 ELSE 0 END as has_structure,
        CASE WHEN ps.longform_music_plan_json IS NOT NULL AND ps.longform_music_plan_json != '' THEN 1 ELSE 0 END as has_music_plan,
        CASE WHEN ps.longform_music_generated_tracks_json IS NOT NULL AND ps.longform_music_generated_tracks_json != '' THEN 1 ELSE 0 END as has_music_tracks,
        (SELECT COUNT(*) FROM image_prompts WHERE project_id = p.id AND image_url IS NOT NULL AND image_url != '') as image_count,
        CASE WHEN t.id IS NOT NULL THEN 1 ELSE 0 END as has_tts,
        ps.video_path,
        ps.external_video_path,
        ps.template_image_url,
        ps.thumbnail_url,
        ps.upload_schedule_at,
        ps.is_uploaded as is_uploaded,
        ps.is_published as is_published,
        ps.admin_publish_ready,
        ps.admin_publish_status,
        ps.youtube_video_id,
        ps.qa_status,
        ps.qa_hold_upload,
        ps.qa_checked_at,
        (SELECT COUNT(*) FROM thumbnails WHERE project_id = p.id) as thumbnail_count,
        ps.app_mode,
        m.description,
        p.employee_email
    FROM projects p
    LEFT JOIN project_settings ps ON p.id = ps.project_id
    LEFT JOIN scripts s ON p.id = s.project_id
    LEFT JOIN script_structure ss ON p.id = ss.project_id
    LEFT JOIN tts_audio t ON p.id = t.project_id
    LEFT JOIN metadata m ON p.id = m.project_id
    """
    
    if employee_email:
        query += " WHERE p.employee_email = ? OR p.employee_email IS NULL OR p.employee_email = '' "
        query += " ORDER BY p.updated_at DESC "
        cursor.execute(query, (employee_email,))
    else:
        query += " ORDER BY p.updated_at DESC "
        cursor.execute(query)
        
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        r = dict(row)
        r["has_structure"] = bool(r.get("has_structure")) or bool(r.get("has_music_plan"))
        is_music_mode = (r.get("app_mode") or "longform") == "longform_music"
        has_cover = bool(r.get("template_image_url")) or int(r.get("image_count") or 0) > 0
        has_tracks = bool(r.get("has_music_tracks"))
        has_thumbnail = bool(r.get("thumbnail_url")) or int(r.get("thumbnail_count") or 0) > 0
        has_render = bool(r.get("video_path")) or bool(r.get("external_video_path")) or str(r.get("project_status") or "") in {
            "rendering", "remote_queued", "remote_packaging", "rendered", "completed"
        }
        has_publish_state = (
            bool(r.get("upload_schedule_at"))
            or bool(r.get("is_uploaded"))
            or bool(r.get("is_published"))
            or str(r.get("admin_publish_ready") or "") == "1"
            or str(r.get("admin_publish_status") or "") in {"pending_review", "to_be_published", "published"}
            or bool(r.get("youtube_video_id"))
        )
        has_remote_delivery = str(r.get("project_status") or "") in {
            "remote_packaging", "remote_queued", "rendering", "rendered", "completed"
        } or bool(r.get("video_path")) or bool(r.get("external_video_path"))
        progress = { # Detailed progress
            "plan": bool(r["has_structure"]),     # 대본 기획
            "script": bool(r["has_script"]),      # 대본 생성
            "image": int(r["image_count"] or 0) > 0,        # 이미지 생성 (하나라도 있으면)
            "tts": bool(r["has_tts"]),            # TTS
            "video": bool(r["video_path"]),       # 영상 렌더링
            "thumbnail": int(r["thumbnail_count"] or 0) > 0,# 썸네일
            "upload": bool(r["is_uploaded"]),     # 업로드
            "publish": bool(r.get("is_published", 0)), # 발행
            "desc": bool(r["description"]),       # 설명
            "music_plan": bool(r.get("has_music_plan")),
            "music_cover": has_cover,
            "music_tracks": has_tracks,
            "music_thumbnail": has_thumbnail,
            "music_render": has_render,
            "music_desc": bool(r["description"]),
            "music_publish": has_publish_state,
        }
        if is_music_mode:
            progress.update({
                "plan": bool(r.get("has_music_plan")),
                "video": has_render,
                "upload": has_publish_state,
                "publish": has_publish_state,
            })
        # 가공된 상태 정보 추가
        results.append({
            "id": r["id"],
            "name": r["name"],
            "topic": r["topic"],
            "name_vi": r.get("name_vi") or "",
            "topic_vi": r.get("topic_vi") or "",
            "video_title_vi": r.get("video_title_vi") or "",
            "name_en": r.get("name_en") or "",
            "topic_en": r.get("topic_en") or "",
            "video_title_en": r.get("video_title_en") or "",
            "name_th": r.get("name_th") or "",
            "topic_th": r.get("topic_th") or "",
            "video_title_th": r.get("video_title_th") or "",
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "video_title": r["video_title"],
            "status": r["project_status"], # String status
            "qa_status": r.get("qa_status") or "",
            "qa_hold_upload": r.get("qa_hold_upload") or "0",
            "qa_checked_at": r.get("qa_checked_at") or "",
            "app_mode": r["app_mode"], # [NEW]
            "progress": progress
        })
    return results

def mark_project_dirty(project_id: int):
    """Supabase project metadata sync 대상 표시."""
    if not project_id:
        return
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE projects SET sync_dirty = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (project_id,))
        conn.commit()
    finally:
        conn.close()


def mark_project_synced(project_id: int, synced_at: str = None):
    """Supabase project metadata sync 성공 표시."""
    if not project_id:
        return
    synced_at = synced_at or datetime.utcnow().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE projects SET sync_dirty = 0, last_synced_at = ? WHERE id = ?",
            (synced_at, project_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_project_remote_deleted(project_id: int, deleted_at: str = None):
    """Supabase row soft-delete 성공 표시."""
    if not project_id:
        return
    deleted_at = deleted_at or datetime.utcnow().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE projects SET remote_deleted_at = ?, sync_dirty = 0, last_synced_at = ? WHERE id = ?",
            (deleted_at, deleted_at, project_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_dirty_projects(employee_email: str = None, limit: int = 20) -> List[Dict]:
    """Supabase metadata sync가 필요한 프로젝트 목록."""
    conn = get_db()
    cursor = conn.cursor()
    if employee_email:
        cursor.execute(
            """
            SELECT * FROM projects
            WHERE (sync_dirty = 1 OR last_synced_at IS NULL OR last_synced_at = '')
              AND (employee_email = ? OR employee_email IS NULL OR employee_email = '')
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (employee_email, limit),
        )
    else:
        cursor.execute(
            """
            SELECT * FROM projects
            WHERE sync_dirty = 1 OR last_synced_at IS NULL OR last_synced_at = ''
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_project(project_id: int, **kwargs):
    """프로젝트 업데이트"""
    if not kwargs:
        return
    conn = get_db()
    cursor = conn.cursor()

    if "target_language" in kwargs and "language" not in kwargs:
        kwargs["language"] = kwargs.pop("target_language")

    updates = ", ".join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values()) + [project_id]

    cursor.execute(
        f"UPDATE projects SET {updates}, sync_dirty = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        values
    )
    conn.commit()
    conn.close()

def delete_project(project_id: int):
    """프로젝트 삭제 (관련 데이터도 삭제)"""
    mark_project_dirty(project_id)
    conn = get_db()
    cursor = conn.cursor()

    tables = ['analysis', 'script_structure', 'scripts', 'image_prompts',
              'tts_audio', 'metadata', 'thumbnails', 'shorts',
              'project_settings', 'music_track_plans', 'project_sources']
    for table in tables:
        try:
            cursor.execute(f"DELETE FROM {table} WHERE project_id = ?", (project_id,))
        except Exception:
            pass  # Table may not exist yet

    cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()

def move_project(project_id: int, target_mode: str):
    """프로젝트 모드(app_mode) 변경"""
    conn = get_db()
    cursor = conn.cursor()
    # project_settings 테이블의 app_mode 업데이트
    cursor.execute("UPDATE project_settings SET app_mode = ?, updated_at = CURRENT_TIMESTAMP WHERE project_id = ?", (target_mode, project_id))
    # projects 테이블의 status는 유지되지만, 모드에 따라 UI에서 다르게 보일 수 있음
    conn.commit()
    conn.close()
    return True

def copy_project(project_id: int, target_mode: str):
    """프로젝트 전체 데이터 복제 (대상 모드로 변경)"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. 원본 프로젝트 정보 가져오기
    cursor.execute("SELECT name, topic, language FROM projects WHERE id = ?", (project_id,))
    orig = cursor.fetchone()
    if not orig:
        conn.close()
        return None
    
    orig_name, topic, language = orig
    new_name = f"{orig_name} (Copy)"
    
    # 2. 새 프로젝트 생성
    cursor.execute("INSERT INTO projects (name, topic, language) VALUES (?, ?, ?)", 
                   (new_name, topic, language))
    new_pid = cursor.lastrowid
    
    # 3. 데이터 복사 대상 테이블 목록
    tables = [
        ('project_settings', 'id'),
        ('analysis', 'id'),
        ('script_structure', 'id'),
        ('scripts', 'id'),
        ('image_prompts', 'id'),
        ('tts_audio', 'id'),
        ('metadata', 'id'),
        ('thumbnails', 'id'),
        ('project_sources', 'id'),
        ('project_characters', 'id')
    ]
    
    for table, pk_col in tables:
        try:
            # 테이블 컬럼 정보 조회
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [info[1] for info in cursor.fetchall() if info[1] != pk_col]
            
            if not columns:
                continue
            
            # INSERT INTO ... SELECT 문 구성
            col_list = ", ".join(columns)
            
            # SELECT 절 구성 (project_id는 new_pid로, app_mode는 target_mode로 치환)
            select_parts = []
            for col in columns:
                if col == 'project_id':
                    select_parts.append("? as project_id")
                elif col == 'app_mode' and table == 'project_settings':
                    select_parts.append("? as app_mode")
                elif col == 'title' and table == 'project_settings':
                    select_parts.append("? as title") # 썸네일 제목도 새 이름으로? 일단 그대로 둠
                else:
                    select_parts.append(col)
            
            select_list = ", ".join(select_parts)
            
            query = f"INSERT INTO {table} ({col_list}) SELECT {select_list} FROM {table} WHERE project_id = ?"
            
            # 파라미터 구성
            params = [new_pid]
            if 'app_mode' in columns and table == 'project_settings':
                params.append(target_mode)
            if 'title' in columns and table == 'project_settings':
                params.append(new_name)
            params.append(project_id)
            
            cursor.execute(query, tuple(params))
        except Exception as e:
            print(f"[DB] Error copying table {table}: {e}")
            continue
            
    conn.commit()
    conn.close()
    return new_pid


def get_top_analyses(limit: int = 10) -> List[Dict]:
    """바이럴 점수가 높은 과거 분석 데이터 조회 (학습용)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT analysis_result FROM analysis 
        WHERE viral_score >= 80 
        ORDER BY viral_score DESC, created_at DESC 
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# ============ 분석 데이터 ============

def save_analysis(project_id: int, video_data: Dict, analysis_result: Dict):
    """분석 결과 저장"""
    conn = get_db()
    cursor = conn.cursor()

    # 기존 분석 삭제
    cursor.execute("DELETE FROM analysis WHERE project_id = ?", (project_id,))

    # video_id extraction (handle search response which has a dict for id)
    v_id = video_data.get('id', '')
    if isinstance(v_id, dict):
        v_id = v_id.get('videoId', '')

    cursor.execute("""
        INSERT INTO analysis
        (project_id, video_id, video_title, channel_title, thumbnail_url,
         view_count, like_count, comment_count, viral_score, analysis_result)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        project_id,
        v_id,
        video_data.get('snippet', {}).get('title'),
        video_data.get('snippet', {}).get('channelTitle'),
        video_data.get('snippet', {}).get('thumbnails', {}).get('high', {}).get('url'),
        video_data.get('statistics', {}).get('viewCount', 0),
        video_data.get('statistics', {}).get('likeCount', 0),
        video_data.get('statistics', {}).get('commentCount', 0),
        video_data.get('viralScore', 0),
        json.dumps(analysis_result, ensure_ascii=False)
    ))

    conn.commit()
    conn.close()

def get_analysis(project_id: int) -> Optional[Dict]:
    """분석 결과 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM analysis WHERE project_id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        data = dict(row)
        data['analysis_result'] = json.loads(data['analysis_result']) if data['analysis_result'] else {}
        return data
    return None

# ============ 대본 구조 ============

# ============ 대본 ============

def save_script(project_id: int, script: str, word_count: int, duration: int):
    """대본 저장 (scripts 테이블 및 project_settings 테이블 동기화)"""
    conn = get_db()
    cursor = conn.cursor()

    # 1. scripts 테이블 업데이트
    cursor.execute("DELETE FROM scripts WHERE project_id = ?", (project_id,))
    cursor.execute("""
        INSERT INTO scripts (project_id, full_script, word_count, estimated_duration)
        VALUES (?, ?, ?, ?)
    """, (project_id, script, word_count, duration))

    # 2. project_settings 테이블 업데이트 (동기화)
    # project_settings에 해당 프로젝트가 이미 존재하는지 확인
    cursor.execute("SELECT project_id FROM project_settings WHERE project_id = ?", (project_id,))
    if cursor.fetchone():
        cursor.execute("UPDATE project_settings SET script = ?, updated_at = CURRENT_TIMESTAMP WHERE project_id = ?", (script, project_id))
    else:
        cursor.execute("INSERT INTO project_settings (project_id, script) VALUES (?, ?)", (project_id, script))

    conn.commit()
    conn.close()
    mark_project_dirty(project_id)

def update_project_render_status(project_id: int, status: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE projects SET status = ?, sync_dirty = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, project_id))
    conn.commit()
    conn.close()


def create_channel(name: str, handle: str, description: str = None, proxy: str = None) -> int:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO channels (name, handle, description, proxy) VALUES (?, ?, ?, ?)", 
                   (name, handle, description, proxy))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return new_id

def delete_channel(channel_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
    conn.commit()
    conn.close()

def update_channel_credentials(channel_id: int, path: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE channels SET credentials_path = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", 
                   (path, channel_id))
    conn.commit()
    conn.close()

def update_channel(channel_id: int, name: str, handle: str, description: str = None, proxy: str = None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE channels SET name = ?, handle = ?, description = ?, proxy = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", 
                   (name, handle, description, proxy, channel_id))
    conn.commit()
    conn.close()

def get_script(project_id: int) -> Optional[Dict]:
    """대본 조회 (scripts 테이블 우선, 없으면 project_settings 확인)"""
    print(f"[DB_DEBUG] get_script called for project_id: {project_id}")
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. scripts 테이블 조회
    cursor.execute("SELECT * FROM scripts WHERE project_id = ?", (project_id,))
    row = cursor.fetchone()
    
    if row:
        conn.close()
        data = dict(row)
        print(f"[DB_DEBUG] Found in scripts table. Content len: {len(data.get('full_script') or '')}")
        return data
        
    # 2. Fallback: project_settings 테이블 조회
    cursor.execute("SELECT script FROM project_settings WHERE project_id = ?", (project_id,))
    setting_row = cursor.fetchone()
    conn.close()
    
    if setting_row and setting_row['script']:
        print(f"[DB_DEBUG] Found in project_settings. Content len: {len(setting_row['script'])}")
        return {
            'project_id': project_id,
            'full_script': setting_row['script'],
            'word_count': len(setting_row['script']),
            'estimated_duration': 60
        }
        
    print(f"[DB_DEBUG] Script NOT FOUND for project_id: {project_id}")
    return None

def save_script_structure(project_id: int, structure: Dict):
    """대본 구조 저장"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Identify if 'structure' key exists in input (wrapper)
    actual_struct = structure.get("structure", structure)
    
    sections_json = json.dumps(actual_struct.get("sections", []), ensure_ascii=False)
    
    # Check existence
    cursor.execute("SELECT id FROM script_structure WHERE project_id = ?", (project_id,))
    row = cursor.fetchone()
    
    if row:
        cursor.execute("""
            UPDATE script_structure 
            SET hook = ?, sections = ?, cta = ?, style = ?, duration = ?, created_at = CURRENT_TIMESTAMP
            WHERE project_id = ?
        """, (
            actual_struct.get("hook"), 
            sections_json, 
            actual_struct.get("cta"), 
            actual_struct.get("style"), 
            actual_struct.get("duration"), 
            project_id
        ))
    else:
        cursor.execute("""
            INSERT INTO script_structure (project_id, hook, sections, cta, style, duration)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            project_id, 
            actual_struct.get("hook"), 
            sections_json, 
            actual_struct.get("cta"), 
            actual_struct.get("style"), 
            actual_struct.get("duration")
        ))
    
    conn.commit()
    conn.close()
    mark_project_dirty(project_id)

def get_script_structure(project_id: int) -> Optional[Dict]:
    """대본 구조 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM script_structure WHERE project_id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        data = dict(row)
        try:
            sections = json.loads(data['sections']) if data['sections'] else []
        except Exception:
            sections = []
            
        structure_dict = {
             "hook": data.get("hook"),
             "sections": sections,
             "cta": data.get("cta"),
             "style": data.get("style"),
             "duration": data.get("duration")
        }

        # Return wrapper format expected by Autopilot AND flat format for Frontend
        return {
            "project_id": project_id,
            "structure": structure_dict, # For Autopilot
            **structure_dict             # For Frontend (mix-in)
        }
    return None

# ============ 이미지 프롬프트 ============

def update_image_prompt_url(project_id: int, scene_number: int, image_url: str):
    """특정 장면의 이미지 URL 업데이트"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. 해당 프로젝트/장면이 있는지 확인
    cursor.execute(
        "SELECT id FROM image_prompts WHERE project_id = ? AND scene_number = ?",
        (project_id, scene_number)
    )
    exists = cursor.fetchone()
    
    if exists:
        # 업데이트
        cursor.execute("""
            UPDATE image_prompts 
            SET image_url = ?, created_at = CURRENT_TIMESTAMP
            WHERE project_id = ? AND scene_number = ?
        """, (image_url, project_id, scene_number))
    else:
        # 없으면 새로 생성 (프롬프트는 비워둠)
        cursor.execute("""
            INSERT INTO image_prompts (project_id, scene_number, image_url)
            VALUES (?, ?, ?)
        """, (project_id, scene_number, image_url))
        
    conn.commit()
    conn.close()
    mark_project_dirty(project_id)

def update_image_prompt_video_url(project_id: int, scene_number: int, video_url: str):
    """특정 장면의 비디오 URL 업데이트 (Wan 2.2 Motion)"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 해당 프로젝트/장면이 있는지 확인
    cursor.execute(
        "SELECT id FROM image_prompts WHERE project_id = ? AND scene_number = ?",
        (project_id, scene_number)
    )
    exists = cursor.fetchone()
    
    if exists:
        # 업데이트
        cursor.execute("""
            UPDATE image_prompts 
            SET video_url = ?, created_at = CURRENT_TIMESTAMP
            WHERE project_id = ? AND scene_number = ?
        """, (video_url, project_id, scene_number))
        
    conn.commit()
    conn.close()
    mark_project_dirty(project_id)

# ============ TTS ============

def save_tts(project_id: int, voice_id: str, voice_name: str, audio_path: str, duration: float):
    """TTS 저장"""
    import time
    max_retries = 3
    retry_delay = 0.5
    
    for attempt in range(max_retries):
        try:
            conn = get_db()
            cursor = conn.cursor()

            try:
                cursor.execute("DELETE FROM tts_audio WHERE project_id = ?", (project_id,))

                cursor.execute("""
                    INSERT INTO tts_audio (project_id, voice_id, voice_name, audio_path, duration)
                    VALUES (?, ?, ?, ?, ?)
                """, (project_id, voice_id, voice_name, audio_path, duration))

                conn.commit()
                mark_project_dirty(project_id)
                return True
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower():
                    raise e # Let outer handle retry
                else:
                    print(f"Error saving TTS: {e}")
                    raise e
            finally:
                conn.close()

        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < max_retries - 1:
                print(f"[DB] Database locked in save_tts, retrying... ({attempt+1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            else:
                print(f"[DB] Final error in save_tts: {e}")
                raise e # Notify upstream
        except Exception as e:
            print(f"[DB] Unexpected error in save_tts: {e}")
            raise e

def get_tts(project_id: int) -> Optional[Dict]:
    """TTS 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tts_audio WHERE project_id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

# ============ 메타데이터 ============

def save_metadata(project_id: int, titles: List[str], description: str,
                  tags: List[str], hashtags: List[str]):
    """메타데이터 저장"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM metadata WHERE project_id = ?", (project_id,))

    cursor.execute("""
        INSERT INTO metadata (project_id, titles, description, tags, hashtags)
        VALUES (?, ?, ?, ?, ?)
    """, (
        project_id,
        json.dumps(titles, ensure_ascii=False),
        description,
        json.dumps(tags, ensure_ascii=False),
        json.dumps(hashtags, ensure_ascii=False)
    ))

    conn.commit()
    conn.close()
    mark_project_dirty(project_id)

def get_metadata(project_id: int) -> Optional[Dict]:
    """메타데이터 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM metadata WHERE project_id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        data = dict(row)
        data['titles'] = json.loads(data['titles']) if data['titles'] else []
        data['tags'] = json.loads(data['tags']) if data['tags'] else []
        data['hashtags'] = json.loads(data['hashtags']) if data['hashtags'] else []
        return data
    return None

def get_project_metadata(project_id: int, app_mode: Optional[str] = None) -> Optional[Dict]:
    """Return mode-scoped metadata when available, with legacy fallback."""
    settings = get_project_settings(project_id) or {}
    resolved_mode = str(
        app_mode
        or settings.get("app_mode")
        or get_global_setting("app_mode", "longform")
        or "longform"
    ).strip().lower()
    raw_data = settings.get(f"metadata_{resolved_mode}")

    if raw_data:
        try:
            parsed = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
            if isinstance(parsed, dict):
                parsed["titles"] = parsed.get("titles") or []
                parsed["tags"] = parsed.get("tags") or []
                parsed["hashtags"] = parsed.get("hashtags") or []
                return parsed
        except Exception:
            pass

    return get_metadata(project_id)

# ============ 썸네일 ============

def save_thumbnails(project_id: int, ideas: List[Dict], texts: List[str], full_settings: Dict = None):
    """썸네일 아이디어 및 설정 저장"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM thumbnails WHERE project_id = ?", (project_id,))

    cursor.execute("""
        INSERT INTO thumbnails (project_id, ideas, texts, full_settings)
        VALUES (?, ?, ?, ?)
    """, (
        project_id,
        json.dumps(ideas, ensure_ascii=False),
        json.dumps(texts, ensure_ascii=False),
        json.dumps(full_settings, ensure_ascii=False) if full_settings else None
    ))

    conn.commit()
    conn.close()
    mark_project_dirty(project_id)

def get_thumbnails(project_id: int) -> Optional[Dict]:
    """썸네일 아이디어 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM thumbnails WHERE project_id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        data = dict(row)
        data['ideas'] = json.loads(data['ideas']) if data['ideas'] else []
        data['texts'] = json.loads(data['texts']) if data['texts'] else []
        data['full_settings'] = json.loads(data['full_settings']) if data.get('full_settings') else {}
        return data
    return None

# ============ 프로젝트 핵심 설정 (10가지 요소) ============

def save_project_settings(project_id: int, settings: Dict):
    """프로젝트 핵심 설정 저장/업데이트"""
    conn = get_db()
    cursor = conn.cursor()

    # 기존 설정 확인
    cursor.execute("SELECT id FROM project_settings WHERE project_id = ?", (project_id,))
    exists = cursor.fetchone()

    if exists:
        # 업데이트
        fields = []
        values = []
        for key in ['title', 'thumbnail_text', 'thumbnail_url', 'duration_seconds', 'aspect_ratio',
                    'script', 'hashtags', 'voice_tone', 'voice_name', 'voice_language', 'voice_style_prompt', 
                    'video_command', 'video_path', 'is_uploaded',
                    'image_style_prompt', 'subtitle_font', 'subtitle_color', 'target_language', 'subtitle_style_enum',
                    'subtitle_font_size', 'subtitle_stroke_color', 'subtitle_stroke_width', 'subtitle_position_y', 'background_video_url',
                    'character_ref_text', 'character_ref_image_path', 'script_style',
                    'subtitle_base_color', 'subtitle_pos_y', 'subtitle_pos_x', 'subtitle_bg_enabled', 'subtitle_stroke_enabled',
                    'subtitle_line_spacing', 'subtitle_bg_color', 'subtitle_bg_opacity',
                    'subtitle_line_spacing', 'subtitle_bg_color', 'subtitle_bg_opacity',
                    'subtitle_line_spacing', 'subtitle_bg_color', 'subtitle_bg_opacity',
                    'voice_provider', 'voice_speed', 'voice_multi_enabled', 'voice_mapping_json', 'sfx_mapping_json', 'app_mode', 'intro_video_path', 'thumbnail_style', 'image_style',
                    'actual_payout', 'asset_mix_summary_json', 'video_clip_ratio', 'total_scenes', 'video_scenes', 'image_scenes',
                    'webtoon_auto_split', 'webtoon_smart_pan', 'webtoon_convert_zoom', 'webtoon_scenes_json', 'webtoon_plan_json']: # [NEW] Webtoon
            if key in settings:
                fields.append(f"{key} = ?")
                values.append(settings[key])

        if fields:
            values.append(project_id)
            cursor.execute(f"""
                UPDATE project_settings
                SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP
                WHERE project_id = ?
            """, values)
    else:
        # 새로 생성
        cursor.execute("""
            INSERT INTO project_settings
             (project_id, title, thumbnail_text, thumbnail_url, duration_seconds, aspect_ratio,
              script, hashtags, voice_tone, voice_name, voice_language, voice_style_prompt,
              video_command, video_path, is_uploaded,
              image_style_prompt, subtitle_font, subtitle_color, target_language, subtitle_style_enum, subtitle_font_size, subtitle_stroke_color, subtitle_stroke_width, subtitle_position_y, background_video_url, character_ref_text, character_ref_image_path, script_style,
              subtitle_base_color, subtitle_pos_y, subtitle_pos_x, subtitle_bg_enabled, subtitle_stroke_enabled, subtitle_line_spacing, subtitle_bg_color, subtitle_bg_opacity,
              voice_provider, voice_speed, voice_multi_enabled, voice_mapping_json, app_mode, intro_video_path, thumbnail_style, image_style,
              actual_payout, asset_mix_summary_json, video_clip_ratio, total_scenes, video_scenes, image_scenes,
              webtoon_auto_split, webtoon_smart_pan, webtoon_convert_zoom, webtoon_scenes_json, webtoon_plan_json)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
         """, (
            project_id,
            settings.get('title'),
            settings.get('thumbnail_text'),
            settings.get('thumbnail_url'),
            settings.get('duration_seconds', 60),
            settings.get('aspect_ratio', '16:9'),
            settings.get('script'),
            settings.get('hashtags'),
            settings.get('voice_tone', 'neutral'),
            settings.get('voice_name', 'Puck'),
            settings.get('voice_language', 'ko-KR'),
            settings.get('voice_style_prompt'),
            settings.get('video_command'),
            settings.get('video_path'),
            settings.get('is_uploaded', 0),
            settings.get('image_style_prompt'),
            settings.get('subtitle_font', 'Malgun Gothic'),
            settings.get('subtitle_color', 'white'),
            settings.get('target_language', 'ko'),
            settings.get('subtitle_style_enum', 'Basic_White'),
            settings.get('subtitle_font_size', 5.4),
            settings.get('subtitle_stroke_color', 'black'),
            settings.get('subtitle_stroke_width', 0.15),
            settings.get('subtitle_position_y'),
            settings.get('background_video_url'),
            settings.get('character_ref_text'),
            settings.get('character_ref_image_path'),
            settings.get('script_style'),
            settings.get('subtitle_base_color'),
            settings.get('subtitle_pos_y'),
            settings.get('subtitle_pos_x'),
            settings.get('subtitle_bg_enabled', 1),
            settings.get('subtitle_stroke_enabled', 0),
            settings.get('subtitle_line_spacing', 0.1),
            settings.get('subtitle_bg_color', '#000000'),
            settings.get('subtitle_bg_opacity', 0.5),
            settings.get('voice_provider', 'elevenlabs'),
            settings.get('voice_speed', 1.0),
            settings.get('voice_multi_enabled', 0),
            settings.get('voice_mapping_json'),
            settings.get('app_mode', 'longform'),
            settings.get('intro_video_path'),
            settings.get('thumbnail_style'),
            settings.get('image_style'),
            settings.get('actual_payout', 0),
            settings.get('asset_mix_summary_json'),
            settings.get('video_clip_ratio'),
            settings.get('total_scenes', 0),
            settings.get('video_scenes', 0),
            settings.get('image_scenes', 0),
            settings.get('webtoon_auto_split', 1),
            settings.get('webtoon_smart_pan', 1),
            settings.get('webtoon_convert_zoom', 1),
            settings.get('webtoon_scenes_json'),
            settings.get('webtoon_plan_json')
        ))
    conn.commit()
    conn.close()
    mark_project_dirty(project_id)

# ============ 프로젝트 소스 (NotebookLM 기능) ============

def add_project_source(project_id: int, source_type: str, title: str, content: str, url: str = None) -> int:
    """프로젝트 소스 추가"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO project_sources (project_id, type, title, content, url) VALUES (?, ?, ?, ?, ?)",
        (project_id, source_type, title, content, url)
    )
    source_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return source_id

def get_project_sources(project_id: int) -> List[Dict]:
    """프로젝트의 모든 소스 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM project_sources WHERE project_id = ? ORDER BY created_at DESC", (project_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def delete_project_source(source_id: int):
    """프로젝트 소스 삭제"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM project_sources WHERE id = ?", (source_id,))
    conn.commit()
    conn.close()

def delete_all_project_sources(project_id: int):
    """프로젝트의 모든 소스 삭제"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM project_sources WHERE project_id = ?", (project_id,))
    conn.commit()
    conn.close()

def get_project_settings(project_id: int) -> Optional[Dict]:
    """프로젝트 핵심 설정 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM project_settings WHERE project_id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_project_setting(project_id: int, key: str, value: Any):
    """단일 설정 업데이트"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(project_settings)")
    existing_cols = [col[1] for col in cursor.fetchall()]

    if key not in existing_cols:
        # 동적 키 (예: scene_1_motion)는 테이블 스키마에 즉시 추가
        try:
            cursor.execute(f"ALTER TABLE project_settings ADD COLUMN {key} TEXT")
            print(f"[DB] Added new dynamic column: {key}")
        except Exception as e:
            print(f"[DB] Failed to add dynamic column '{key}': {e}")
            conn.close()
            return False

    import time
    max_retries = 3
    retry_delay = 0.5

    for attempt in range(max_retries):
        try:
            cursor.execute(f"""
                UPDATE project_settings
                SET {key} = ?, updated_at = CURRENT_TIMESTAMP
                WHERE project_id = ?
            """, (value, project_id))
            
            # [NEW] 'script' 업데이트 시 scripts 테이블도 동기화
            if key == 'script' and value:
                try:
                    # 대략적인 시간 계산 (한국어 1분당 450자 기준)
                    char_count = len(str(value))
                    est_duration = max(5, int(char_count / 7.5)) # 최소 5초
                    
                    cursor.execute("DELETE FROM scripts WHERE project_id = ?", (project_id,))
                    cursor.execute("""
                        INSERT INTO scripts (project_id, full_script, word_count, estimated_duration)
                        VALUES (?, ?, ?, ?)
                    """, (project_id, value, char_count, est_duration))
                except Exception as e:
                    print(f"[DB] Script sync failed in update_project_setting: {e}")

            if cursor.rowcount == 0:
                conn.close() 
                if attempt == 0: # Only try insert on first failure if it's not a lock issue
                    print("[DB] Row not found, falling back to insert")
                    save_project_settings(project_id, {key: value})
                return True

            conn.commit()
            conn.close()
            mark_project_dirty(project_id)
            return True

        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < max_retries - 1:
                print(f"[DB] Database locked in update_project_setting, retrying in {retry_delay}s... ({attempt+1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay *= 2 # Exponential backoff
                # Re-open connection as cursor might be invalidated? typically just retry exec is enough but safer to loop
                conn.close() # Close and retry gets new conn
                conn = get_db()
                cursor = conn.cursor()
                continue
            else:
                print(f"[DB] Error updating project setting: {e}")
                conn.close()
                return False
        except Exception as e:
             print(f"[DB] Unexpected error in update_project_setting: {e}")
             conn.close()
             return False

    return False


# ============ 학습형 제작 시스템 로그 ============

def _json_dumps_safe(value: Any) -> str:
    try:
        return json.dumps(value or {}, ensure_ascii=False, default=str)
    except Exception:
        return json.dumps({"raw": str(value)}, ensure_ascii=False)


def _json_loads_safe(value: Any, fallback: Any = None) -> Any:
    if value is None or value == "":
        return {} if fallback is None else fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return {} if fallback is None else fallback


def log_learning_event(project_id: int, event_type: str, stage: str = "", payload: Optional[Dict[str, Any]] = None, source: str = "system") -> Optional[int]:
    """제작 과정 학습 이벤트를 append-only로 저장한다."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO project_learning_events (project_id, event_type, stage, source, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project_id, event_type, stage or "", source or "system", _json_dumps_safe(payload)),
        )
        event_id = cursor.lastrowid
        conn.commit()
        return event_id
    except Exception as e:
        print(f"[Learning] Failed to log event: {e}")
        return None
    finally:
        conn.close()


def get_learning_events(project_id: int, limit: int = 200) -> List[Dict[str, Any]]:
    """프로젝트 학습 이벤트 목록 조회."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT * FROM project_learning_events
            WHERE project_id = ?
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT ?
            """,
            (project_id, max(1, min(int(limit or 200), 1000))),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            row["payload"] = _json_loads_safe(row.pop("payload_json", None), {})
        return rows
    finally:
        conn.close()


def create_learning_snapshot(project_id: int, snapshot_type: str = "manual", snapshot: Optional[Dict[str, Any]] = None) -> Optional[int]:
    """프로젝트의 특정 시점 학습 스냅샷을 저장한다."""
    snapshot = snapshot or {}
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO project_learning_snapshots (
                project_id, snapshot_type, reference_json, style_json, script_json,
                thumbnail_json, tts_json, video_json, qa_json, upload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                snapshot_type or "manual",
                _json_dumps_safe(snapshot.get("reference")),
                _json_dumps_safe(snapshot.get("style")),
                _json_dumps_safe(snapshot.get("script")),
                _json_dumps_safe(snapshot.get("thumbnail")),
                _json_dumps_safe(snapshot.get("tts")),
                _json_dumps_safe(snapshot.get("video")),
                _json_dumps_safe(snapshot.get("qa")),
                _json_dumps_safe(snapshot.get("upload")),
            ),
        )
        snapshot_id = cursor.lastrowid
        conn.commit()
        return snapshot_id
    except Exception as e:
        print(f"[Learning] Failed to create snapshot: {e}")
        return None
    finally:
        conn.close()


def get_learning_snapshot(project_id: int, snapshot_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """최근 학습 스냅샷 조회."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if snapshot_type:
            cursor.execute(
                """
                SELECT * FROM project_learning_snapshots
                WHERE project_id = ? AND snapshot_type = ?
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT 1
                """,
                (project_id, snapshot_type),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM project_learning_snapshots
                WHERE project_id = ?
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT 1
                """,
                (project_id,),
            )
        row = cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        for key in ["reference", "style", "script", "thumbnail", "tts", "video", "qa", "upload"]:
            json_key = f"{key}_json"
            data[key] = _json_loads_safe(data.pop(json_key, None), {})
        return data
    finally:
        conn.close()


def get_learning_admin_stats(limit: int = 100) -> Dict[str, Any]:
    """웹어드민용 전체 학습 통계."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) AS c FROM project_learning_events")
        total_events = (cursor.fetchone() or {"c": 0})["c"]
        cursor.execute("SELECT COUNT(*) AS c FROM project_learning_snapshots")
        total_snapshots = (cursor.fetchone() or {"c": 0})["c"]

        cursor.execute("""
            SELECT event_type, COUNT(*) AS count
            FROM project_learning_events
            GROUP BY event_type
            ORDER BY count DESC, event_type ASC
        """)
        event_counts = [dict(row) for row in cursor.fetchall()]

        cursor.execute("""
            SELECT stage, COUNT(*) AS count
            FROM project_learning_events
            GROUP BY stage
            ORDER BY count DESC, stage ASC
        """)
        stage_counts = [dict(row) for row in cursor.fetchall()]

        cursor.execute("""
            SELECT p.id AS project_id, p.name, p.topic, COUNT(e.id) AS event_count,
                   MAX(e.created_at) AS last_event_at
            FROM project_learning_events e
            LEFT JOIN projects p ON p.id = e.project_id
            GROUP BY e.project_id
            ORDER BY datetime(last_event_at) DESC
            LIMIT ?
        """, (max(1, min(int(limit or 100), 500)),))
        project_rows = [dict(row) for row in cursor.fetchall()]

        cursor.execute("""
            SELECT e.*, p.name AS project_name
            FROM project_learning_events e
            LEFT JOIN projects p ON p.id = e.project_id
            ORDER BY datetime(e.created_at) DESC, e.id DESC
            LIMIT ?
        """, (max(1, min(int(limit or 100), 500)),))
        recent_events = [dict(row) for row in cursor.fetchall()]
        for event in recent_events:
            event["payload"] = _json_loads_safe(event.pop("payload_json", None), {})

        manual_reviews = [e for e in recent_events if e.get("event_type") == "manual_review"]
        ratings = []
        for event in manual_reviews:
            try:
                rating = (event.get("payload") or {}).get("rating")
                if rating not in (None, ""):
                    ratings.append(float(rating))
            except Exception:
                pass

        return {
            "total_events": total_events,
            "total_snapshots": total_snapshots,
            "event_counts": event_counts,
            "stage_counts": stage_counts,
            "projects": project_rows,
            "recent_events": recent_events,
            "manual_review_count": next((x["count"] for x in event_counts if x.get("event_type") == "manual_review"), 0),
            "upload_completed_count": next((x["count"] for x in event_counts if x.get("event_type") == "upload_completed"), 0),
            "upload_failed_count": next((x["count"] for x in event_counts if x.get("event_type") == "upload_failed"), 0),
            "qa_hold_count": next((x["count"] for x in event_counts if x.get("event_type") == "qa_hold"), 0),
            "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
        }
    finally:
        conn.close()


def get_unsynced_learning_events(limit: int = 100) -> List[Dict[str, Any]]:
    """Supabase로 아직 전송되지 않은 학습 이벤트 조회."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT e.*, p.sync_id AS project_sync_id, p.employee_email, p.name AS project_name, p.topic AS project_topic
            FROM project_learning_events e
            LEFT JOIN projects p ON p.id = e.project_id
            WHERE e.remote_synced_at IS NULL OR e.remote_synced_at = ''
            ORDER BY datetime(e.created_at) ASC, e.id ASC
            LIMIT ?
            """,
            (max(1, min(int(limit or 100), 500)),),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            row["payload"] = _json_loads_safe(row.pop("payload_json", None), {})
        return rows
    finally:
        conn.close()


def get_unsynced_learning_snapshots(limit: int = 100) -> List[Dict[str, Any]]:
    """Supabase로 아직 전송되지 않은 학습 스냅샷 조회."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT s.*, p.sync_id AS project_sync_id, p.employee_email, p.name AS project_name, p.topic AS project_topic
            FROM project_learning_snapshots s
            LEFT JOIN projects p ON p.id = s.project_id
            WHERE s.remote_synced_at IS NULL OR s.remote_synced_at = ''
            ORDER BY datetime(s.created_at) ASC, s.id ASC
            LIMIT ?
            """,
            (max(1, min(int(limit or 100), 500)),),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            for key in ["reference", "style", "script", "thumbnail", "tts", "video", "qa", "upload"]:
                json_key = f"{key}_json"
                row[key] = _json_loads_safe(row.pop(json_key, None), {})
        return rows
    finally:
        conn.close()


def mark_learning_event_remote_synced(event_id: int, synced_at: str = None):
    synced_at = synced_at or datetime.utcnow().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE project_learning_events SET remote_synced_at = ?, remote_sync_error = NULL WHERE id = ?",
            (synced_at, event_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_learning_snapshot_remote_synced(snapshot_id: int, synced_at: str = None):
    synced_at = synced_at or datetime.utcnow().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE project_learning_snapshots SET remote_synced_at = ?, remote_sync_error = NULL WHERE id = ?",
            (synced_at, snapshot_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_learning_event_remote_sync_error(event_id: int, error: str):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE project_learning_events SET remote_sync_error = ? WHERE id = ?",
            ((error or "")[:1000], event_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_learning_snapshot_remote_sync_error(snapshot_id: int, error: str):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE project_learning_snapshots SET remote_sync_error = ? WHERE id = ?",
            ((error or "")[:1000], snapshot_id),
        )
        conn.commit()
    finally:
        conn.close()


def replace_music_track_plans(project_id: int, tracks: List[Dict[str, Any]]) -> None:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM music_track_plans WHERE project_id = ?", (project_id,))
    for index, track in enumerate(tracks or []):
        if not isinstance(track, dict):
            continue
        cursor.execute(
            """
            INSERT INTO music_track_plans (
                project_id, track_index, title, genre, mood, instruments, lyrics,
                vocalist_gender, vocal_mode, duration_seconds, prompt, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                int(track.get("track_index", index)),
                track.get("title"),
                track.get("genre"),
                track.get("mood"),
                json.dumps(track.get("instruments"), ensure_ascii=False) if isinstance(track.get("instruments"), (list, dict)) else track.get("instruments"),
                track.get("lyrics"),
                track.get("vocalist_gender"),
                track.get("vocal_mode"),
                int(track.get("duration_seconds") or 240),
                track.get("prompt"),
                track.get("status") or "planned",
            ),
        )
    conn.commit()
    conn.close()


def get_music_track_plans(project_id: int) -> List[Dict[str, Any]]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM music_track_plans
        WHERE project_id = ?
        ORDER BY track_index ASC, id ASC
        """,
        (project_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    results: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        instruments = item.get("instruments")
        if isinstance(instruments, str) and instruments.strip():
            try:
                item["instruments"] = json.loads(instruments)
            except Exception:
                pass
        results.append(item)
    return results


def update_music_track_plan(project_id: int, track_index: int, updates: Dict[str, Any]) -> bool:
    allowed_fields = [
        "title",
        "genre",
        "mood",
        "instruments",
        "lyrics",
        "vocalist_gender",
        "vocal_mode",
        "duration_seconds",
        "prompt",
        "status",
    ]
    fields = []
    values: List[Any] = []
    for key in allowed_fields:
        if key not in updates:
            continue
        value = updates[key]
        if key == "instruments" and isinstance(value, (list, dict)):
            value = json.dumps(value, ensure_ascii=False)
        fields.append(f"{key} = ?")
        values.append(value)
    if not fields:
        return False

    conn = get_db()
    cursor = conn.cursor()
    values.extend([project_id, track_index])
    cursor.execute(
        f"""
        UPDATE music_track_plans
        SET {", ".join(fields)}, updated_at = CURRENT_TIMESTAMP
        WHERE project_id = ? AND track_index = ?
        """,
        values,
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated


# ============ 쇼츠 ============

def save_shorts(project_id: int, shorts_data: List[Dict]):
    """쇼츠 데이터 저장"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM shorts WHERE project_id = ?", (project_id,))

    cursor.execute("""
        INSERT INTO shorts (project_id, shorts_data)
        VALUES (?, ?)
    """, (project_id, json.dumps(shorts_data, ensure_ascii=False)))
    conn.commit()
    conn.close()

def get_shorts(project_id: int) -> List[Dict]:
    """쇼츠 데이터 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT shorts_data FROM shorts WHERE project_id = ? ORDER BY created_at DESC", (project_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return json.loads(row['shorts_data'])
    return []



# ============ 캐릭터 관리 ============

def save_project_characters(project_id: int, characters: List[Dict]):
    """캐릭터 목록 저장 (기존 데이터 삭제 후 재저장)"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # 기존 캐릭터 삭제 (단, 이미지는 유지하고 싶다면 업데이트 로직이 필요하지만, 여기선 리셋으로 처리)
        # 이미지 URL 유지를 위해 기존 데이터 조회
        existing_chars = {}
        cursor.execute("SELECT name, image_url FROM project_characters WHERE project_id = ?", (project_id,))
        for row in cursor.fetchall():
            if row['name']:
                existing_chars[row['name']] = row['image_url']

        cursor.execute("DELETE FROM project_characters WHERE project_id = ?", (project_id,))
        
        for char in characters:
            # 기존 이미지 URL 보존 시도
            img_url = char.get('image_url') or existing_chars.get(char.get('name', ''), '')
            dna_yaml = char.get('dna_yaml') or ''
            seed = char.get('seed')
            
            cursor.execute("""
                INSERT INTO project_characters (project_id, name, role, description_ko, prompt_en, image_url, dna_yaml, seed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                project_id, 
                char.get('name', ''), 
                char.get('role', ''), 
                char.get('description_ko', ''), 
                char.get('prompt_en', ''), 
                img_url,
                dna_yaml,
                seed
            ))
        conn.commit()
    except Exception as e:
        print(f"[DB] save_project_characters error: {e}")
        raise e
    finally:
        conn.close()

def get_project_characters(project_id: int) -> List[Dict]:
    """캐릭터 목록 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM project_characters WHERE project_id = ? ORDER BY id", (project_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_character_image(project_id: int, name: str, image_url: str):
    """특정 캐릭터 이미지 업데이트"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE project_characters 
            SET image_url = ? 
            WHERE project_id = ? AND name = ?
        """, (image_url, project_id, name))
        
        if cursor.rowcount == 0:
            print(f"[DB] Warning: No character found to update image for pid={project_id}, name='{name}'")
        else:
            print(f"[DB] Updated character image for pid={project_id}, name='{name}'. Rows: {cursor.rowcount}")
        
        conn.commit()
    except Exception as e:
        print(f"[DB] update_character_image error: {e}")
    finally:
        conn.close()

# ============ 조회 함수 ============

def get_projects() -> List[Dict]:
    """모든 프로젝트 목록 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_all_channels() -> List[Dict]:
    """모든 채널 목록 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM channels ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_channel(channel_id: int) -> Optional[Dict]:
    """특정 채널 정보 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM channels WHERE id = ?", (channel_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_channel_by_handle(handle: str) -> Optional[Dict]:
    """YouTube 채널 핸들/ID로 로컬 채널 정보를 조회"""
    if not handle:
        return None
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM channels WHERE handle = ?", (handle,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_project(project_id: int) -> Optional[Dict]:
    """특정 프로젝트 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def get_project_full_data_v2(project_id: int) -> Optional[Dict]:
    """프로젝트의 모든 데이터 조회 (단일 연결로 배치 처리)"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    project_row = cursor.fetchone()
    if not project_row:
        conn.close()
        return None
    project = dict(project_row)

    # 단일 커서로 모든 테이블 순차 조회 (연결 재생성 없이)
    def _one(sql, params=()):
        cursor.execute(sql, params)
        r = cursor.fetchone()
        return dict(r) if r else None

    def _many(sql, params=()):
        cursor.execute(sql, params)
        return [dict(r) for r in cursor.fetchall()]

    pid = (project_id,)

    settings_row = _one("SELECT * FROM project_settings WHERE project_id = ?", pid)
    analysis_row = _one("SELECT * FROM analysis WHERE project_id = ?", pid)
    structure_row = _one("SELECT * FROM script_structure WHERE project_id = ?", pid)
    script_row    = _one("SELECT * FROM scripts WHERE project_id = ?", pid)
    tts_row       = _one("SELECT * FROM tts_audio WHERE project_id = ?", pid)
    meta_row      = _one("SELECT * FROM metadata WHERE project_id = ?", pid)
    image_rows    = _many("SELECT * FROM image_prompts WHERE project_id = ? ORDER BY scene_number", pid)
    thumb_rows    = _many("SELECT * FROM thumbnails WHERE project_id = ? ORDER BY id DESC", pid)
    shorts_rows   = _many("SELECT * FROM shorts WHERE project_id = ? ORDER BY id DESC", pid)
    char_rows     = _many("SELECT * FROM project_characters WHERE project_id = ?", pid)

    conn.close()

    # analysis JSON 파싱
    if analysis_row and analysis_row.get('analysis_result'):
        try:
            analysis_row['analysis_result'] = json.loads(analysis_row['analysis_result'])
        except Exception:
            pass

    # metadata JSON 파싱
    if meta_row:
        try:
            meta_row['titles'] = json.loads(meta_row['titles']) if meta_row.get('titles') else []
        except Exception:
            meta_row['titles'] = []
        try:
            meta_row['tags'] = json.loads(meta_row['tags']) if meta_row.get('tags') else []
        except Exception:
            meta_row['tags'] = []
        try:
            meta_row['hashtags'] = json.loads(meta_row['hashtags']) if meta_row.get('hashtags') else []
        except Exception:
            meta_row['hashtags'] = []


    # script_structure sections JSON 파싱 + wrapper 포맷
    script_structure = None
    if structure_row:
        try:
            sections = json.loads(structure_row['sections']) if structure_row.get('sections') else []
        except Exception:
            sections = []
        sd = {
            "hook": structure_row.get("hook"),
            "sections": sections,
            "cta": structure_row.get("cta"),
            "style": structure_row.get("style"),
            "duration": structure_row.get("duration"),
        }
        script_structure = {"project_id": project_id, "structure": sd, **sd}

    # script: scripts 테이블 우선, fallback settings
    script = None
    if script_row:
        script = {
            'full_script': script_row.get('full_script', ''),
            'word_count': script_row.get('word_count', 0),
            'estimated_duration': script_row.get('estimated_duration', 0),
            'title': settings_row.get('title') if settings_row else None,
        }
    elif settings_row and settings_row.get('script'):
        script = {
            'full_script': settings_row['script'],
            'word_count': 0,
            'estimated_duration': 0,
            'title': settings_row.get('title'),
        }

    # image_prompts: JSON 필드 파싱
    for ip in image_rows:
        for field in ('character_positions', 'color_palette', 'composition_notes'):
            if ip.get(field):
                try:
                    ip[field] = json.loads(ip[field])
                except Exception:
                    pass

    return {
        'project': project,
        'settings': settings_row,
        'analysis': analysis_row,
        'script_structure': script_structure,
        'script': script,
        'image_prompts': image_rows,
        'tts': tts_row,
        'metadata': meta_row,
        'thumbnails': thumb_rows,
        'shorts': shorts_rows,
        'characters': char_rows,
    }

# ============ 글로벌 설정 (기본값) ============

def save_global_setting(key: str, value: Any):
    """글로벌 설정 저장"""
    conn = get_db()
    cursor = conn.cursor()

    json_val = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)

    cursor.execute("""
        INSERT INTO global_settings (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
    """, (key, json_val))

    conn.commit()
    conn.close()
    invalidate_global_setting_cache(key)

_global_setting_cache: Dict[str, Any] = {}
_global_setting_cache_ts: Dict[str, float] = {}
_GLOBAL_SETTING_TTL = 30.0  # 30초 캐시

def invalidate_global_setting_cache(key: str = None):
    """글로벌 설정 캐시 무효화 (저장 후 호출)"""
    if key:
        _global_setting_cache.pop(key, None)
        _global_setting_cache_ts.pop(key, None)
    else:
        _global_setting_cache.clear()
        _global_setting_cache_ts.clear()

def get_global_setting(key: str, default: Any = None, value_type: str = None) -> Any:
    """글로벌 설정 조회 (TTL 캐시 적용)"""
    now = _time.monotonic()
    if key in _global_setting_cache:
        if now - _global_setting_cache_ts[key] < _GLOBAL_SETTING_TTL:
            val = _global_setting_cache[key]
            # bool 변환은 캐시 후에도 적용
            if value_type == "bool":
                if isinstance(val, bool): return val
                if isinstance(val, str): return val.lower() in ('true', '1', 'yes')
                return bool(val)
            return val if val is not None else default

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM global_settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()

    if row:
        val = row['value']
        try:
            parsed = json.loads(val)
        except Exception:
            parsed = val
        _global_setting_cache[key] = parsed
        _global_setting_cache_ts[key] = now

        if value_type == "bool":
            if isinstance(parsed, bool): return parsed
            if isinstance(parsed, str): return parsed.lower() in ('true', '1', 'yes')
            return bool(parsed)
        return parsed

    _global_setting_cache[key] = None
    _global_setting_cache_ts[key] = now
    return default

def get_subtitle_defaults() -> Dict:
    """자막 기본값 조회 (최근 프로젝트 설정 우선 -> 없으면 글로벌 기본값)"""
    
    # 1. 최근 수정된 프로젝트에서 자막 설정 가져오기 (사용자 경험 연속성 보장)
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT subtitle_font, subtitle_font_size, subtitle_base_color, subtitle_style_enum, 
                   subtitle_stroke_color, subtitle_stroke_width, subtitle_bg_enabled, subtitle_bg_opacity,
                   subtitle_line_spacing, subtitle_bg_color
            FROM project_settings 
            ORDER BY updated_at DESC 
            LIMIT 1
        """)
        row = cursor.fetchone()
        conn.close()
        
        if row and row['subtitle_font']:
            # DB 컬럼 -> Dict 매핑
            return {
                "subtitle_font": row['subtitle_font'],
                "subtitle_font_size": row['subtitle_font_size'],
                "subtitle_color": row['subtitle_base_color'],
                "subtitle_style_enum": row['subtitle_style_enum'],
                "subtitle_stroke_color": row['subtitle_stroke_color'],
                "subtitle_stroke_width": row['subtitle_stroke_width'],
                "subtitle_bg_enabled": row['subtitle_bg_enabled'],
                "subtitle_bg_opacity": row['subtitle_bg_opacity'],
                "subtitle_line_spacing": row['subtitle_line_spacing'],
                "subtitle_bg_color": row['subtitle_bg_color']
            }
    except Exception as e:
        print(f"[DB] Error fetching recent subtitle settings: {e}")

    # 2. Fallback to Global Defaults (if DB is empty or error)
    return get_global_setting("subtitle_default_style", {
        "subtitle_font": "GmarketSansBold", 
        "subtitle_font_size": 5.4,
        "subtitle_color": "white",
        "subtitle_style_enum": "Basic_White",
        "subtitle_stroke_color": "black",
        "subtitle_stroke_width": 0,
        "subtitle_bg_enabled": 1,
        "subtitle_bg_opacity": 0.5,
        "subtitle_line_spacing": 0.1,
        "subtitle_bg_color": "#000000"
    })

# ============ 성공 전략 지식 베이스 (학습 시스템) ============

def save_success_knowledge(category: str, pattern: str, insight: str, source_video_id: str = None, script_style: str = "story"):
    """성공 전략 지식 저장"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 중복 패턴 방지 (단순 체크)
    cursor.execute("SELECT id FROM success_knowledge WHERE pattern = ? AND category = ?", (pattern, category))
    if cursor.fetchone():
        conn.close()
        return
        
    cursor.execute("""
        INSERT INTO success_knowledge (category, pattern, insight, source_video_id, script_style)
        VALUES (?, ?, ?, ?, ?)
    """, (category, pattern, insight, source_video_id, script_style))
    
    conn.commit()
    conn.close()

def get_recent_knowledge(limit: int = 10, category: str = None, script_style: str = None) -> List[Dict]:
    """최근 누적된 지식 조회"""
    conn = get_db()
    cursor = conn.cursor()
    
    query = "SELECT * FROM success_knowledge WHERE 1=1"
    params = []
    
    if category:
        query += " AND category = ?"
        params.append(category)
    if script_style:
        query += " AND script_style = ?"
        params.append(script_style)
        
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_all_knowledge_by_style(script_style: str) -> List[Dict]:
    """특정 스타일에 대한 모든 지식 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM success_knowledge WHERE script_style = ? ORDER BY category", (script_style,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# 초기화는 main.py 등에서 명시적으로 호출 권장
# if __name__ == "__main__":
#     init_db()
#     migrate_db()
# ===========================================
# 이미지 스타일 프리셋 관리
# ===========================================



# ===========================================
# 썸네일 스타일 프리셋 관리
# ===========================================

def get_thumbnail_style_presets() -> Dict[str, Dict[str, Any]]:
    """썸네일 스타일 프리셋 조회 (수정: prompt 키 보장)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM thumbnail_style_presets")
    rows = cursor.fetchall()
    conn.close()
    
    result = {}
    for row in rows:
        row_dict = dict(row)
        result[row_dict['style_key']] = {
            'prompt': row_dict['prompt_value'], # Autopilot expects 'prompt'
            'prompt_value': row_dict['prompt_value'], # Legacy/consistency
            'image_url': row_dict.get('image_url')
        }
    return result


def save_image_prompts(project_id: int, prompts: list):
    import json
    print(f"[DB] save_image_prompts called for {project_id} with {len(prompts)} items")
    
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM image_prompts WHERE project_id = ?", (project_id,))

        for i, prompt in enumerate(prompts):
            cursor.execute("""
                INSERT INTO image_prompts
                (project_id, scene_number, scene_text, prompt_ko, prompt_en, image_url,
                 script_start, script_end, scene_title, video_url,
                 sfx_prompt, bgm_prompt, sfx_url, bgm_url, fade_in, motion_desc, engine,
                 prompt_char, prompt_bg, flow_prompt, scene_type,
                 is_dual, start_frame, end_frame, prompt_en_start, prompt_en_end, scene_text_vi)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                project_id,
                i + 1,
                prompt.get('scene_text') or prompt.get('scene') or prompt.get('prompt_ko') or '',
                prompt.get('prompt_ko') or '',
                prompt.get('prompt_en') or prompt.get('prompt_content') or prompt.get('prompt') or '',
                prompt.get('image_url'),
                prompt.get('script_start') or '',
                prompt.get('script_end') or '',
                prompt.get('scene_title') or '',
                prompt.get('video_url', ''),
                prompt.get('sfx_prompt', ''),
                prompt.get('bgm_prompt', ''),
                prompt.get('sfx_url', ''),
                prompt.get('bgm_url', ''),
                prompt.get('fade_in', ''),
                prompt.get('motion_desc', ''),
                prompt.get('engine', 'wan'),
                prompt.get('prompt_char', ''),
                prompt.get('prompt_bg', ''),
                prompt.get('flow_prompt', ''),
                prompt.get('scene_type', ''),
                prompt.get('is_dual', 0),
                json.dumps(prompt.get('start_frame')) if isinstance(prompt.get('start_frame'), (dict, list)) else prompt.get('start_frame', ''),
                json.dumps(prompt.get('end_frame')) if isinstance(prompt.get('end_frame'), (dict, list)) else prompt.get('end_frame', ''),
                prompt.get('prompt_en_start', ''),
                prompt.get('prompt_en_end', ''),
                prompt.get('scene_text_vi', '')
            ))
        conn.commit()
        mark_project_dirty(project_id)
    except Exception as e:
        print(f"[DB Error] save_image_prompts: {e}")
    finally:
        conn.close()

def update_image_prompt_scene_text_vi(prompt_id: int, scene_text_vi: str):
    """장면 스크립트 베트남어 번역 업데이트"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE image_prompts SET scene_text_vi = ? WHERE id = ?", (scene_text_vi, prompt_id))
    conn.commit()
    conn.close()

def update_image_prompt_scene_text_en(prompt_id: int, scene_text_en: str):
    """장면 스크립트 영어 번역 업데이트"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE image_prompts SET scene_text_en = ? WHERE id = ?", (scene_text_en, prompt_id))
    conn.commit()
    conn.close()

def update_image_prompt_scene_text_th(prompt_id: int, scene_text_th: str):
    """장면 스크립트 태국어 UI 번역 업데이트"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE image_prompts SET scene_text_th = ? WHERE id = ?", (scene_text_th, prompt_id))
    conn.commit()
    conn.close()


def get_image_prompts(project_id: int):
    import json
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT * FROM image_prompts WHERE project_id = ? ORDER BY scene_number",
            (project_id,)
        )
        rows = cursor.fetchall()
        
        prompts = []
        for row in rows:
            d = dict(row)
            # Ensure all keys exist for frontend compatibility
            fields = ['script_start', 'script_end', 'scene_title', 'video_url',
                      'sfx_prompt', 'bgm_prompt', 'sfx_url', 'bgm_url', 'fade_in', 'motion_desc', 'engine',
                      'prompt_char', 'prompt_bg', 'flow_prompt', 'scene_type',
                      'is_dual', 'start_frame', 'end_frame', 'prompt_en_start', 'prompt_en_end', 'scene_text_vi']
            for f in fields:
                if f not in d or d[f] is None:
                    d[f] = ''
            
            # [FIX] Parse JSON for frame objects
            for f in ('start_frame', 'end_frame'):
                if isinstance(d.get(f), str) and d[f].strip().startswith('{'):
                    try:
                        d[f] = json.loads(d[f])
                    except Exception:
                        pass
                if not d.get(f):
                    d[f] = {}

            # [FIX] Default engine should be 'wan' if empty
            if not d.get('engine'): d['engine'] = 'wan'
            
            prompts.append(d)
        return prompts
    except Exception as e:
        print(f"[DB Error] get_image_prompts: {e}")
        return []
    finally:
        conn.close()

# [NEW] Autopilot Presets Helper
def save_autopilot_preset(name: str, settings: dict):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO autopilot_presets (name, settings_json) VALUES (?, ?)", (name, json.dumps(settings, ensure_ascii=False)))
        conn.commit()
    except Exception as e:
        print(f"[DB Error] Save Preset: {e}")
    finally:
        conn.close()

def get_autopilot_presets():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM autopilot_presets ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"[DB Error] Get Presets: {e}")
        return []
    finally:
        conn.close()

def delete_autopilot_preset(preset_id: int):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM autopilot_presets WHERE id = ?", (preset_id,))
        conn.commit()
    except Exception as e:
        print(f"[DB Error] Delete Preset: {e}")
    finally:
        conn.close()

# ============ 스타일 프리셋 관리 ============

def get_style_presets(mode: str = None):
    """이미지 스타일 프리셋 조회. mode 지정 시 해당 mode + 'all' 스타일만 반환"""
    conn = get_db()
    cursor = conn.cursor()
    if mode:
        cursor.execute("SELECT * FROM style_presets WHERE mode = ? OR mode = 'all' OR mode IS NULL", (mode,))
    else:
        cursor.execute("SELECT * FROM style_presets")
    rows = cursor.fetchall()
    conn.close()

    result = {}
    for row in rows:
        row_dict = dict(row)
        result[row_dict['style_key'].lower()] = {
            'prompt_value': row_dict['prompt_value'],
            'image_url': row_dict.get('image_url'),
            'gemini_instruction': row_dict.get('gemini_instruction') or '',
            'mode': row_dict.get('mode') or 'image',
            'display_name_ko': row_dict.get('display_name_ko') or '',
            'display_name_vi': row_dict.get('display_name_vi') or ''
        }
    return result

def get_style_preset(style_key: str) -> Optional[Dict]:
    """단일 이미지 스타일 프리셋 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM style_presets WHERE style_key = ?", (style_key,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        row_dict = dict(row)
        return {
            'style_key': row_dict['style_key'],
            'prompt': row_dict['prompt_value'],
            'image_url': row_dict.get('image_url'),
            'display_name_ko': row_dict.get('display_name_ko') or '',
            'display_name_vi': row_dict.get('display_name_vi') or ''
        }
    return None


def save_style_preset(style_key: str, prompt_value: str, image_url: str = None, gemini_instruction: str = None, mode: str = None, display_name_ko: str = None, display_name_vi: str = None):
    """이미지 스타일 프리셋 저장. mode: 'image'(기본) | 'blog' | 'all'"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM style_presets WHERE style_key = ?", (style_key,))
    existing = cursor.fetchone()

    if existing:
        updates = ["prompt_value = ?", "updated_at = CURRENT_TIMESTAMP"]
        params = [prompt_value]
        if image_url is not None:
            updates.append("image_url = ?")
            params.append(image_url)
        if gemini_instruction is not None:
            updates.append("gemini_instruction = ?")
            params.append(gemini_instruction)
        if mode is not None:
            updates.append("mode = ?")
            params.append(mode)
        if display_name_ko is not None:
            updates.append("display_name_ko = ?")
            params.append(display_name_ko)
        if display_name_vi is not None:
            updates.append("display_name_vi = ?")
            params.append(display_name_vi)
        
        sql = f"UPDATE style_presets SET {', '.join(updates)} WHERE style_key = ?"
        params.append(style_key)
        cursor.execute(sql, tuple(params))
    else:
        effective_mode = mode or 'image'
        cursor.execute("""
            INSERT INTO style_presets (style_key, prompt_value, image_url, gemini_instruction, mode, display_name_ko, display_name_vi)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (style_key, prompt_value, image_url, gemini_instruction, effective_mode, display_name_ko or '', display_name_vi or ''))

    conn.commit()
    conn.close()


def clear_all_style_presets():
    """모든 이미지 스타일 프리셋을 삭제 (sync 전 초기화용)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM style_presets")
    conn.commit()
    conn.close()


# ===========================================
# 자막 스타일 프리셋 관리
# ===========================================


def get_subtitle_style_presets():
    """자막 스타일 프리셋 목록 조회"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name, settings_json FROM subtitle_style_presets ORDER BY name ASC")
        rows = cursor.fetchall()
        return [{"name": row['name'], "settings_json": row['settings_json']} for row in rows]
    except Exception as e:
        print(f"[DB Error] get_subtitle_style_presets: {e}")
        return []
    finally:
        if conn: conn.close()

def save_subtitle_style_preset(name: str, settings_json: str):
    """자막 스타일 프리셋 저장 (Upsert)"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # SQLite doesn't support ON CONFLICT for all versions easily if name is not unique in schema, 
        # but I added UNIQUE(name). 
        # Actually I'll use a simpler replace for older sqlite if needed
        cursor.execute("INSERT OR REPLACE INTO subtitle_style_presets (name, settings_json, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (name, settings_json))
        conn.commit()
    except Exception as e:
        print(f"[DB Error] save_subtitle_style_preset: {e}")
    finally:
        if conn: conn.close()

def delete_subtitle_style_preset(name: str):
    """자막 스타일 프리셋 삭제"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM subtitle_style_presets WHERE name = ?", (name,))
        conn.commit()
    except Exception as e:
        print(f"[DB Error] delete_subtitle_style_preset: {e}")
    finally:
        if conn: conn.close()

def get_shorts_template_presets(category: Optional[str] = None):
    """숏폼 템플릿 프리셋 목록 조회"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if category:
            cursor.execute("SELECT name, settings_json, image_path FROM shorts_template_presets WHERE category = ? ORDER BY updated_at DESC", (category,))
        else:
            cursor.execute("SELECT name, settings_json, image_path FROM shorts_template_presets ORDER BY updated_at DESC")
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[DB Error] get_shorts_template_presets: {e}")
        return []
    finally:
        if conn: conn.close()

def get_shorts_template_preset(name: str, category: Optional[str] = None):
    """특정 숏폼 템플릿 조회"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        if category:
            cursor.execute("SELECT * FROM shorts_template_presets WHERE name = ? AND category = ?", (name, category))
        else:
            cursor.execute("SELECT * FROM shorts_template_presets WHERE name = ?", (name,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f"[DB Error] get_shorts_template_preset: {e}")
        return None

def save_shorts_template_preset(name: str, settings_json: str, image_path: Optional[str] = None, category: str = 'shorts'):
    """숏폼 템플릿 프리셋 저장 (Upsert)"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR REPLACE INTO shorts_template_presets (name, settings_json, image_path, category, updated_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)", 
                       (name, settings_json, image_path, category))
        conn.commit()
    except Exception as e:
        print(f"[DB Error] save_shorts_template_preset: {e}")
    finally:
        if conn: conn.close()

def delete_shorts_template_preset(name: str, category: Optional[str] = None):
    """숏폼 템플릿 프리셋 삭제"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if category:
            cursor.execute("DELETE FROM shorts_template_presets WHERE name = ? AND category = ?", (name, category))
        else:
            cursor.execute("DELETE FROM shorts_template_presets WHERE name = ?", (name,))
        conn.commit()
    except Exception as e:
        print(f"[DB Error] delete_shorts_template_preset: {e}")
    finally:
        if conn: conn.close()

def get_script_style_presets():
    """대본 스타일 프리셋 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM script_style_presets")
    rows = cursor.fetchall()
    conn.close()
    
    result = {}
    for row in rows:
        result[row['style_key']] = row['prompt_value']
    return result

def get_script_style_presets_detailed():
    """대본 스타일 프리셋 상세 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM script_style_presets")
    rows = cursor.fetchall()
    conn.close()
    
    result = {}
    for row in rows:
        row_dict = dict(row)
        result[row_dict['style_key']] = {
            'prompt_value': row_dict['prompt_value'],
            'display_name_ko': row_dict.get('display_name_ko') or '',
            'display_name_vi': row_dict.get('display_name_vi') or ''
        }
    return result

def save_script_style_preset(style_key: str, prompt_value: str, display_name_ko: str = None, display_name_vi: str = None):
    """대본 스타일 프리셋 저장"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM script_style_presets WHERE style_key = ?", (style_key,))
    existing = cursor.fetchone()
    
    if existing:
        updates = ["prompt_value = ?", "updated_at = CURRENT_TIMESTAMP"]
        params = [prompt_value]
        if display_name_ko is not None:
            updates.append("display_name_ko = ?")
            params.append(display_name_ko)
        if display_name_vi is not None:
            updates.append("display_name_vi = ?")
            params.append(display_name_vi)
        sql = f"UPDATE script_style_presets SET {', '.join(updates)} WHERE style_key = ?"
        params.append(style_key)
        cursor.execute(sql, tuple(params))
    else:
        cursor.execute("""
            INSERT INTO script_style_presets (style_key, prompt_value, display_name_ko, display_name_vi) 
            VALUES (?, ?, ?, ?)
        """, (style_key, prompt_value, display_name_ko or '', display_name_vi or ''))
    
    conn.commit()
    conn.close()

# Removed duplicate get_thumbnail_style_presets to avoid collision

def save_thumbnail_style_preset(style_key: str, prompt_value: str, image_url: str = None, display_name_ko: str = None, display_name_vi: str = None):
    """썸네일 스타일 프리셋 저장"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM thumbnail_style_presets WHERE style_key = ?", (style_key,))
    existing = cursor.fetchone()
    
    if existing:
        updates = ["prompt_value = ?", "updated_at = CURRENT_TIMESTAMP"]
        params = [prompt_value]
        if image_url is not None:
            updates.append("image_url = ?")
            params.append(image_url)
        if display_name_ko is not None:
            updates.append("display_name_ko = ?")
            params.append(display_name_ko)
        if display_name_vi is not None:
            updates.append("display_name_vi = ?")
            params.append(display_name_vi)
        sql = f"UPDATE thumbnail_style_presets SET {', '.join(updates)} WHERE style_key = ?"
        params.append(style_key)
        cursor.execute(sql, tuple(params))
    else:
        cursor.execute("""
            INSERT INTO thumbnail_style_presets (style_key, prompt_value, image_url, display_name_ko, display_name_vi) 
            VALUES (?, ?, ?, ?, ?)
        """, (style_key, prompt_value, image_url, display_name_ko or '', display_name_vi or ''))
    
    conn.commit()
    conn.close()


# ============================================
# 커머스 비디오 관리 (TopView)
# ============================================

def create_commerce_video(video_data):
    """커머스 비디오 레코드 생성"""
    import json
    conn = get_db()
    cursor = conn.cursor()
    
    product_images_json = json.dumps(video_data.get('product_images', []))
    
    cursor.execute("""
        INSERT INTO commerce_videos (
            product_url, product_name, product_price, product_description,
            product_images, style_preset, model_type, background_type,
            music_type, message, cta, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        video_data.get('product_url'),
        video_data.get('product_name'),
        video_data.get('product_price'),
        video_data.get('product_description'),
        product_images_json,
        video_data.get('style_preset', 'electronics'),
        video_data.get('model_type'),
        video_data.get('background_type'),
        video_data.get('music_type'),
        video_data.get('message'),
        video_data.get('cta', 'buy_now'),
        video_data.get('status', 'pending')
    ))
    
    video_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return video_id

def update_commerce_video(video_id, updates):
    """커머스 비디오 업데이트"""
    conn = get_db()
    cursor = conn.cursor()
    
    set_clauses = []
    values = []
    
    for key, value in updates.items():
        set_clauses.append(f"{key} = ?")
        values.append(value)
    
    set_clauses.append("updated_at = CURRENT_TIMESTAMP")
    
    query = f"""
        UPDATE commerce_videos 
        SET {', '.join(set_clauses)}
        WHERE id = ?
    """
    
    values.append(video_id)
    
    cursor.execute(query, values)
    conn.commit()
    conn.close()

def get_commerce_video(video_id):
    """특정 커머스 비디오 조회"""
    import json
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM commerce_videos WHERE id = ?
    """, (video_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    video = dict(row)
    
    if video.get('product_images'):
        try:
            video['product_images'] = json.loads(video['product_images'])
        except Exception:
            video['product_images'] = []
    
    return video

def get_all_commerce_videos(limit=50):
    """모든 커머스 비디오 조회"""
    import json
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM commerce_videos 
        ORDER BY created_at DESC 
        LIMIT ?
    """, (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    videos = []
    for row in rows:
        video = dict(row)
        
        if video.get('product_images'):
            try:
                video['product_images'] = json.loads(video['product_images'])
            except Exception:
                video['product_images'] = []
        
        videos.append(video)
    
    return videos

def delete_commerce_video(video_id):
    """커머스 비디오 삭제"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        DELETE FROM commerce_videos WHERE id = ?
    """, (video_id,))
    
    conn.commit()
    conn.close()

# ==========================================
# 웹툰 수동 처리 학습 (Learning Rules)
# ==========================================

def get_webtoon_rules():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM webtoon_learning_rules ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_webtoon_rule(condition_type, condition_value, action_type, description):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO webtoon_learning_rules 
        (condition_type, condition_value, action_type, description)
        VALUES (?, ?, ?, ?)
    ''', (condition_type, condition_value, action_type, description))
    conn.commit()
    conn.close()

def delete_webtoon_rule(rule_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM webtoon_learning_rules WHERE id = ?', (rule_id,))
    conn.commit()
    conn.close()

# ==========================================
# 퍼블리시 세션 (원소스 멀티유즈)
# ==========================================

def create_publish_session(project_id: int, title: str, content: str) -> int:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO publish_sessions (project_id, title, content) VALUES (?, ?, ?)",
        (project_id, title, content)
    )
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return session_id

def get_publish_session(session_id: int) -> Optional[Dict]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM publish_sessions WHERE id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_publish_sessions_by_project(project_id: int) -> List[Dict]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM publish_sessions WHERE project_id = ? ORDER BY created_at DESC",
        (project_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_publish_sessions() -> List[Dict]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ps.*, p.name as project_name
        FROM publish_sessions ps
        LEFT JOIN projects p ON ps.project_id = p.id
        ORDER BY ps.updated_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_publish_session(session_id: int, **kwargs):
    conn = get_db()
    cursor = conn.cursor()
    updates = ", ".join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values()) + [session_id]
    cursor.execute(
        f"UPDATE publish_sessions SET {updates}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        values
    )
    conn.commit()
    conn.close()

def delete_publish_session(session_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM publish_images WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM publish_sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()

# 퍼블리시 이미지 CRUD

def add_publish_image(session_id: int, position: int, prompt_ko: str, prompt_en: str) -> int:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO publish_images (session_id, position, prompt_ko, prompt_en) VALUES (?, ?, ?, ?)",
        (session_id, position, prompt_ko, prompt_en)
    )
    image_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return image_id

def get_publish_images(session_id: int) -> List[Dict]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM publish_images WHERE session_id = ? ORDER BY position",
        (session_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_publish_image(image_id: int, **kwargs):
    conn = get_db()
    cursor = conn.cursor()
    updates = ", ".join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values()) + [image_id]
    cursor.execute(
        f"UPDATE publish_images SET {updates} WHERE id = ?",
        values
    )
    conn.commit()
    conn.close()

def delete_publish_image(image_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM publish_images WHERE id = ?", (image_id,))
    conn.commit()
    conn.close()

def get_recent_projects(limit: int = 10, employee_email: str = None) -> List[Dict]:
    """최근 업데이트된 프로젝트 목록 조회 (이메일 필터링 지원)"""
    conn = get_db()
    cursor = conn.cursor()
    if employee_email:
        cursor.execute(
            """
            SELECT * FROM projects
            WHERE employee_email = ? OR employee_email IS NULL OR employee_email = ''
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (employee_email, limit),
        )
    else:
        cursor.execute("SELECT * FROM projects ORDER BY updated_at DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def resolve_remote_user_id_for_log(project_id=None) -> str:
    """Resolve Supabase Auth UUID for remote log sync using the current user email."""
    from pathlib import Path
    from services.web_admin_client import web_admin_client

    license_value = ""
    try:
        license_path = Path(__file__).parent / "license.key"
        if license_path.exists():
            license_value = license_path.read_text(encoding="utf-8").strip()
    except Exception:
        license_value = ""

    email = ""
    try:
        if project_id:
            project = get_project(project_id)
            email = (project or {}).get("employee_email") or ""
    except Exception:
        email = ""

    if not email:
        try:
            from services.auth_service import auth_service
            email = auth_service.get_user_email() or ""
        except Exception:
            email = ""

    return web_admin_client.resolve_user_id(email=email, candidate=license_value)


def add_ai_log(project_id, task_type: str, model_id: str, provider: str, status: str, prompt_summary: str = "", error_msg: str = "", elapsed_time: float = 0.0, input_tokens: int = 0, output_tokens: int = 0, balance_after: int = None, thinking_tokens: int = 0):
    """AI 생성 로그 추가 (로컬 DB + Supabase 원격 동기화)"""
    # 실패한 작업은 토큰 사용량 0으로 처리
    if status == 'failed':
        input_tokens = 0
        output_tokens = 0
        thinking_tokens = 0
    
    # balance_after가 없으면 현재 auth_service에서 가져옴
    if balance_after is None:
        try:
            from services.auth_service import auth_service
            balance_after = auth_service.get_token_balance()
        except:
            pass

    # [NEW] worker_email 가져오기
    worker_email = None
    try:
        from services.auth_service import auth_service
        worker_email = auth_service.get_user_email()
    except:
        pass

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO ai_generation_logs (project_id, task_type, model_id, provider, status, prompt_summary, error_msg, elapsed_time, input_tokens, output_tokens, balance_after, thinking_tokens, worker_email)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, task_type, model_id, provider, status, prompt_summary, error_msg, elapsed_time, input_tokens, output_tokens, balance_after, thinking_tokens, worker_email))
        conn.commit()
    except Exception as e:
        print(f"[DB] Failed to add AI log: {e}")
    finally:
        conn.close()

    # 백그라운드에서 Supabase 원격 동기화 (메인 스레드 블로킹 없음)
    import threading
    def _push_remote():
        try:
            import requests as _req, os as _os
            from pathlib import Path
            base_dir = Path(__file__).parent
            
            user_id = resolve_remote_user_id_for_log(project_id)
            if not user_id:
                print("[Sync] Could not resolve Supabase profile UUID for remote log push")
                return

            # DASHBOARD_URL 환경변수 사용
            base_url = _os.getenv("DASHBOARD_URL", "https://mytube-ashy-seven.vercel.app")
            
            # 로컬 배포 환경 자동 감지 (localhost:3000 우선)
            if _os.getenv("DEBUG") == "true" or _os.path.exists(_os.path.join(base_dir, ".env.local")):
                try:
                    # 로컬 대시보드가 응답하는지 확인
                    check_resp = _req.get("http://localhost:3000/api/health", timeout=0.5, proxies={"http": None, "https": None})
                    if check_resp.status_code == 200:
                        base_url = "http://localhost:3000"
                except Exception:
                    pass

            payload = {
                "userId": user_id,
                "task_type": task_type,
                "model_id": model_id,
                "provider": provider,
                "status": status,
                "prompt_summary": prompt_summary,
                "error_msg": error_msg,
                "elapsed_time": elapsed_time,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "thinking_tokens": thinking_tokens,
                "balance_after": balance_after
            }
            
            resp = _req.post(f"{base_url}/api/logs", json=payload, timeout=10, proxies={"http": None, "https": None})
            if resp.status_code != 200:
                try:
                    print(f"[Sync] Failed to push log to {base_url}: {resp.status_code} {resp.text}")
                except Exception:
                    pass
            else:
                try:
                    print(f"[Sync] Successfully pushed {task_type} log to remote.")
                except Exception:
                    pass
                
        except Exception as e:
            try:
                print(f"[Sync] Error during remote push: {e}")
            except Exception:
                pass
            
    threading.Thread(target=_push_remote, daemon=True).start()


def get_daily_token_usage():
    """오늘 하루 사용한 총 토큰량 합계 반환"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # KST 기준 오늘 날짜 구하기
        from datetime import datetime, timedelta, timezone
        kst = timezone(timedelta(hours=9))
        today = datetime.now(kst).strftime('%Y-%m-%d')
        
        cursor.execute("""
            SELECT SUM(input_tokens + output_tokens) as total 
            FROM ai_generation_logs 
            WHERE date(created_at, 'localtime') = ?
        """, (today,))
        row = cursor.fetchone()
        return row['total'] if row and row['total'] else 0
    except Exception as e:
        print(f"[DB] Failed to get daily token usage: {e}")
        return 0
    finally:
        conn.close()

def get_ai_logs(limit: int = 100, days: int = None) -> List[Dict[str, Any]]:
    """AI 생성 로그 조회 (날짜 필터링 지원)"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        query = """
            SELECT id, project_id, task_type, model_id, provider, status, prompt_summary, error_msg, elapsed_time, input_tokens, output_tokens, balance_after, created_at
            FROM ai_generation_logs
        """
        params = []
        if days:
            query += " WHERE created_at >= datetime('now', ?)"
            params.append(f'-{days} days')
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"[DB] Failed to get AI logs: {e}")
        return []
    finally:
        conn.close()

def clear_ai_logs():
    """모든 AI 로그 삭제"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM ai_generation_logs")
        conn.commit()
    except Exception as e:
        print(f"[DB] Failed to clear AI logs: {e}")
    finally:
        conn.close()



def get_project_settings_by_youtube_id(youtube_video_id: str):
    """유튜브 비디오 ID로 프로젝트 설정을 조회"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM project_settings WHERE youtube_video_id = ?", (youtube_video_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"[DB Error] get_project_settings_by_youtube_id: {e}")
        return None
    finally:
        conn.close()

def get_channel(channel_id: int):
    """ID로 채널 정보를 조회"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM channels WHERE id = ?", (channel_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"[DB Error] get_channel: {e}")
        return None
    finally:
        conn.close()

def get_worker_settlement_stats(
    start_date: str = None,
    end_date: str = None,
    email: str = None,
    approved_only: bool = True,
) -> List[Dict[str, Any]]:
    """직원 정산을 위해 날짜 범위 및 이메일별 작업량 통계를 집계합니다."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # 1. AI 작업량(ai_generation_logs) 집계
        query = """
            SELECT
                COALESCE(worker_email, 'unknown') as worker,
                COUNT(id) as total_ai_tasks,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_ai_tasks,
                SUM(CASE WHEN task_type = 'tts_gen' THEN 1 ELSE 0 END) as tts_tasks,
                SUM(CASE WHEN task_type = 'vision_gen' OR task_type = 'image_crop' THEN 1 ELSE 0 END) as media_tasks
            FROM ai_generation_logs
            WHERE 1=1
        """
        params = []
        if start_date:
            query += " AND created_at >= ?"
            params.append(f"{start_date} 00:00:00")
        if end_date:
            query += " AND created_at <= ?"
            params.append(f"{end_date} 23:59:59")
        if email:
            query += " AND worker_email = ?"
            params.append(email)

        query += " GROUP BY worker"
        cursor.execute(query, params)
        rows = cursor.fetchall()

        # 2. 프로젝트 완료(projects 테이블) 집계 (employee_email 연동)
        approved_statuses = (
            "approved",
            "to_be_published",
            "published",
            "publish_completed",
            "youtube_published",
        )
        approved_status_expr = "LOWER(COALESCE(ps.admin_publish_status, ''))"
        completed_expr = (
            f"CASE WHEN {approved_status_expr} IN ({','.join(['?'] * len(approved_statuses))}) "
            "THEN 1 ELSE 0 END"
            if approved_only
            else "CASE WHEN p.status = 'completed' OR p.status = 'rendered' THEN 1 ELSE 0 END"
        )
        p_query = f"""
            SELECT
                COALESCE(p.employee_email, 'unknown') as worker,
                COUNT(DISTINCT p.id) as total_projects,
                SUM({completed_expr}) as completed_projects,
                SUM(CASE WHEN ({completed_expr}) = 1 THEN CAST(COALESCE(NULLIF(ps.actual_payout, 0), ps.estimated_payout, 0) AS INTEGER) ELSE 0 END) as total_project_payout,
                SUM(CASE WHEN ({completed_expr}) = 1 THEN CAST(COALESCE(ps.estimated_payout, 0) AS INTEGER) ELSE 0 END) as total_estimated_payout,
                SUM(CASE WHEN ({completed_expr}) = 1 THEN CAST(COALESCE(ps.actual_payout, 0) AS INTEGER) ELSE 0 END) as total_actual_payout
            FROM projects p
            LEFT JOIN project_settings ps ON ps.project_id = p.id
            WHERE 1=1
        """
        p_params = list(approved_statuses) if approved_only else []
        if start_date:
            p_query += " AND p.updated_at >= ?"
            p_params.append(f"{start_date} 00:00:00")
        if end_date:
            p_query += " AND p.updated_at <= ?"
            p_params.append(f"{end_date} 23:59:59")
        if email:
            p_query += " AND p.employee_email = ?"
            p_params.append(email)

        p_query += " GROUP BY worker"
        cursor.execute(p_query, p_params)
        p_rows = cursor.fetchall()

        # 매핑 통합
        stats_map = {}
        for r in rows:
            w = r['worker']
            stats_map[w] = {
                "worker": w,
                "total_ai_tasks": r['total_ai_tasks'],
                "success_ai_tasks": r['success_ai_tasks'],
                "tts_tasks": r['tts_tasks'],
                "media_tasks": r['media_tasks'],
                "total_projects": 0,
                "completed_projects": 0
            }

        for pr in p_rows:
            w = pr['worker']
            if w not in stats_map:
                stats_map[w] = {
                    "worker": w,
                    "total_ai_tasks": 0,
                    "success_ai_tasks": 0,
                    "tts_tasks": 0,
                    "media_tasks": 0,
                    "total_projects": 0,
                    "completed_projects": 0,
                    "total_project_payout": 0,
                    "total_estimated_payout": 0,
                    "total_actual_payout": 0,
                }
            stats_map[w]["total_projects"] = pr['total_projects']
            stats_map[w]["completed_projects"] = pr['completed_projects']
            stats_map[w]["total_project_payout"] = pr['total_project_payout'] or 0
            stats_map[w]["total_estimated_payout"] = pr['total_estimated_payout'] or 0
            stats_map[w]["total_actual_payout"] = pr['total_actual_payout'] or 0

        return list(stats_map.values())
    except Exception as e:
        print(f"[DB] Failed to get worker settlement stats: {e}")
        return []
    finally:
        conn.close()


def get_worker_project_history(employee_email: str):
    conn = get_db()
    cursor = conn.cursor()
    try:
        query = '''
            SELECT
                p.id as project_id,
                p.name as project_name,
                p.updated_at as completion_date,
                ps.duration_seconds,
                ps.video_clip_ratio,
                ps.estimated_payout as payout_amount
            FROM projects p
            LEFT JOIN project_settings ps ON p.id = ps.project_id
            WHERE p.employee_email = ? 
              AND p.status IN ('completed', 'rendered', 'published', 'uploaded', 'youtube_published')
            ORDER BY p.updated_at DESC
        '''
        cursor.execute(query, (employee_email,))
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[DB] Error in get_worker_project_history: {e}")
        return []
    finally:
        conn.close()



def create_withdrawal(employee_email: str, amount: float, dest_address: str) -> int:
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO withdrawals (employee_email, amount, dest_address, status) VALUES (?, ?, ?, 'pending')",
            (employee_email, amount, dest_address)
        )
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print(f"[DB] Error creating withdrawal: {e}")
        return 0
    finally:
        conn.close()

def get_worker_withdrawals(employee_email: str):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, amount, dest_address, status, created_at FROM withdrawals WHERE employee_email = ? ORDER BY created_at DESC",
            (employee_email,)
        )
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[DB] Error getting withdrawals: {e}")
        return []
    finally:
        conn.close()



def is_user_admin(email: str) -> bool:
    """Check if user is admin"""
    try:
        result = db.query_single(
            "SELECT is_admin FROM users WHERE email = ?",
            (email,)
        )
        return result[0] if result else False
    except:
        return False


def get_settlement_summary(start_date=None, end_date=None, email=None):
    """Get settlement summary for workers"""
    try:
        query = """
            SELECT
                w.email as worker,
                COUNT(DISTINCT p.id) as total_projects,
                SUM(CASE WHEN p.status = 'completed' THEN 1 ELSE 0 END) as completed_projects,
                COUNT(DISTINCT ai.id) as total_ai_tasks,
                SUM(CASE WHEN ai.status = 'success' THEN 1 ELSE 0 END) as success_ai_tasks,
                COUNT(DISTINCT t.id) as tts_tasks,
                COUNT(DISTINCT m.id) as media_tasks,
                COALESCE(SUM(p.estimated_payout), 0) as total_estimated_payout
            FROM workers w
            LEFT JOIN projects p ON w.email = p.worker_email
            LEFT JOIN ai_tasks ai ON w.email = ai.worker_email
            LEFT JOIN tts_tasks t ON w.email = t.worker_email
            LEFT JOIN media_tasks m ON w.email = m.worker_email
            WHERE 1=1
        """

        params = []

        if start_date:
            query += " AND p.created_at >= ?"
            params.append(start_date)

        if end_date:
            query += " AND p.created_at <= ?"
            params.append(end_date)

        if email:
            query += " AND w.email = ?"
            params.append(email)

        query += " GROUP BY w.email ORDER BY w.email"

        results = db.query(query, tuple(params))

        stats = []
        for row in results:
            stats.append({
                "worker": row[0],
                "total_projects": row[1] or 0,
                "completed_projects": row[2] or 0,
                "total_ai_tasks": row[3] or 0,
                "success_ai_tasks": row[4] or 0,
                "tts_tasks": row[5] or 0,
                "media_tasks": row[6] or 0,
                "total_estimated_payout": row[7] or 0
            })

        return stats
    except Exception as e:
        print(f"Error getting settlement summary: {e}")
        return []

def delete_user_data(email: str) -> bool:
    """탈퇴 회원의 모든 로컬 데이터를 삭제한다."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # 1. 사용자의 프로젝트 id 리스트 가져오기
        cursor.execute("SELECT id FROM projects WHERE employee_email = ?", (email,))
        project_ids = [row[0] for row in cursor.fetchall()]
        
        if project_ids:
            placeholders = ",".join("?" for _ in project_ids)
            
            child_tables = [
                "project_settings", "music_track_plans", "analysis", "script_structure",
                "project_sources", "scripts", "image_prompts", "tts_audio", "metadata",
                "thumbnails", "shorts", "project_characters", "project_feedback", "ai_generation_logs"
            ]
            for table in child_tables:
                try:
                    cursor.execute(f"DELETE FROM {table} WHERE project_id IN ({placeholders})", tuple(project_ids))
                except Exception as e:
                    print(f"[DB Delete] Failed to delete from {table}: {e}")
                    
        # 2. projects 테이블 삭제
        cursor.execute("DELETE FROM projects WHERE employee_email = ?", (email,))
        
        # 3. withdrawals 테이블 삭제
        cursor.execute("DELETE FROM withdrawals WHERE employee_email = ?", (email,))
        
        conn.commit()
        print(f"[DB Delete] Successfully deleted all data for user: {email}")
        return True
    except Exception as e:
        conn.rollback()
        print(f"[DB Delete] Error deleting user data for {email}: {e}")
        return False

