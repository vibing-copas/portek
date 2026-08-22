import sqlite3
import json

DB_PATH = "data/tracker.db"
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Get latest ts per chain
cursor.execute("""
    SELECT s.chain_id, s.kind, s.level, s.payload_json
    FROM snapshots s
    INNER JOIN (
        SELECT chain_id, MAX(ts) as max_ts
        FROM snapshots
        GROUP BY chain_id
    ) latest ON s.chain_id = latest.chain_id AND s.ts = latest.max_ts
""")

rows = cursor.fetchall()
l1_count = 0
l1_profitable = 0
l2_count = 0
l2_profitable = 0

for r in rows:
    chain_id, kind, level, payload_json = r
    if kind == "trade":
        payload = json.loads(payload_json)
        profit = parseFloat = float(payload.get("estimated_profit_usd") or 0)
        available = float(payload.get("available") or 0)
        
        if level == 1:
            l1_count += 1
            if profit > 0.01 and available > 0:
                l1_profitable += 1
        elif level == 2:
            l2_count += 1
            if profit > 0.01 and available > 0:
                l2_profitable += 1

print(f"Level 1 trades: {l1_count} total, {l1_profitable} with profit > 0.01 and available > 0")
print(f"Level 2 trades: {l2_count} total, {l2_profitable} with profit > 0.01 and available > 0")

conn.close()
