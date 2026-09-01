#!/usr/bin/env python3
import os
import sys
import json
import sqlite3
import time
import requests
import dotenv
from web3 import Web3

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from carbon_tracker.storage.db import connect as db_connect, upsert_token

dotenv.load_dotenv()

DB_PATH = os.getenv("DB_PATH", "data/tracker.db")
ETH_RPC_URL = os.getenv("ETH_RPC_URL", "https://rpc.ankr.com/eth")
COMPARISON_FILE = os.path.join("data", "topic1_vs_token_registry_comparison.json")
LOGS_FILE = os.path.join("data", "vortex_eth_topic1_logs.json")
METADATA_CACHE_FILE = os.path.join("data", "token_metadata.json")
CHAIN_ID = 1  # Ethereum Mainnet

def decode_bytes32_string(val_bytes):
    try:
        val_str = val_bytes.rstrip(b'\x00').decode('utf-8', errors='ignore').strip()
        return val_str if val_str else None
    except Exception:
        return None

def fetch_token_metadata_rpc(w3, token_addr):
    """Fetch symbol and decimals of an ERC20 token via Web3 RPC or DexScreener fallback."""
    addr_checksum = Web3.to_checksum_address(token_addr)
    addr_lower = token_addr.lower()

    if addr_lower in ["0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", "0x0000000000000000000000000000000000000000"]:
        return {"symbol": "ETH", "decimals": 18}

    symbol = None
    decimals = 18

    # 1. Query symbol() selector 0x95d89b41 via RPC
    try:
        res = w3.eth.call({'to': addr_checksum, 'data': '0x95d89b41'})
        if res and len(res) >= 32:
            try:
                symbol = w3.codec.decode(['string'], res)[0].strip()
            except Exception:
                symbol = decode_bytes32_string(res)
    except Exception as e:
        pass

    # 2. Query decimals() selector 0x313ce567 via RPC
    try:
        res = w3.eth.call({'to': addr_checksum, 'data': '0x313ce567'})
        if res and len(res) >= 32:
            decimals = int(w3.codec.decode(['uint8'], res)[0])
    except Exception as e:
        pass

    # 3. Fallback to DexScreener if symbol is missing
    if not symbol:
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{addr_lower}"
            resp = requests.get(url, timeout=5).json()
            pairs = resp.get("pairs", [])
            if pairs:
                base_token = pairs[0].get("baseToken", {})
                if base_token.get("address", "").lower() == addr_lower:
                    symbol = base_token.get("symbol")
                else:
                    quote_token = pairs[0].get("quoteToken", {})
                    if quote_token.get("address", "").lower() == addr_lower:
                        symbol = quote_token.get("symbol")
        except Exception:
            pass

    if not symbol:
        symbol = f"UNKNOWN_{token_addr[:6]}"

    return {"symbol": symbol, "decimals": decimals}

def parse_block_num(val):
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        if val.startswith("0x"):
            return int(val, 16)
        return int(val)
    return None

def main():
    print("=" * 80)
    print("INSERTING MISSING TOPIC1 TOKENS INTO TOKEN_REGISTRY (DATA/TRACKER.DB)")
    print("=" * 80)

    # 1. Load comparison report
    if not os.path.exists(COMPARISON_FILE):
        print(f"[X] Comparison file not found: {COMPARISON_FILE}")
        sys.exit(1)

    with open(COMPARISON_FILE, "r", encoding="utf-8") as f:
        comparison_data = json.load(f)

    missing_tokens = comparison_data.get("only_in_topic1", [])
    if not missing_tokens:
        print("[+] No missing tokens to insert. Everything is up to date.")
        return

    missing_addresses = [item["address"].lower() for item in missing_tokens]
    print(f"[+] Found {len(missing_addresses)} missing tokens to enrich & insert into DB.\n")

    # 2. Load log events to determine block ranges
    logs_by_token = {}
    if os.path.exists(LOGS_FILE):
        with open(LOGS_FILE, "r", encoding="utf-8") as f:
            all_logs = json.load(f)

        for log in all_logs:
            topics = log.get("topics", [])
            if len(topics) > 1 and topics[1]:
                clean_topic1 = topics[1].lower()
                if len(clean_topic1) >= 40:
                    addr = "0x" + clean_topic1[-40:]
                    if addr in missing_addresses:
                        blk = parse_block_num(log.get("blockNumber"))
                        if addr not in logs_by_token:
                            logs_by_token[addr] = []
                        if blk is not None:
                            logs_by_token[addr].append(blk)

    # 3. Connect to Web3 RPC
    w3 = Web3(Web3.HTTPProvider(ETH_RPC_URL))
    if not w3.is_connected():
        print(f"[!] Warning: Web3 RPC at {ETH_RPC_URL} not connected. Fallbacks will be used.")

    # 4. Load metadata cache if exists
    meta_cache = {}
    if os.path.exists(METADATA_CACHE_FILE):
        try:
            with open(METADATA_CACHE_FILE, "r", encoding="utf-8") as f:
                meta_cache = json.load(f)
        except Exception:
            meta_cache = {}

    # 5. Connect DB
    db = db_connect(DB_PATH)
    inserted_list = []

    for idx, raw_addr in enumerate(missing_addresses, 1):
        checksum_addr = Web3.to_checksum_address(raw_addr)
        print(f"[{idx}/{len(missing_addresses)}] Processing {checksum_addr}...")

        # Fetch symbol & decimals
        meta = fetch_token_metadata_rpc(w3, checksum_addr)
        print(f"    Symbol: {meta['symbol']} | Decimals: {meta['decimals']}")

        # Save to metadata cache
        meta_cache[raw_addr] = meta

        # Block ranges
        blocks = logs_by_token.get(raw_addr, [])
        first_seen = min(blocks) if blocks else None
        last_seen = max(blocks) if blocks else None
        event_count = len(blocks) if blocks else 1

        info = {
            "first_seen_block": first_seen,
            "last_seen_block": last_seen,
            "events": event_count,
            "last_fee_raw": "0",
            "last_trade_source": "ETH",
            "last_trade_target": meta["symbol"],
            "last_trade_source_amount": "0",
            "last_trade_target_amount": "0",
            "last_trade_block": last_seen
        }

        # Upsert into token_registry
        upsert_token(db, CHAIN_ID, raw_addr, meta, info)
        inserted_list.append({
            "chain_id": CHAIN_ID,
            "token_address": checksum_addr,
            "symbol": meta["symbol"],
            "decimals": meta["decimals"],
            "events": event_count,
            "first_seen_block": first_seen,
            "last_seen_block": last_seen
        })
        time.sleep(0.1)

    db.commit()
    db.close()

    # Save updated metadata cache
    with open(METADATA_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(meta_cache, f, indent=2)

    print("\n" + "=" * 80)
    print("SUCCESSFULLY INSERTED/UPDATED TOKENS IN TOKEN_REGISTRY:")
    print("=" * 80)
    print(f"{'#':<3} | {'SYMBOL':<10} | {'DEC':<4} | {'EVENTS':<6} | {'FIRST BLK':<10} | {'LAST BLK':<10} | {'ADDRESS':<42}")
    print("-" * 90)
    for idx, item in enumerate(inserted_list, 1):
        print(f"{idx:<3} | {item['symbol']:<10} | {item['decimals']:<4} | {item['events']:<6} | {str(item['first_seen_block']):<10} | {str(item['last_seen_block']):<10} | {item['token_address']}")
    print("=" * 90)
    print(f"[✔] Total {len(inserted_list)} tokens successfully added to {DB_PATH} (token_registry table).")

if __name__ == "__main__":
    main()
