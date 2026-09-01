#!/usr/bin/env python3
import os
import sqlite3

DB_PATH = os.path.join("data", "tracker.db")

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for chain_id, name in [(1329, "Sei"), (42220, "Celo")]:
        cursor.execute("SELECT token_address, symbol, decimals, events FROM token_registry WHERE chain_id = ?", (chain_id,))
        rows = cursor.fetchall()
        print("=" * 80)
        print(f"TOKENS FOR {name.upper()} (CHAIN ID {chain_id}): {len(rows)} TOKENS")
        print("=" * 80)
        print(f"{'SYMBOL':<15} | {'DEC':<4} | {'EVENTS':<6} | {'ADDRESS':<42}")
        print("-" * 80)
        unknown_count = 0
        for addr, sym, dec, ev in rows:
            sym_str = sym or "UNKNOWN"
            if "UNKNOWN" in sym_str or sym_str.startswith("0x"):
                unknown_count += 1
            print(f"{sym_str:<15} | {dec:<4} | {ev:<6} | {addr}")
        print(f"\n[i] Total tokens needing enrichment for {name}: {unknown_count} out of {len(rows)}\n")

    conn.close()

if __name__ == "__main__":
    main()
