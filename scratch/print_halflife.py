import sqlite3
import json

db = sqlite3.connect("data/tracker.db")
# Get the maximum ts (latest snapshot)
max_ts = db.execute("SELECT MAX(ts) FROM snapshots").fetchone()[0]
print(f"Latest TS: {max_ts}")
for row in db.execute("SELECT payload_json FROM snapshots WHERE ts = ? AND kind='trade'", (max_ts,)):
    data = json.loads(row[0])
    if data.get("status") == "OK":
        print(f"Symbol: {data.get('symbol')}, Half-life: {data.get('half_life_seconds')} seconds, Pair: {data.get('pair')}, Premium: {data.get('premium_pct')}, ETA: {data.get('eta_days')}")
