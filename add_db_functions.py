#!/usr/bin/env python3
"""Add database helper functions for settlement and admin checks"""

import re

file_path = "database.py"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Check if functions already exist
if 'def is_user_admin' in content:
    print("Functions already exist")
    exit(0)

# Add new functions before the end of file
new_functions = '''

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
'''

# Find a good place to insert - before the last class or function
# Look for the end of the file or last function definition
insert_position = len(content)

# Write the file
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content[:insert_position] + new_functions + content[insert_position:])

print("Database helper functions added successfully")
