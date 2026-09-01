#!/usr/bin/env python3
import os
import sqlite3
import dotenv

dotenv.load_dotenv()
DB_PATH = os.getenv("DB_PATH", "data/tracker.db")

def cleanup_database():
    if not os.path.exists(DB_PATH):
        print(f"[-] Database {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print(f"[+] Cleaning up duplicate token entries in {DB_PATH}...")

    # 1. Normalize token_registry addresses to lowercase and merge duplicates
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS token_registry_clean (
            chain_id INTEGER NOT NULL, 
            token_address TEXT NOT NULL, 
            symbol TEXT, 
            decimals INTEGER,
            first_seen_block INTEGER, 
            last_seen_block INTEGER, 
            events INTEGER, 
            last_fee_raw TEXT,
            last_trade_source TEXT, 
            last_trade_target TEXT, 
            last_trade_source_amount TEXT, 
            last_trade_target_amount TEXT, 
            last_trade_block INTEGER,
            PRIMARY KEY(chain_id, token_address)
        );
    """)

    cursor.execute("""
        INSERT OR REPLACE INTO token_registry_clean (
            chain_id, token_address, symbol, decimals,
            first_seen_block, last_seen_block, events, last_fee_raw,
            last_trade_source, last_trade_target,
            last_trade_source_amount, last_trade_target_amount, last_trade_block
        )
        SELECT 
            chain_id, 
            LOWER(token_address) as token_address, 
            MAX(symbol) as symbol, 
            MAX(decimals) as decimals,
            MIN(first_seen_block) as first_seen_block, 
            MAX(last_seen_block) as last_seen_block, 
            SUM(events) as events, 
            MAX(last_fee_raw) as last_fee_raw,
            MAX(last_trade_source) as last_trade_source, 
            MAX(last_trade_target) as last_trade_target,
            MAX(last_trade_source_amount) as last_trade_source_amount, 
            MAX(last_trade_target_amount) as last_trade_target_amount, 
            MAX(last_trade_block) as last_trade_block
        FROM token_registry
        GROUP BY chain_id, LOWER(token_address);
    """)

    cursor.execute("DROP TABLE token_registry;")
    cursor.execute("ALTER TABLE token_registry_clean RENAME TO token_registry;")

    # 2. Normalize snapshots token_address to lowercase
    cursor.execute("UPDATE snapshots SET token_address = LOWER(token_address);")

    # 3. Deduplicate snapshots table (keep highest id per ts, chain_id, kind, token_address)
    cursor.execute("""
        DELETE FROM snapshots 
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM snapshots
            GROUP BY ts, chain_id, kind, COALESCE(level, -1), LOWER(token_address)
        );
    """)

    conn.commit()

    reg_count = cursor.execute("SELECT COUNT(*) FROM token_registry").fetchone()[0]
    snap_count = cursor.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]

    print(f"[+] Cleanup completed successfully!")
    print(f"[+] Total unique tokens in token_registry: {reg_count}")
    print(f"[+] Total snapshots after deduplication: {snap_count}")

    conn.close()

if __name__ == "__main__":
    cleanup_database()
