#!/usr/bin/env python3
import os
import sys
import json
import sqlite3
import dotenv

# Ensure project root is in python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from carbon_tracker.storage.db import connect, upsert_token, save_scan_progress

dotenv.load_dotenv()

DB_PATH = os.getenv("DB_PATH", "data/tracker.db")
TOTALS_FILE = os.path.join("data", "vortex_eth_trade_totals.json")
LOGS_FILE = os.path.join("data", "vortex_eth_logs.json")
CHAIN_ID = 1  # Ethereum Mainnet

def main():
    if not os.path.exists(TOTALS_FILE):
        print(f"Error: {TOTALS_FILE} not found.")
        return

    with open(TOTALS_FILE, "r", encoding="utf-8") as f:
        totals_data = json.load(f)

    print(f"Loaded {len(totals_data)} tokens from {TOTALS_FILE}.")

    # Connect to SQLite database
    db = connect(DB_PATH)
    print(f"Connected to database at {DB_PATH}.")

    consolidated_count = 0
    min_block = None
    max_block = None

    for item in totals_data:
        token_addr = item["address"].lower()
        symbol = item["symbol"]
        decimals = item["decimals"]
        trades = item.get("trades", [])
        
        events_count = item.get("trade_count", len(trades))
        
        # Calculate block ranges and last trade details
        first_seen = None
        last_seen = None
        last_trade = trades[0] if trades else {}
        
        if trades:
            blocks = [t["block_number"] for t in trades if "block_number" in t]
            if blocks:
                first_seen = min(blocks)
                last_seen = max(blocks)
                if min_block is None or first_seen < min_block:
                    min_block = first_seen
                if max_block is None or last_seen > max_block:
                    max_block = last_seen

        meta = {
            "symbol": symbol,
            "decimals": decimals
        }
        
        info = {
            "first_seen_block": first_seen,
            "last_seen_block": last_seen,
            "events": events_count,
            "last_fee_raw": str(item.get("total_raw", "0")),
            "last_trade_source": item.get("source_symbol", "ETH"),
            "last_trade_target": symbol,
            "last_trade_source_amount": str(last_trade.get("source_formatted", "")),
            "last_trade_target_amount": str(last_trade.get("target_formatted", "")),
            "last_trade_block": last_seen
        }

        upsert_token(db, CHAIN_ID, token_addr, meta, info)
        consolidated_count += 1

    # Save scan progress in database
    if min_block and max_block:
        save_scan_progress(db, CHAIN_ID, min_block, max_block)

    db.commit()
    print(f"\n[+] Successfully consolidated {consolidated_count} unique tokens into {DB_PATH} (token_registry table).")
    print(f"[+] Scan progress updated for Chain ID {CHAIN_ID}: First Block={min_block}, Last Block={max_block}.")

    # Inspect SQLite contents
    rows = db.execute("SELECT chain_id, token_address, symbol, decimals, events, first_seen_block, last_seen_block FROM token_registry WHERE chain_id=1 ORDER BY events DESC LIMIT 15").fetchall()
    print("\n--- Top 15 Consolidated Tokens in token_registry ---")
    print(f"{'CHAIN':<6} | {'SYMBOL':<12} | {'DEC':<4} | {'EVENTS':<8} | {'ADDRESS':<42}")
    print("-" * 80)
    for r in rows:
        print(f"{r[0]:<6} | {r[2]:<12} | {r[3]:<4} | {r[4]:<8} | {r[1]}")
    print("-" * 80)

    db.close()

if __name__ == "__main__":
    main()
