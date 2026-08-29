import sqlite3
import json

conn = sqlite3.connect('data/tracker.db')
cursor = conn.cursor()

latest_ts = cursor.execute("SELECT MAX(ts) FROM snapshots").fetchone()[0]
print(f"Latest ts: {latest_ts}")

rows = cursor.execute(
    "SELECT chain_id, kind, level, token_address, payload_json FROM snapshots WHERE ts = ?", (latest_ts,)
).fetchall()

print(f"Total rows for latest ts ({latest_ts}): {len(rows)}")

for r in rows:
    cid, kind, level, addr, payload_str = r
    payload = json.loads(payload_str)
    symbol = payload.get("symbol", "")
    print(f"Chain: {cid} | Kind: {kind} | Level: {level} | Token: {symbol} ({addr})")
    if "eth" in symbol.lower() or addr.lower() in ["0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"]:
        print("  -> PAYLOAD:", json.dumps(payload, indent=2))

conn.close()
