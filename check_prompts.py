import sqlite3
import json

def check_recent_prompts():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT prompt_en, prompt_char FROM image_prompts ORDER BY id DESC LIMIT 10")
    rows = cursor.fetchall()
    for i, row in enumerate(rows):
        print(f"--- Prompt {i+1} ---")
        print(f"EN: {row[0]}")
        print(f"CHAR: {row[1]}")
    conn.close()

if __name__ == "__main__":
    check_recent_prompts()
