# database.py - SQLite 로컬 데이터베이스
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

DB_PATH = Path(__file__).parent / "data" / "wingsai.db"

def get_db():
    """데이터베이스 연결"""
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """테이블 초기화"""
    conn = get_db()
    cursor = conn.cursor()

    # 프로젝트 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            topic TEXT,
            status TEXT DEFAULT 'draft',
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
            thumbnail_text TEXT,
            thumbnail_url TEXT,
            duration_seconds INTEGER DEFAULT 60,
            aspect_ratio TEXT DEFAULT '9:16',
            script TEXT,
            hashtags TEXT,
            voice_tone TEXT DEFAULT 'neutral',
            voice_name TEXT DEFAULT 'Puck',
            voice_language TEXT DEFAULT 'ko-KR',
            voice_style_prompt TEXT,
            video_command TEXT,
            video_path TEXT,
            is_uploaded INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

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

    # 썸네일 아이디어
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS thumbnails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            ideas TEXT,
            texts TEXT,
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

    conn.commit()
    conn.close()

def migrate_db():
    """기존 테이블에 새 컬럼 추가 (마이그레이션)"""
    conn = get_db()
    cursor = conn.cursor()

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
        
    conn.commit()
    print("[DB] Migration completed")

    conn.close()

# ============ 프로젝트 CRUD ============

def create_project(name: str, topic: str = None) -> int:
    """새 프로젝트 생성 + 기본 설정 초기화"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO projects (name, topic) VALUES (?, ?)",
        (name, topic)
    )
    project_id = cursor.lastrowid

    # 기본 설정 생성
    from services.settings_service import settings_service
    defaults = settings_service.get_gemini_tts_settings()
    
    cursor.execute(
        """INSERT INTO project_settings 
           (project_id, title, voice_name, voice_language, voice_style_prompt) 
           VALUES (?, ?, ?, ?, ?)""",
        (project_id, name, defaults.get("voice_name", "Puck"), 
         defaults.get("language_code", "ko-KR"), defaults.get("style_prompt", ""))
    )

    conn.commit()
    conn.close()
    return project_id

def get_recent_projects(limit: int = 5) -> List[Dict]:
    """최근 프로젝트 목록 조회 (중복 방지용)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, topic FROM projects 
        WHERE status != 'draft' 
        ORDER BY created_at DESC 
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_project(project_id: int) -> Optional[Dict]:
    """프로젝트 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_projects() -> List[Dict]:
    """모든 프로젝트 목록"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects ORDER BY updated_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_project(project_id: int, **kwargs):
    """프로젝트 업데이트"""
    conn = get_db()
    cursor = conn.cursor()

    updates = ", ".join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values()) + [project_id]

    cursor.execute(
        f"UPDATE projects SET {updates}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        values
    )
    conn.commit()
    conn.close()

def delete_project(project_id: int):
    """프로젝트 삭제 (관련 데이터도 삭제)"""
    conn = get_db()
    cursor = conn.cursor()

    tables = ['analysis', 'script_structure', 'scripts', 'image_prompts',
              'tts_audio', 'metadata', 'thumbnails', 'shorts']
    for table in tables:
        cursor.execute(f"DELETE FROM {table} WHERE project_id = ?", (project_id,))

    cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()

# ============ 분석 데이터 ============

def save_analysis(project_id: int, video_data: Dict, analysis_result: Dict):
    """분석 결과 저장"""
    conn = get_db()
    cursor = conn.cursor()

    # 기존 분석 삭제
    cursor.execute("DELETE FROM analysis WHERE project_id = ?", (project_id,))

    cursor.execute("""
        INSERT INTO analysis
        (project_id, video_id, video_title, channel_title, thumbnail_url,
         view_count, like_count, comment_count, viral_score, analysis_result)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        project_id,
        video_data.get('id'),
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

def save_script_structure(project_id: int, structure: Dict):
    """대본 구조 저장"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM script_structure WHERE project_id = ?", (project_id,))

    cursor.execute("""
        INSERT INTO script_structure
        (project_id, hook, sections, cta, style, duration)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        project_id,
        structure.get('hook'),
        json.dumps(structure.get('sections', []), ensure_ascii=False),
        structure.get('cta'),
        structure.get('style'),
        structure.get('duration')
    ))

    conn.commit()
    conn.close()

def get_script_structure(project_id: int) -> Optional[Dict]:
    """대본 구조 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM script_structure WHERE project_id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        data = dict(row)
        data['sections'] = json.loads(data['sections']) if data['sections'] else []
        return data
    return None

# ============ 대본 ============

def save_script(project_id: int, script: str, word_count: int, duration: int):
    """대본 저장"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM scripts WHERE project_id = ?", (project_id,))

    cursor.execute("""
        INSERT INTO scripts (project_id, full_script, word_count, estimated_duration)
        VALUES (?, ?, ?, ?)
    """, (project_id, script, word_count, duration))

    conn.commit()
    conn.close()

def get_script(project_id: int) -> Optional[Dict]:
    """대본 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scripts WHERE project_id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

# ============ 이미지 프롬프트 ============

def save_image_prompts(project_id: int, prompts: List[Dict]):
    """이미지 프롬프트 저장"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM image_prompts WHERE project_id = ?", (project_id,))

    for i, prompt in enumerate(prompts):
        cursor.execute("""
            INSERT INTO image_prompts
            (project_id, scene_number, scene_text, prompt_ko, prompt_en, image_url)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            project_id,
            i + 1,
            prompt.get('scene'),
            prompt.get('prompt_ko'),
            prompt.get('prompt_en'),
            prompt.get('image_url')
        ))

    conn.commit()
    conn.close()

def get_image_prompts(project_id: int) -> List[Dict]:
    """이미지 프롬프트 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM image_prompts WHERE project_id = ? ORDER BY scene_number",
        (project_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# ============ TTS ============

def save_tts(project_id: int, voice_id: str, voice_name: str, audio_path: str, duration: float):
    """TTS 저장"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM tts_audio WHERE project_id = ?", (project_id,))

    cursor.execute("""
        INSERT INTO tts_audio (project_id, voice_id, voice_name, audio_path, duration)
        VALUES (?, ?, ?, ?, ?)
    """, (project_id, voice_id, voice_name, audio_path, duration))

    conn.commit()
    conn.close()

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

# ============ 썸네일 ============

def save_thumbnails(project_id: int, ideas: List[Dict], texts: List[str]):
    """썸네일 아이디어 저장"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM thumbnails WHERE project_id = ?", (project_id,))

    cursor.execute("""
        INSERT INTO thumbnails (project_id, ideas, texts)
        VALUES (?, ?, ?)
    """, (
        project_id,
        json.dumps(ideas, ensure_ascii=False),
        json.dumps(texts, ensure_ascii=False)
    ))

    conn.commit()
    conn.close()

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
                    'video_command', 'video_path', 'is_uploaded']:
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
             video_command, video_path, is_uploaded)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            project_id,
            settings.get('title'),
            settings.get('thumbnail_text'),
            settings.get('thumbnail_url'),
            settings.get('duration_seconds', 60),
            settings.get('aspect_ratio', '9:16'),
            settings.get('script'),
            settings.get('hashtags'),
            settings.get('voice_tone', 'neutral'),
            settings.get('voice_name', 'Puck'),
            settings.get('voice_language', 'ko-KR'),
            settings.get('voice_style_prompt'),
            settings.get('video_command'),
            settings.get('video_path'),
            settings.get('is_uploaded', 0)
        ))

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

    allowed_keys = ['title', 'thumbnail_text', 'thumbnail_url', 'duration_seconds', 'aspect_ratio',
                    'script', 'hashtags', 'voice_tone', 'voice_name', 'voice_language', 'voice_style_prompt',
                    'video_command', 'video_path', 'is_uploaded']

    if key not in allowed_keys:
        conn.close()
        return False

    cursor.execute(f"""
        UPDATE project_settings
        SET {key} = ?, updated_at = CURRENT_TIMESTAMP
        WHERE project_id = ?
    """, (value, project_id))

    conn.commit()
    conn.close()
    return True


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

def get_shorts(project_id: int) -> Optional[Dict]:
    """쇼츠 데이터 조회"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM shorts WHERE project_id = ?", (project_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        data = dict(row)
        data['shorts_data'] = json.loads(data['shorts_data']) if data['shorts_data'] else []
        return data
    return None

# ============ 프로젝트 전체 데이터 ============

def get_project_full_data(project_id: int) -> Optional[Dict]:
    """프로젝트의 모든 데이터 조회"""
    project = get_project(project_id)
    if not project:
        return None

    return {
        'project': project,
        'settings': get_project_settings(project_id),
        'analysis': get_analysis(project_id),
        'script_structure': get_script_structure(project_id),
        'script': get_script(project_id),
        'image_prompts': get_image_prompts(project_id),
        'tts': get_tts(project_id),
        'metadata': get_metadata(project_id),
        'thumbnails': get_thumbnails(project_id),
        'shorts': get_shorts(project_id)
    }

# 초기화
init_db()
migrate_db()
