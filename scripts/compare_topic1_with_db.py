#!/usr/bin/env python3
import os
import sys
import json
import sqlite3
from web3 import Web3

DB_PATH = os.path.join("data", "tracker.db")
TOPIC1_FILE = os.path.join("data", "vortex_eth_topic1_addresses.json")
OUTPUT_COMPARISON_JSON = os.path.join("data", "topic1_vs_token_registry_comparison.json")

def checksum(addr):
    try:
        return Web3.to_checksum_address(addr)
    except Exception:
        return addr.lower()

def main():
    print("=" * 80)
    print("COMPARISON: TOPIC1 LOG ADDRESSES VS TOKEN_REGISTRY IN TRACKER.DB (CHAIN_ID = 1)")
    print("=" * 80)

    # 1. Load topic1 addresses
    if not os.path.exists(TOPIC1_FILE):
        print(f"[X] File not found: {TOPIC1_FILE}")
        sys.exit(1)

    with open(TOPIC1_FILE, "r", encoding="utf-8") as f:
        topic1_data = json.load(f)

    raw_topic1_addrs = topic1_data.get("unique_addresses", [])
    topic1_set = {checksum(a) for a in raw_topic1_addrs}
    topic1_occurrences = {checksum(k): v for k, v in topic1_data.get("address_occurrences", {}).items()}

    print(f"[+] Total unique addresses from topic1 logs : {len(topic1_set)}")

    # 2. Query token_registry in tracker.db for chain_id = 1
    if not os.path.exists(DB_PATH):
        print(f"[X] Database file not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT token_address, symbol FROM token_registry WHERE chain_id = 1")
    db_rows = cursor.fetchall()
    conn.close()

    db_set = {checksum(r[0]): (r[1] or "UNKNOWN") for r in db_rows}
    print(f"[+] Total token addresses in token_registry (ETH, chain_id=1): {len(db_set)}")

    # 3. Compare sets
    in_both = topic1_set.intersection(set(db_set.keys()))
    only_in_topic1 = topic1_set - set(db_set.keys())
    only_in_db = set(db_set.keys()) - topic1_set

    print("-" * 80)
    print(f"📊 COMPARISON SUMMARY:")
    print(f"  • In BOTH topic1 and token_registry : {len(in_both)}")
    print(f"  • ONLY in topic1 (missing from DB)  : {len(only_in_topic1)}")
    print(f"  • ONLY in DB (missing from topic1)  : {len(only_in_db)}")
    print("-" * 80)

    # Prepare lists for detail
    in_both_details = sorted([
        {"address": a, "symbol": db_set[a], "events_in_topic1": topic1_occurrences.get(a, 0)}
        for a in in_both
    ], key=lambda x: x["symbol"])

    only_in_topic1_details = sorted([
        {"address": a, "events_in_topic1": topic1_occurrences.get(a, 0)}
        for a in only_in_topic1
    ], key=lambda x: x["address"])

    only_in_db_details = sorted([
        {"address": a, "symbol": db_set[a]}
        for a in only_in_db
    ], key=lambda x: x["symbol"])

    # 4. Print details
    if only_in_topic1_details:
        print("\n⚠️  ADDRESSES IN TOPIC1 BUT NOT IN DB TOKEN_REGISTRY:")
        for item in only_in_topic1_details:
            print(f"   - {item['address']} ({item['events_in_topic1']} events)")

    if only_in_db_details:
        print("\nℹ️  ADDRESSES IN DB TOKEN_REGISTRY BUT NOT IN TOPIC1:")
        for item in only_in_db_details:
            print(f"   - {item['address']} (Symbol: {item['symbol']})")

    # 5. Save report
    report = {
        "summary": {
            "total_topic1": len(topic1_set),
            "total_db": len(db_set),
            "in_both_count": len(in_both),
            "only_in_topic1_count": len(only_in_topic1),
            "only_in_db_count": len(only_in_db)
        },
        "in_both": in_both_details,
        "only_in_topic1": only_in_topic1_details,
        "only_in_db": only_in_db_details
    }

    with open(OUTPUT_COMPARISON_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\n[✔] Detailed comparison report saved to: {OUTPUT_COMPARISON_JSON}")
    print("=" * 80)

if __name__ == "__main__":
    main()
