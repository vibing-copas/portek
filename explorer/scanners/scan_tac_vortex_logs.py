#!/usr/bin/env python3
import os
import sys
import json
import sqlite3
import time
import requests
import dotenv
from web3 import Web3
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from carbon_tracker.storage.db import connect as db_connect, upsert_token

dotenv.load_dotenv(ROOT / ".env")

DB_PATH = os.getenv("DB_PATH", str(ROOT / "data" / "tracker.db"))
METADATA_CACHE_FILE = ROOT / "data" / "token_metadata.json"
TAC_BLOCKSCOUT_URL = "https://tac.blockscout.com/api"

# Topic0 filters
VORTEX_PRICE_UPDATED_TOPIC0 = "0x5a387f90e98064d45229fc077854834539bef69df2b1447346ce29f8761a158f".lower()
VORTEX_TOKEN_TRADED_TOPIC0  = "0x16ddee9b3f1b2e6f797172fe2cd10a214e749294074e075e451f95aecd0b958c".lower()
CONTROLLER_TOKENS_TRADED_TOPIC0 = "0x95f3b01351225fea0e69a46f68b164c9dea10284f12cd4a907ce66510ab7af6a".lower()

TAC_CFG = {
    "chain_id": 239,
    "name": "TAC Network",
    "rpc": os.getenv("TAC_RPC_URL") or "https://rpc.tac.build",
    "vortex": "0xf7c7d7507041977aB0328CAf449f1e80085709a9",
    "controller": "0xA4682A2A5Fe02feFF8Bd200240A41AD0E6EaF8d5",
    "from_block": 3814052
}

def create_session():
    session = requests.Session()
    retry = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504, 429])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

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

def parse_hex_int(val):
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        if val.startswith("0x"):
            return int(val, 16)
        try:
            return int(val)
        except ValueError:
            return 0
    return 0

def fetch_blockscout_all_logs(session, contract_addr, from_block=3814052):
    """Fetch all event logs for a contract via Blockscout API in page chunks."""
    all_logs = []
    page = 1
    offset = 1000
    while True:
        url = f"{TAC_BLOCKSCOUT_URL}?module=logs&action=getLogs&address={contract_addr}&fromBlock={from_block}&toBlock=latest&page={page}&offset={offset}"
        try:
            r = session.get(url, timeout=20).json()
            items = r.get("result", [])
            if not items or not isinstance(items, list):
                break
            all_logs.extend(items)
            print(f"  [+] {contract_addr[:10]}... page {page}: fetched {len(items)} logs (total so far: {len(all_logs)})...")
            if len(items) < offset:
                break
            page += 1
            time.sleep(0.05)
        except Exception as e:
            print(f"  [!] Error fetching Blockscout logs page {page}: {e}")
            break
    return all_logs

def fetch_token_metadata(w3, token_addr):
    addr_lower = token_addr.lower()

    if addr_lower in ["0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", "0x0000000000000000000000000000000000000000"]:
        return {"symbol": "NATIVE", "decimals": 18}

    symbol = None
    decimals = 18

    # 1. symbol() 0x95d89b41
    if w3 and w3.is_connected():
        try:
            addr_checksum = Web3.to_checksum_address(token_addr)
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
            addr_checksum = Web3.to_checksum_address(token_addr)
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

def main():
    print("=" * 80)
    print(f"BLOCKSCOUT LOG SCANNER: TAC NETWORK (CHAIN ID {TAC_CFG['chain_id']})")
    print("=" * 80)
    print(f"Vortex Contract      : {TAC_CFG['vortex']}")
    print(f"Controller Contract  : {TAC_CFG['controller']}")
    print(f"Contract Creation Blk: {TAC_CFG['from_block']}")

    session = create_session()
    w3 = Web3(Web3.HTTPProvider(TAC_CFG["rpc"]))

    # Load existing metadata cache
    meta_cache = {}
    if METADATA_CACHE_FILE.exists():
        with open(METADATA_CACHE_FILE, "r", encoding="utf-8") as f:
            meta_cache = json.load(f)

    db = db_connect(DB_PATH)

    # 1. Fetch Vortex logs
    print(f"\n[*] Fetching Vortex event logs from block {TAC_CFG['from_block']}...")
    vortex_logs = fetch_blockscout_all_logs(session, TAC_CFG['vortex'], TAC_CFG['from_block'])
    print(f"[+] Retrieved total {len(vortex_logs)} Vortex events on TAC.")

    # 2. Fetch Controller logs
    print(f"\n[*] Fetching Controller event logs from block {TAC_CFG['from_block']}...")
    ctrl_logs = fetch_blockscout_all_logs(session, TAC_CFG['controller'], TAC_CFG['from_block'])
    print(f"[+] Retrieved total {len(ctrl_logs)} Controller events on TAC.")

    # Discover unique token addresses & classify events
    found_tokens = {}
    price_logs = []
    traded_logs = []
    ctrl_traded_logs = []

    for l in vortex_logs:
        topics = l.get("topics", [])
        if not topics:
            continue
        t0 = topics[0].lower() if topics[0] else ""
        blk = parse_hex_int(l.get("blockNumber"))

        if t0 == VORTEX_PRICE_UPDATED_TOPIC0:
            price_logs.append(l)
            if len(topics) > 1 and topics[1]:
                t_addr = decode_topic_address(topics[1])
                if t_addr:
                    if t_addr not in found_tokens:
                        found_tokens[t_addr] = {"first_seen": blk, "last_seen": blk, "count": 0}
                    found_tokens[t_addr]["count"] += 1
                    found_tokens[t_addr]["first_seen"] = min(found_tokens[t_addr]["first_seen"], blk)
                    found_tokens[t_addr]["last_seen"] = max(found_tokens[t_addr]["last_seen"], blk)
        elif t0 == VORTEX_TOKEN_TRADED_TOPIC0:
            traded_logs.append(l)
            for topic in topics[1:]:
                if topic:
                    t_addr = decode_topic_address(topic)
                    if t_addr and len(t_addr) == 42:
                        if t_addr not in found_tokens:
                            found_tokens[t_addr] = {"first_seen": blk, "last_seen": blk, "count": 0}
                        found_tokens[t_addr]["count"] += 1
                        found_tokens[t_addr]["first_seen"] = min(found_tokens[t_addr]["first_seen"], blk)
                        found_tokens[t_addr]["last_seen"] = max(found_tokens[t_addr]["last_seen"], blk)

    for l in ctrl_logs:
        topics = l.get("topics", [])
        if not topics:
            continue
        t0 = topics[0].lower() if topics[0] else ""
        blk = parse_hex_int(l.get("blockNumber"))
        if t0 == CONTROLLER_TOKENS_TRADED_TOPIC0:
            ctrl_traded_logs.append(l)

        for topic in topics[1:]:
            if topic:
                t_addr = decode_topic_address(topic)
                if t_addr and len(t_addr) == 42:
                    if t_addr not in found_tokens:
                        found_tokens[t_addr] = {"first_seen": blk, "last_seen": blk, "count": 0}
                    found_tokens[t_addr]["count"] += 1
                    found_tokens[t_addr]["first_seen"] = min(found_tokens[t_addr]["first_seen"], blk)
                    found_tokens[t_addr]["last_seen"] = max(found_tokens[t_addr]["last_seen"], blk)

    print(f"\n[+] Classified logs:")
    print(f"  Vortex PriceUpdated events: {len(price_logs)}")
    print(f"  Vortex TokenTraded events : {len(traded_logs)}")
    print(f"  Controller TokensTraded   : {len(ctrl_traded_logs)}")
    print(f"[+] Discovered {len(found_tokens)} unique tokens on TAC Network since block {TAC_CFG['from_block']}.")

    # Enrich metadata & update DB
    inserted_count = 0
    for t_addr, info in found_tokens.items():
        cache_key = f"{TAC_CFG['chain_id']}:{t_addr.lower()}"
        if cache_key in meta_cache:
            meta = meta_cache[cache_key]
        else:
            print(f"  [~] Fetching metadata for new TAC token: {t_addr}...")
            meta = fetch_token_metadata(w3, t_addr)
            meta_cache[cache_key] = meta
            time.sleep(0.05)

        upsert_token(
            db,
            TAC_CFG['chain_id'],
            t_addr,
            meta,
            {
                "first_seen_block": info["first_seen"],
                "last_seen_block": info["last_seen"],
                "events": info["count"]
            }
        )
        inserted_count += 1

    db.commit()

    # Save metadata cache
    with open(METADATA_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(meta_cache, f, indent=2)

    # Save raw logs
    raw_logs_file = ROOT / "data" / "vortex_tac_logs.json"
    with open(raw_logs_file, "w", encoding="utf-8") as f:
        json.dump({
            "chain_id": TAC_CFG['chain_id'],
            "vortex_price_logs": price_logs,
            "vortex_traded_logs": traded_logs,
            "controller_logs": ctrl_traded_logs
        }, f, indent=2)

    # Calculate trade totals per token
    totals_by_token = {}
    for l in price_logs + traded_logs + ctrl_traded_logs:
        blk = parse_hex_int(l.get("blockNumber"))
        tx_hash = l.get("transactionHash", "")
        ts = parse_hex_int(l.get("timeStamp", 0))
        topics = l.get("topics", [])
        
        for topic in topics[1:]:
            if topic:
                t_addr = decode_topic_address(topic)
                if t_addr and len(t_addr) == 42:
                    t_lower = t_addr.lower()
                    if t_lower not in totals_by_token:
                        totals_by_token[t_lower] = {
                            "token_address": t_addr,
                            "chain_id": TAC_CFG['chain_id'],
                            "events_count": 0,
                            "first_block": blk,
                            "last_block": blk,
                            "last_tx_hash": tx_hash,
                            "last_timestamp": ts
                        }
                    totals_by_token[t_lower]["events_count"] += 1
                    totals_by_token[t_lower]["first_block"] = min(totals_by_token[t_lower]["first_block"], blk)
                    totals_by_token[t_lower]["last_block"] = max(totals_by_token[t_lower]["last_block"], blk)

    totals_file = ROOT / "data" / "vortex_tac_trade_totals.json"
    with open(totals_file, "w", encoding="utf-8") as f:
        json.dump(list(totals_by_token.values()), f, indent=2)

    db.close()
    print(f"\n[+] SUCCESS! Scanned {len(price_logs) + len(traded_logs) + len(ctrl_traded_logs)} events.")
    print(f"[+] Total {inserted_count} TAC tokens saved to token_registry and {totals_file}!")

if __name__ == "__main__":
    main()
