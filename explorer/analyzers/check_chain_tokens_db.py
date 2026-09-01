#!/usr/bin/env python3
import os
import sqlite3

DB_PATH = os.path.join("data", "tracker.db")

def main():
    if not os.path.exists(DB_PATH):
        print(f"DB not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT chain_id, COUNT(*) FROM token_registry GROUP BY chain_id")
    rows = cursor.fetchall()

    chain_names = {
        1: "Ethereum",
        1329: "Sei",
        42220: "Celo",
        239: "TAC",
        2632500: "COTI"
    }

    print("=" * 60)
    print("TOKEN REGISTRY COUNTS BY CHAIN IN DATA/TRACKER.DB")
    print("=" * 60)
    for chain_id, count in rows:
        name = chain_names.get(chain_id, f"Chain {chain_id}")
        print(f"Chain {chain_id:7d} ({name:<10}): {count:4d} tokens in token_registry")
    print("=" * 60)

    conn.close()

if __name__ == "__main__":
    main()
