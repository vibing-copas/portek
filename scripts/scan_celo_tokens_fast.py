#!/usr/bin/env python3
import os
import sys
import json
import sqlite3
import time
import requests
import dotenv
from web3 import Web3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from carbon_tracker.storage.db import connect as db_connect, upsert_token

dotenv.load_dotenv()

CELO_RPC_URL = os.getenv("CELO_RPC_URL") or "https://rpc.ankr.com/celo/a0834bb80047cb660d1506390713260441065f52f48dd8dc410b1af99a86bf1d"
DB_PATH = os.getenv("DB_PATH", "data/tracker.db")
METADATA_CACHE_FILE = os.path.join("data", "token_metadata.json")
CHAIN_ID = 42220

VORTEX_ADDRESS = Web3.to_checksum_address("0xD9D89e8A0dfE549e5B424D5b511cB3b84A764857")
CONTROLLER_ADDRESS = Web3.to_checksum_address("0x6619871118D144c1c28eC3b23036FC1f0829ed3a")

# Event topic0 signatures
VORTEX_PRICE_UPDATED_TOPIC0 = "0x5a387f90e98064d45229fc077854834539bef69df2b1447346ce29f8761a158f".lower()
VORTEX_TOKEN_TRADED_TOPIC0  = "0x16ddee9b3f1b2e6f797172fe2cd10a214e749294074e075e451f95aecd0b958c".lower()
CONTROLLER_TOKENS_TRADED_TOPIC0 = "0x95f3b01351225fea0e69a46f68b164c9dea10284f12cd4a907ce66510ab7af6a".lower()

# Deployment block for Celo Carbon contracts
START_BLOCK = 66870000  # Carbon deployment on Celo Mainnet

def decode_topic_address(topic_hex: str) -> str:
    if not topic_hex or not isinstance(topic_hex, str):
        return ""
    clean = topic_hex.lower()
    if clean.startswith("0x"):
        clean = clean[2:]
    if len(clean) >= 40:
        raw_addr = "0x" + clean[-40:]
        try:
            return Web3.to_checksum_address(raw_addr)
        except Exception:
            return raw_addr
    return ""

def fetch_logs_rpc_chunked(w3, contract_addr, topic0, from_block, to_block, chunk_size=50000):
    contract_addr = Web3.to_checksum_address(contract_addr)
    all_logs = []
    curr = from_block

    print(f"[*] Scanning {contract_addr[:10]}... logs from block {curr} to {to_block} (chunk {chunk_size})...", flush=True)

    while curr <= to_block:
        end = min(curr + chunk_size - 1, to_block)
        try:
            logs = w3.eth.get_logs({
                "address": contract_addr,
                "fromBlock": curr,
                "toBlock": end,
                "topics": [topic0]
            })
            for l in logs:
                all_logs.append(json.loads(Web3.to_json(l)))
        except Exception as e:
            if chunk_size > 5000:
                chunk_size = chunk_size // 2
        curr = end + 1
        time.sleep(0.001)

    return all_logs

def fetch_token_metadata(w3, token_addr):
    addr_checksum = Web3.to_checksum_address(token_addr)
    addr_lower = token_addr.lower()

    if addr_lower in ["0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", "0x0000000000000000000000000000000000000000"]:
        return {"symbol": "CELO", "decimals": 18}

    symbol = None
    decimals = 18

    # 1. symbol()
    try:
        res = w3.eth.call({'to': addr_checksum, 'data': '0x95d89b41'})
        if res and len(res) >= 32:
            try:
                symbol = w3.codec.decode(['string'], res)[0].strip()
            except Exception:
                try:
                    symbol = res.rstrip(b'\x00').decode('utf-8', errors='ignore').strip()
                except Exception:
                    pass
    except Exception:
        pass

    # 2. decimals()
    try:
        res = w3.eth.call({'to': addr_checksum, 'data': '0x313ce567'})
        if res and len(res) >= 32:
            decimals = int(w3.codec.decode(['uint8'], res)[0])
    except Exception:
        pass

    # 3. DexScreener fallback
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
    print("FAST SCAN: CELO MAINNET LOGS & TOKEN REGISTRY ENRICHMENT")
    print("=" * 80)

    w3 = Web3(Web3.HTTPProvider(CELO_RPC_URL))
    if not w3.is_connected():
        print(f"[X] Cannot connect to Celo RPC: {CELO_RPC_URL}")
        sys.exit(1)

    latest_block = w3.eth.block_number
    print(f"[+] Connected to Celo RPC. Latest Block: {latest_block}")
    print(f"[+] Start Block : {START_BLOCK}")

    # Connect DB
    db = db_connect(DB_PATH)
    cursor = db.cursor()
    cursor.execute("SELECT token_address FROM token_registry WHERE chain_id = ?", (CHAIN_ID,))
    db_tokens = {row[0].lower() for row in cursor.fetchall()}
    print(f"[+] Existing Celo tokens in token_registry: {len(db_tokens)}")

    found_tokens = {}

    # 1. Vortex PriceUpdated logs
    vortex_price_logs = fetch_logs_rpc_chunked(w3, VORTEX_ADDRESS, VORTEX_PRICE_UPDATED_TOPIC0, START_BLOCK, latest_block)
    print(f"    -> Retrieved {len(vortex_price_logs)} Vortex PriceUpdated events.")
    for l in vortex_price_logs:
        topics = l.get("topics", [])
        if len(topics) > 1 and topics[1]:
            addr = decode_topic_address(topics[1])
            if addr and len(addr) == 42:
                raw = addr.lower()
                blk = parse_block_num(l.get("blockNumber"))
                if raw not in found_tokens:
                    found_tokens[raw] = []
                if blk:
                    found_tokens[raw].append(blk)

    # 2. Vortex TokenTraded logs
    vortex_traded_logs = fetch_logs_rpc_chunked(w3, VORTEX_ADDRESS, VORTEX_TOKEN_TRADED_TOPIC0, START_BLOCK, latest_block)
    print(f"    -> Retrieved {len(vortex_traded_logs)} Vortex TokenTraded events.")
    for l in vortex_traded_logs:
        topics = l.get("topics", [])
        if len(topics) > 2 and topics[2]:
            addr = decode_topic_address(topics[2])
            if addr and len(addr) == 42:
                raw = addr.lower()
                blk = parse_block_num(l.get("blockNumber"))
                if raw not in found_tokens:
                    found_tokens[raw] = []
                if blk:
                    found_tokens[raw].append(blk)

    # 3. Controller TokensTraded logs
    ctrl_traded_logs = fetch_logs_rpc_chunked(w3, CONTROLLER_ADDRESS, CONTROLLER_TOKENS_TRADED_TOPIC0, START_BLOCK, latest_block)
    print(f"    -> Retrieved {len(ctrl_traded_logs)} Controller TokensTraded events.")
    for l in ctrl_traded_logs:
        topics = l.get("topics", [])
        blk = parse_block_num(l.get("blockNumber"))
        if len(topics) > 2 and topics[2]:
            addr2 = decode_topic_address(topics[2])
            if addr2 and len(addr2) == 42:
                raw2 = addr2.lower()
                if raw2 not in found_tokens:
                    found_tokens[raw2] = []
                if blk:
                    found_tokens[raw2].append(blk)
        if len(topics) > 3 and topics[3]:
            addr3 = decode_topic_address(topics[3])
            if addr3 and len(addr3) == 42:
                raw3 = addr3.lower()
                if raw3 not in found_tokens:
                    found_tokens[raw3] = []
                if blk:
                    found_tokens[raw3].append(blk)

    all_scanned_addrs = set(found_tokens.keys())
    missing_addrs = all_scanned_addrs - db_tokens

    print(f"\n[+] Total unique Celo tokens found on-chain: {len(all_scanned_addrs)}")
    print(f"[+] NEW Celo tokens to insert: {len(missing_addrs)}")

    # Metadata cache
    meta_cache = {}
    if os.path.exists(METADATA_CACHE_FILE):
        try:
            with open(METADATA_CACHE_FILE, "r", encoding="utf-8") as f:
                meta_cache = json.load(f)
        except Exception:
            pass

    if missing_addrs:
        inserted_count = 0
        print(f"\n[*] Enriching & inserting {len(missing_addrs)} new Celo tokens...")

        for idx, raw_addr in enumerate(sorted(list(missing_addrs)), 1):
            checksum_addr = Web3.to_checksum_address(raw_addr)
            meta = fetch_token_metadata(w3, checksum_addr)
            meta_cache[raw_addr] = meta

            blocks = found_tokens.get(raw_addr, [])
            first_seen = min(blocks) if blocks else START_BLOCK
            last_seen = max(blocks) if blocks else latest_block
            events_count = len(blocks) if blocks else 1

            info = {
                "first_seen_block": first_seen,
                "last_seen_block": last_seen,
                "events": events_count,
                "last_fee_raw": "0",
                "last_trade_source": "CELO",
                "last_trade_target": meta["symbol"],
                "last_trade_source_amount": "0",
                "last_trade_target_amount": "0",
                "last_trade_block": last_seen
            }

            upsert_token(db, CHAIN_ID, raw_addr, meta, info)
            inserted_count += 1
            print(f"   [{idx:2d}/{len(missing_addrs)}] Inserted {meta['symbol']:<12} (Dec: {meta['decimals']:<2}, Events: {events_count:<4}) -> {checksum_addr}")
            time.sleep(0.1)

        db.commit()
        with open(METADATA_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(meta_cache, f, indent=2)

        print(f"\n[+] Successfully added {inserted_count} new Celo tokens to token_registry.")
    else:
        print("[+] All Celo tokens found on-chain are already registered in token_registry.")

    db.close()
    print("=" * 80)

if __name__ == "__main__":
    main()
