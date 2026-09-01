#!/usr/bin/env python3
import os
import sys
import json
import sqlite3
import time
import requests
import yaml
import dotenv
from web3 import Web3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from carbon_tracker.storage.db import connect as db_connect, upsert_token

dotenv.load_dotenv()

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
DB_PATH = os.getenv("DB_PATH", "data/tracker.db")
METADATA_CACHE_FILE = os.path.join("data", "token_metadata.json")

# Topic0 filters
VORTEX_PRICE_UPDATED_TOPIC0 = "0x5a387f90e98064d45229fc077854834539bef69df2b1447346ce29f8761a158f".lower()
VORTEX_TOKEN_TRADED_TOPIC0  = "0x16ddee9b3f1b2e6f797172fe2cd10a214e749294074e075e451f95aecd0b958c".lower()
CONTROLLER_TOKENS_TRADED_TOPIC0 = "0x95f3b01351225fea0e69a46f68b164c9dea10284f12cd4a907ce66510ab7af6a".lower()

CHAIN_CONFIGS = {
    "sei": {
        "chain_id": 1329,
        "name": "Sei",
        "rpc": os.getenv("SEI_RPC_URL") or "https://evm-rpc.sei-apis.com",
        "vortex": "0x5715203B16F15d7349Cb1E3537365E9664EAf933",
        "controller": "0xe4816658ad10bF215053C533cceAe3f59e1f1087",
        "creation_block": 229000000,
        "chunk_size": 1800
    },
    "celo": {
        "chain_id": 42220,
        "name": "Celo",
        "rpc": os.getenv("CELO_RPC_URL") or "https://rpc.ankr.com/celo/a0834bb80047cb660d1506390713260441065f52f48dd8dc410b1af99a86bf1d",
        "vortex": "0xD9D89e8A0dfE549e5B424D5b511cB3b84A764857",
        "controller": "0x6619871118D144c1c28eC3b23036FC1f0829ed3a",
        "creation_block": 25000000,
        "chunk_size": 100000
    }
}

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

def decode_bytes32_string(val_bytes):
    try:
        val_str = val_bytes.rstrip(b'\x00').decode('utf-8', errors='ignore').strip()
        return val_str if val_str else None
    except Exception:
        return None

def fetch_token_metadata(w3, token_addr):
    addr_checksum = Web3.to_checksum_address(token_addr)
    addr_lower = token_addr.lower()

    if addr_lower in ["0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", "0x0000000000000000000000000000000000000000"]:
        return {"symbol": "NATIVE", "decimals": 18}

    symbol = None
    decimals = 18

    # 1. symbol() 0x95d89b41
    try:
        res = w3.eth.call({'to': addr_checksum, 'data': '0x95d89b41'})
        if res and len(res) >= 32:
            try:
                symbol = w3.codec.decode(['string'], res)[0].strip()
            except Exception:
                symbol = decode_bytes32_string(res)
    except Exception:
        pass

    # 2. decimals() 0x313ce567
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

def fetch_logs_chunked(w3, contract_addr, topics, from_block, to_block, chunk_size=100000):
    contract_addr = Web3.to_checksum_address(contract_addr)
    all_logs = []
    curr = from_block

    while curr <= to_block:
        end = min(curr + chunk_size - 1, to_block)
        try:
            logs = w3.eth.get_logs({
                "address": contract_addr,
                "fromBlock": curr,
                "toBlock": end,
                "topics": topics
            })
            for l in logs:
                all_logs.append(json.loads(Web3.to_json(l)))
            curr = end + 1
            time.sleep(0.1)
        except Exception as e:
            err_str = str(e)
            if "earliest available block" in err_str:
                import re
                match = re.search(r"earliest available block (\d+)", err_str)
                if match:
                    earliest_block = int(match.group(1))
                    print(f"    [!] RPC is pruned. Fast-forwarding start block to earliest available: {earliest_block}")
                    curr = max(curr, earliest_block)
                    continue
            if chunk_size > 10000:
                chunk_size = chunk_size // 2
                print(f"    [!] RPC error chunk {curr}-{end}: {e}. Reduced chunk size to {chunk_size}...")
            else:
                print(f"    [!] Error fetching chunk {curr}-{end}: {e}. Skipping chunk.")
                curr = end + 1
    return all_logs

def process_chain(chain_key, cfg, db, meta_cache):
    chain_id = cfg["chain_id"]
    name = cfg["name"]
    rpc_url = cfg["rpc"]
    vortex_addr = cfg["vortex"]
    controller_addr = cfg["controller"]
    start_block = cfg["creation_block"]
    chunk_size = cfg["chunk_size"]

    print("\n" + "=" * 80)
    print(f"SCANNING {name.upper()} (CHAIN ID {chain_id}) FROM BLOCK {start_block} TO LATEST")
    print("=" * 80)

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print(f"[X] Could not connect to RPC for {name}: {rpc_url}")
        return 0

    latest_block = w3.eth.block_number
    print(f"[+] Connected to {name} RPC. Current latest block: {latest_block}")

    # 1. Existing tokens in DB
    cursor = db.cursor()
    cursor.execute("SELECT token_address FROM token_registry WHERE chain_id = ?", (chain_id,))
    db_tokens = {row[0].lower() for row in cursor.fetchall()}
    print(f"[+] Existing tokens in token_registry for {name}: {len(db_tokens)}")

    found_tokens = {}

    # 2. Fetch Vortex PriceUpdated logs (topic1 = token)
    print(f"[*] Scanning Vortex PriceUpdated logs ({vortex_addr})...")
    vortex_price_logs = fetch_logs_chunked(w3, vortex_addr, [VORTEX_PRICE_UPDATED_TOPIC0], start_block, latest_block, chunk_size)
    print(f"    -> Found {len(vortex_price_logs)} Vortex PriceUpdated events.")
    for l in vortex_price_logs:
        topics = l.get("topics", [])
        if len(topics) > 1 and topics[1]:
            addr = decode_topic_address(topics[1])
            if addr and len(addr) == 42:
                raw = addr.lower()
                blk = l.get("blockNumber")
                if raw not in found_tokens:
                    found_tokens[raw] = []
                if blk:
                    found_tokens[raw].append(int(blk, 16) if isinstance(blk, str) and blk.startswith("0x") else int(blk))

    # 3. Fetch Controller TokensTraded logs (topic2 = sourceToken, topic3 = targetToken)
    print(f"[*] Scanning Controller TokensTraded logs ({controller_addr})...")
    ctrl_traded_logs = fetch_logs_chunked(w3, controller_addr, [CONTROLLER_TOKENS_TRADED_TOPIC0], start_block, latest_block, chunk_size)
    print(f"    -> Found {len(ctrl_traded_logs)} Controller TokensTraded events.")
    for l in ctrl_traded_logs:
        topics = l.get("topics", [])
        blk = l.get("blockNumber")
        blk_num = int(blk, 16) if isinstance(blk, str) and blk.startswith("0x") else (int(blk) if blk else None)
        
        # topic2
        if len(topics) > 2 and topics[2]:
            addr2 = decode_topic_address(topics[2])
            if addr2 and len(addr2) == 42:
                raw2 = addr2.lower()
                if raw2 not in found_tokens:
                    found_tokens[raw2] = []
                if blk_num:
                    found_tokens[raw2].append(blk_num)
                    
        # topic3
        if len(topics) > 3 and topics[3]:
            addr3 = decode_topic_address(topics[3])
            if addr3 and len(addr3) == 42:
                raw3 = addr3.lower()
                if raw3 not in found_tokens:
                    found_tokens[raw3] = []
                if blk_num:
                    found_tokens[raw3].append(blk_num)

    all_scanned_addrs = set(found_tokens.keys())
    missing_addrs = all_scanned_addrs - db_tokens

    print(f"\n[+] Total unique tokens scanned on-chain for {name}: {len(all_scanned_addrs)}")
    print(f"[+] NEW tokens to insert for {name}: {len(missing_addrs)}")

    if not missing_addrs:
        print(f"[+] No new tokens found for {name}. token_registry is already up to date.")
        return 0

    inserted_count = 0
    print(f"\n[*] Fetching metadata & inserting {len(missing_addrs)} new tokens for {name}...")

    for idx, raw_addr in enumerate(sorted(list(missing_addrs)), 1):
        checksum_addr = Web3.to_checksum_address(raw_addr)
        meta = fetch_token_metadata(w3, checksum_addr)
        meta_cache[raw_addr] = meta

        blocks = found_tokens.get(raw_addr, [])
        first_seen = min(blocks) if blocks else start_block
        last_seen = max(blocks) if blocks else latest_block
        events_count = len(blocks) if blocks else 1

        info = {
            "first_seen_block": first_seen,
            "last_seen_block": last_seen,
            "events": events_count,
            "last_fee_raw": "0",
            "last_trade_source": "NATIVE",
            "last_trade_target": meta["symbol"],
            "last_trade_source_amount": "0",
            "last_trade_target_amount": "0",
            "last_trade_block": last_seen
        }

        upsert_token(db, chain_id, raw_addr, meta, info)
        inserted_count += 1
        print(f"   [{idx:2d}/{len(missing_addrs)}] Inserted {meta['symbol']:<12} (Dec: {meta['decimals']:<2}, Events: {events_count:<4}) -> {checksum_addr}")
        time.sleep(0.1)

    db.commit()
    print(f"[+] Successfully added {inserted_count} new tokens to {name} token_registry.")
    return inserted_count

def main():
    db = db_connect(DB_PATH)

    meta_cache = {}
    if os.path.exists(METADATA_CACHE_FILE):
        try:
            with open(METADATA_CACHE_FILE, "r", encoding="utf-8") as f:
                meta_cache = json.load(f)
        except Exception:
            pass

    total_added = 0
    for chain_key, cfg in CHAIN_CONFIGS.items():
        total_added += process_chain(chain_key, cfg, db, meta_cache)

    db.close()

    with open(METADATA_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(meta_cache, f, indent=2)

    print("\n" + "=" * 80)
    print(f"SUMMARY: Total {total_added} new tokens added to token_registry across Sei & Celo.")
    print("=" * 80)

if __name__ == "__main__":
    main()
