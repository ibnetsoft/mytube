import sqlite3
import os
import httpx
import asyncio
from dotenv import load_dotenv

async def list_db_voices():
    db_files = [f for f in os.listdir(".") if f.endswith(".db")]
    print("DB Files:", db_files)
    for db in db_files:
        try:
            conn = sqlite3.connect(db)
            c = conn.cursor()
            tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            print(f"\nDatabase: {db} | Tables: {tables}")
            for tbl in tables:
                try:
                    columns = [col[1] for col in c.execute(f"PRAGMA table_info({tbl})").fetchall()]
                    if any("voice" in col.lower() or "name" in col.lower() for col in columns):
                        # Query some rows
                        rows = c.execute(f"SELECT * FROM {tbl} LIMIT 5").fetchall()
                        print(f"  Table: {tbl} | Columns: {columns}")
                        print(f"  Rows: {rows[:3]}")
                except Exception as e:
                    print(f"  Error reading table {tbl}: {e}")
            conn.close()
        except Exception as e:
            print(f"Error opening DB {db}: {e}")

async def list_elevenlabs_voices():
    load_dotenv(override=True)
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        print("No ElevenLabs API key found in .env")
        return
    url = "https://api.elevenlabs.io/v1/voices"
    headers = {"xi-api-key": api_key}
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(url, headers=headers)
            if r.status_code == 200:
                voices = r.json().get("voices", [])
                print("\n--- ElevenLabs Voices ---")
                for v in voices:
                    print(f"Name: {v.get('name')} | ID: {v.get('voice_id')} | Category: {v.get('category')}")
            else:
                print(f"Error fetching ElevenLabs voices: {r.status_code} - {r.text}")
        except Exception as e:
            print(f"Exception fetching ElevenLabs voices: {e}")

async def main():
    await list_db_voices()
    await list_elevenlabs_voices()

if __name__ == "__main__":
    asyncio.run(main())
