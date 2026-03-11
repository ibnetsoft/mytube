import sqlite3
conn = sqlite3.connect('data/wingsai.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
cursor.execute("SELECT style_key, prompt_value, gemini_instruction FROM style_presets WHERE style_key = 'k_manhwa'")
row = cursor.fetchone()
if row:
    print("--- prompt_value ---")
    print(row['prompt_value'])
    print("\n--- gemini_instruction ---")
    print(row['gemini_instruction'])
else:
    print("Not Found")
conn.close()
