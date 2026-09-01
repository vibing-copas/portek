#!/usr/bin/env python3
import os
import sys
import json
import sqlite3
import dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from carbon_tracker.storage.db import connect, snapshot

dotenv.load_dotenv()
DB_PATH = os.getenv("DB_PATH", "data/tracker.db")
TOTALS_FILE = os.path.join("data", "vortex_eth_trade_totals.json")
CHAIN_ID = 1

def import_trades_to_snapshots():
    if not os.path.exists(TOTALS_FILE):
        print(f"[-] File {TOTALS_FILE} not found.")
        return

    with open(TOTALS_FILE, "r", encoding="utf-8") as f:
        totals_data = json.load(f)

    db = connect(DB_PATH)
    imported_count = 0

    for token_item in totals_data:
        token_addr = token_item["address"].lower()
        level = token_item["level"]
        trades = token_item.get("trades", [])

        for tr in trades:
            ts = tr.get("timestamp_raw", 0)
            payload = {
                "chain_id": CHAIN_ID,
                "token_address": token_addr,
                "symbol": token_item["symbol"],
                "level": level,
                "pair_name": tr.get("pair_name"),
                "tx_hash": tr.get("tx_hash"),
                "block_number": tr.get("block_number"),
                "caller": tr.get("caller"),
                "source_symbol": tr.get("source_symbol"),
                "source_formatted": tr.get("source_formatted"),
                "target_formatted": tr.get("target_formatted"),
                "usd_value": tr.get("usd_value", 0.0)
            }
            snapshot(db, ts, CHAIN_ID, "vortex_trade_event", level, token_addr, payload)
            imported_count += 1

    db.commit()
    print(f"[+] Successfully imported {imported_count} individual Vortex trade event snapshots into {DB_PATH}.")
    db.close()

if __name__ == "__main__":
    import_trades_to_snapshots()
