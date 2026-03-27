#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
데이터베이스 마이그레이션: 자막 설정 컬럼 추가
"""

import sqlite3
import os

def migrate():
    """project_settings 테이블에 누락된 자막 설정 컬럼 추가"""
    db_path = "data/wingsai.db"
    
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 추가할 컬럼들
    columns_to_add = [
        ("subtitle_base_color", "TEXT DEFAULT 'white'"),
        ("subtitle_pos_x", "TEXT"),
        ("subtitle_pos_y", "TEXT"),
    ]
    
    for column_name, column_type in columns_to_add:
        try:
            # 컬럼이 이미 있는지 확인
            cursor.execute(f"PRAGMA table_info(project_settings)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if column_name in columns:
                print(f"✓ Column '{column_name}' already exists")
            else:
                # 컬럼 추가
                cursor.execute(f"ALTER TABLE project_settings ADD COLUMN {column_name} {column_type}")
                print(f"✓ Added column '{column_name}'")
        except Exception as e:
            print(f"✗ Error adding column '{column_name}': {e}")
    
    conn.commit()
    conn.close()
    print("\n✅  Migration completed!")

if __name__ == "__main__":
    migrate()
