import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

import database as db

def check_data():
    try:
        db.init_db()
        conn = db.get_db()
        cursor = conn.cursor()
        
        print("=== Recent Projects & Script Data Check ===")
        
        # Get recent 5 projects
        cursor.execute("SELECT id, name, status, updated_at FROM projects ORDER BY updated_at DESC LIMIT 10")
        projects = cursor.fetchall()
        
        for p in projects:
            pid = p['id']
            name = p['name']
            status = p['status']
            print(f"\n[Project ID: {pid}] Name: {name}, Status: {status}")
            
            # 1. scripts table check
            cursor.execute("SELECT full_script FROM scripts WHERE project_id = ?", (pid,))
            s_row = cursor.fetchone()
            if s_row:
                script_len = len(s_row['full_script']) if s_row['full_script'] else 0
                print(f"  -> TABLE 'scripts': FOUND (Length: {script_len})")
                if script_len > 0:
                    print(f"     Preview: {s_row['full_script'][:50]}...")
            else:
                print(f"  -> TABLE 'scripts': NOT FOUND")
                
            # 2. project_settings table check
            cursor.execute("SELECT script FROM project_settings WHERE project_id = ?", (pid,))
            ps_row = cursor.fetchone()
            if ps_row and ps_row['script']:
                script_len = len(ps_row['script'])
                print(f"  -> TABLE 'project_settings': FOUND (Length: {script_len})")
            else:
                print(f"  -> TABLE 'project_settings': NOT FOUND or Empty")
                
        conn.close()
        print("\n=== End of Check ===")
        
    except Exception as e:
        print(f"Error during diagnosis: {e}")

if __name__ == "__main__":
    check_data()
