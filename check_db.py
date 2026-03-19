import sqlite3

def check_db():
    conn = sqlite3.connect('wingsai.db')
    c = conn.cursor()
    c.execute("SELECT key, val FROM global_settings")
    rows = c.fetchall()
    for row in rows:
        key, val = row
        if "token" in key or "secret" in key or "pass" in key:
            print(f"{key}: [HIDDEN]")
        else:
            print(f"{key}: {val}")
    
    # Explicitly check for blog_refresh_token
    c.execute("SELECT val FROM global_settings WHERE key = 'blog_refresh_token'")
    token = c.fetchone()
    if token:
        print(f"DEBUG: blog_refresh_token exists, length: {len(token[0])}")
    else:
        print("DEBUG: blog_refresh_token DOES NOT EXIST in global_settings")
    
    conn.close()

if __name__ == "__main__":
    check_db()
