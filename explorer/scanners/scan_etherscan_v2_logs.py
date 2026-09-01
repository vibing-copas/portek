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

ETHERSCAN_API = os.getenv("ETHERSCAN_API", "RI1364SKZMWSMCE2KD1NCHM7A354W6MSDS")
DB_PATH = os.getenv("DB_PATH", "data/tracker.db")
METADATA_CACHE_FILE = os.path.join("data", "token_metadata.json")
ETHERSCAN_V2_URL = "https://api.etherscan.io/v2/api"

# Topic0 filters
VORTEX_PRICE_UPDATED_TOPIC0 = "0x5a387f90e98064d45229fc077854834539bef69df2b1447346ce29f8761a158f".lower()
VORTEX_TOKEN_TRADED_TOPIC0  = "0x16ddee9b3f1b2e6f797172fe2cd10a214e749294074e075e451f95aecd0b958c".lower()
CONTROLLER_TOKENS_TRADED_TOPIC0 = "0x95f3b01351225fea0e69a46f68b164c9dea10284f12cd4a907ce66510ab7af6a".lower()

CHAINS = {
    "sei": {
        "chain_id": 1329,
        "name": "Sei Mainnet",
        "rpc": os.getenv("SEI_RPC_URL") or "https://evm-rpc.sei-apis.com",
        "vortex": "0x5715203B16F15d7349Cb1E3537365E9664EAf933",
        "controller": "0xe4816658ad10bF215053C533cceAe3f59e1f1087",
        "from_block": 105711575
    },
    "celo": {
        "chain_id": 42220,
        "name": "Celo Mainnet",
        "rpc": os.getenv("CELO_RPC_URL") or "https://rpc.ankr.com/celo/a0834bb80047cb660d1506390713260441065f52f48dd8dc410b1af99a86bf1d",
        "vortex": "0xD9D89e8A0dfE549e5B424D5b511cB3b84A764857",
        "controller": "0x6619871118D144c1c28eC3b23036FC1f0829ed3a",
        "from_block": 30349600  # Exact Celo deployment block
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

def fetch_logs_etherscan_v2(chain_id, contract_addr, topic0, from_block=0, w3=None):
    """Fetch event logs via Etherscan V2 API, with fast RPC fallback."""
    params = {
        "chainid": chain_id,
        "module": "logs",
        "action": "getLogs",
        "address": contract_addr,
        "fromBlock": from_block,
        "toBlock": "latest",
        "topic0": topic0,
        "apikey": ETHERSCAN_API
    }
    try:
        res = requests.get(ETHERSCAN_V2_URL, params=params, timeout=30).json()
        status = res.get("status")
        result = res.get("result", [])
        if status == "1" and isinstance(result, list):
            return result
    except Exception:
        pass

    # Fast Web3 RPC fallback starting from exact creation block
    if w3 and w3.is_connected():
        try:
            latest_blk = w3.eth.block_number
            chunk_size = 100000
            all_logs = []
            curr = from_block
            while curr <= latest_blk:
                end = min(curr + chunk_size - 1, latest_blk)
                try:
                    logs = w3.eth.get_logs({
                        "address": Web3.to_checksum_address(contract_addr),
                        "fromBlock": curr,
                        "toBlock": end,
                        "topics": [topic0]
                    })
                    for l in logs:
                        all_logs.append(json.loads(Web3.to_json(l)))
                except Exception:
                    pass
                curr = end + 1
            return all_logs
        except Exception as rpc_err:
            print(f"    [!] Web3 RPC fallback error: {rpc_err}")
    return []

def fetch_token_metadata_web3(w3, token_addr):
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
                try:
                    symbol = res.rstrip(b'\x00').decode('utf-8', errors='ignore').strip()
                except Exception:
                    pass
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

def parse_block_num(val):
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        if val.startswith("0x"):
            return int(val, 16)
        return int(val)
    return None

def process_chain(chain_key, cfg, db, meta_cache):
    chain_id = cfg["chain_id"]
    name = cfg["name"]
    rpc_url = cfg["rpc"]
    vortex_addr = cfg["vortex"]
    controller_addr = cfg["controller"]
    from_block = cfg["from_block"]

    print("\n" + "=" * 80)
    print(f"ETHERSCAN V2 API SCAN: {name.upper()} (CHAIN ID {chain_id})")
    print("=" * 80)
    print(f"Vortex Contract      : {vortex_addr}")
    print(f"Controller Contract  : {controller_addr}")
    print(f"Start Creation Block : {from_block}")

    w3 = Web3(Web3.HTTPProvider(rpc_url))

    # Existing tokens in DB
    cursor = db.cursor()
    cursor.execute("SELECT token_address FROM token_registry WHERE chain_id = ?", (chain_id,))
    db_tokens = {row[0].lower() for row in cursor.fetchall()}
    print(f"[+] Existing tokens in token_registry for {name}: {len(db_tokens)}")

    found_tokens = {}

    # 1. Fetch Vortex PriceUpdated logs (topic1 = token)
    print(f"[*] Fetching Vortex PriceUpdated logs...")
    vortex_price_logs = fetch_logs_etherscan_v2(chain_id, vortex_addr, VORTEX_PRICE_UPDATED_TOPIC0, from_block, w3=w3)
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

    # 2. Fetch Vortex TokenTraded logs (topic2 = token)
    print(f"[*] Fetching Vortex TokenTraded logs...")
    vortex_traded_logs = fetch_logs_etherscan_v2(chain_id, vortex_addr, VORTEX_TOKEN_TRADED_TOPIC0, from_block, w3=w3)
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

    # 3. Fetch Controller TokensTraded logs (topic2 = sourceToken, topic3 = targetToken)
    print(f"[*] Fetching Controller TokensTraded logs...")
    ctrl_traded_logs = fetch_logs_etherscan_v2(chain_id, controller_addr, CONTROLLER_TOKENS_TRADED_TOPIC0, from_block, w3=w3)
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

    print(f"\n[+] Total unique tokens found on-chain for {name}: {len(all_scanned_addrs)}")
    print(f"[+] NEW tokens to insert for {name}: {len(missing_addrs)}")

    if not missing_addrs:
        print(f"[+] No new tokens found for {name}. token_registry is already complete.")
        return 0

    inserted_count = 0
    print(f"\n[*] Fetching metadata & inserting {len(missing_addrs)} new tokens into token_registry...")

    for idx, raw_addr in enumerate(sorted(list(missing_addrs)), 1):
        checksum_addr = Web3.to_checksum_address(raw_addr)
        meta = fetch_token_metadata_web3(w3, checksum_addr)
        meta_cache[raw_addr] = meta

        blocks = found_tokens.get(raw_addr, [])
        first_seen = min(blocks) if blocks else 0
        last_seen = max(blocks) if blocks else 0
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
    for chain_key, cfg in CHAINS.items():
        total_added += process_chain(chain_key, cfg, db, meta_cache)

    db.close()

    with open(METADATA_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(meta_cache, f, indent=2)

    print("\n" + "=" * 80)
    print(f"SUMMARY: Total {total_added} new tokens added to token_registry across Sei & Celo.")
    print("=" * 80)

if __name__ == "__main__":
    main()
