import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("DATABASE_URL not found in .env")
    exit(1)

with open('docs/supabase_rpc_referral_admin.sql', 'r', encoding='utf-8') as f:
    sql = f.read()

print("Connecting to Supabase PostgreSQL...")
try:
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cursor = conn.cursor()
    print("Executing SQL script...")
    cursor.execute(sql)
    print("Execution successful!")
    cursor.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
    exit(1)
