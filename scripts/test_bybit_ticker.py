import sqlite3
import os
from pathlib import Path
from dotenv import load_dotenv

# Load env
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)
db_path = os.getenv("DB_PATH", "data/tracker.db")

try:
    conn = sqlite3.connect(ROOT / db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT chain_id, count(*) FROM token_registry GROUP BY chain_id")
    rows = cursor.fetchall()
    print("Tokens in token_registry:")
    for r in rows:
        print(f"Chain {r[0]}: {r[1]} tokens")
    
    cursor.execute("SELECT chain_id, token_address, symbol FROM token_registry LIMIT 5")
    print("Sample tokens:")
    for r in cursor.fetchall():
        print(r)
    conn.close()
except Exception as e:
    print("DB Error:", e)

try:
    import aiohttp
    print("aiohttp is installed!")
except ImportError:
    print("aiohttp is NOT installed")
