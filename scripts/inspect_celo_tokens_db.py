#!/usr/bin/env python3
import os
import sqlite3

DB_PATH = "data/tracker.db"

def inspect_celo():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT symbol, decimals, token_address, first_seen_block, last_seen_block, events
        FROM token_registry
        WHERE chain_id = 42220
        ORDER BY symbol ASC
    """)
    rows = cursor.fetchall()
    conn.close()

    print("=" * 80)
    print(f"CELO MAINNET (CHAIN ID 42220) TOKENS IN TOKEN_REGISTRY ({len(rows)} TOKENS)")
    print("=" * 80)
    for idx, (sym, dec, addr, f_blk, l_blk, evts) in enumerate(rows, 1):
        print(f"{idx:2d}. {sym:<12} (Dec: {dec:<2}, Events: {evts:<4}) -> {addr}")

if __name__ == "__main__":
    inspect_celo()
