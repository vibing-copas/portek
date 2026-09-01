#!/usr/bin/env python3
import os
import sys
import json
import sqlite3
import time
import requests
import dotenv
from web3 import Web3

dotenv.load_dotenv()

ETHERSCAN_API = os.getenv("ETHERSCAN_API", "RI1364SKZMWSMCE2KD1NCHM7A354W6MSDS")
ETH_RPC_URL = os.getenv("ETH_RPC_URL", "https://rpc.ankr.com/eth")
DB_PATH = os.getenv("DB_PATH", "data/tracker.db")

ETHERSCAN_URL = "https://api.etherscan.io/v2/api"

def get_contract_creation_block(contract_addr: str) -> int:
    """Fetch exact contract creation block via Etherscan API with fallback."""
    params = {
        "chainid": 1,
        "module": "contract",
        "action": "getcontractcreation",
        "contractaddresses": contract_addr,
        "apikey": ETHERSCAN_API
    }
    try:
        res = requests.get(ETHERSCAN_URL, params=params, timeout=10).json()
        if res.get("status") == "1" and res.get("result"):
            tx_hash = res["result"][0].get("txHash")
            if tx_hash:
                tx_params = {
                    "chainid": 1,
                    "module": "proxy",
                    "action": "eth_getTransactionByHash",
                    "txhash": tx_hash,
                    "apikey": ETHERSCAN_API
                }
                tx_res = requests.get(ETHERSCAN_URL, params=tx_params, timeout=10).json()
                block_hex = tx_res.get("result", {}).get("blockNumber")
                if block_hex:
                    return int(block_hex, 16)
    except Exception:
        pass
    return 17066607  # Known deployment block of Ethereum CarbonController

CONTROLLER_ADDRESS = Web3.to_checksum_address("0xC537e898CD774e2dCBa3B14Ea6f34C93d5eA45e1")
TOPIC0 = "0x95f3b01351225fea0e69a46f68b164c9dea10284f12cd4a907ce66510ab7af6a".lower()

START_BLOCK = get_contract_creation_block(CONTROLLER_ADDRESS)

def decode_topic_address(topic_hex: str) -> str:
    """Extract and checksum 20-byte EVM address from 32-byte topic hex."""
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

def fetch_logs_etherscan(from_block, to_block="latest"):
    params = {
        "chainid": 1,
        "module": "logs",
        "action": "getLogs",
        "address": CONTROLLER_ADDRESS,
        "fromBlock": from_block,
        "toBlock": to_block,
        "topic0": TOPIC0,
        "apikey": ETHERSCAN_API
    }
    
    print(f"[*] Fetching controller logs from Etherscan V2 API (Block {from_block} -> {to_block})...")
    res = requests.get(ETHERSCAN_URL, params=params, timeout=30)
    res.raise_for_status()
    data = res.json()
    
    status = data.get("status")
    message = data.get("message")
    
    if status == "1" and isinstance(data.get("result"), list):
        return data["result"]
    elif message == "No records found":
        return []
    else:
        print(f"[!] Etherscan returned status '{status}' / message '{message}'. Falling back to Web3 RPC...")
        return None

def fetch_logs_rpc(from_block, to_block_num, chunk_size=100000):
    w3 = Web3(Web3.HTTPProvider(ETH_RPC_URL))
    if not w3.is_connected():
        print(f"[X] Cannot connect to RPC: {ETH_RPC_URL}")
        return []
    
    if to_block_num == "latest":
        to_block_num = w3.eth.block_number

    all_logs = []
    curr = from_block
    print(f"[*] Fetching controller logs via RPC from block {curr} to {to_block_num}...")
    
    while curr <= to_block_num:
        end = min(curr + chunk_size - 1, to_block_num)
        try:
            logs = w3.eth.get_logs({
                "address": CONTROLLER_ADDRESS,
                "fromBlock": curr,
                "toBlock": end,
                "topics": [TOPIC0]
            })
            for l in logs:
                all_logs.append(json.loads(Web3.to_json(l)))
            curr = end + 1
            time.sleep(0.2)
        except Exception as e:
            print(f"    [!] Error fetching chunk {curr}-{end}: {e}. Retrying smaller chunk...")
            if chunk_size > 10000:
                return fetch_logs_rpc(curr, to_block_num, chunk_size=chunk_size // 2)
            else:
                curr = end + 1
                
    return all_logs

def main():
    os.makedirs("data", exist_ok=True)
    
    print("=" * 80)
    print("ETHEREUM CONTROLLER - LOG EVENT TOPIC3 ADDRESS EXTRACTOR & COMPARISON")
    print("=" * 80)
    print(f"Contract Address : {CONTROLLER_ADDRESS} (CarbonController)")
    print(f"Topic0 Filter    : {TOPIC0}")
    print(f"Start Block      : {START_BLOCK}")
    print("-" * 80)

    # 1. Fetch logs
    logs = fetch_logs_etherscan(START_BLOCK, "latest")
    if logs is None:
        w3 = Web3(Web3.HTTPProvider(ETH_RPC_URL))
        latest_blk = w3.eth.block_number if w3.is_connected() else "latest"
        logs = fetch_logs_rpc(START_BLOCK, latest_blk)

    print(f"\n[+] Total raw log events retrieved: {len(logs)}")

    # 2. Extract unique addresses from topic3
    topic3_addresses = set()
    address_counts = {}

    for log in logs:
        topics = log.get("topics", [])
        if len(topics) > 3 and topics[3]:
            addr = decode_topic_address(topics[3])
            if addr and len(addr) == 42:
                topic3_addresses.add(addr)
                address_counts[addr] = address_counts.get(addr, 0) + 1

    sorted_topic3 = sorted(list(topic3_addresses))
    print(f"[+] Total unique topic3 addresses extracted: {len(sorted_topic3)}")

    # Save logs and extracted topic3 addresses
    logs_file = os.path.join("data", "controller_eth_topic3_logs.json")
    topic3_json = os.path.join("data", "controller_eth_topic3_addresses.json")
    topic3_txt = os.path.join("data", "controller_eth_topic3_addresses.txt")

    with open(logs_file, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2)

    with open(topic3_json, "w", encoding="utf-8") as f:
        json.dump({
            "contract": CONTROLLER_ADDRESS,
            "topic0": TOPIC0,
            "total_logs": len(logs),
            "total_unique_topic3_addresses": len(sorted_topic3),
            "addresses": sorted_topic3,
            "occurrences": address_counts
        }, f, indent=2)

    with open(topic3_txt, "w", encoding="utf-8") as f:
        for addr in sorted_topic3:
            f.write(f"{addr}\n")

    # 3. Query token_registry from tracker.db
    if not os.path.exists(DB_PATH):
        print(f"[X] Database not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT token_address, symbol FROM token_registry WHERE chain_id = 1")
    db_rows = cursor.fetchall()
    conn.close()

    db_map = {Web3.to_checksum_address(r[0]): (r[1] or "UNKNOWN") for r in db_rows}
    print(f"[+] Total token addresses in token_registry (ETH, chain_id=1): {len(db_map)}")

    # 4. Compare topic3 addresses vs token_registry
    topic3_set = set(sorted_topic3)
    db_set = set(db_map.keys())

    in_both = topic3_set.intersection(db_set)
    only_in_topic3 = topic3_set - db_set
    only_in_db = db_set - topic3_set

    print("\n" + "=" * 80)
    print("📊 COMPARISON SUMMARY (CONTROLLER TOPIC3 VS TOKEN_REGISTRY):")
    print("=" * 80)
    print(f"  • In BOTH topic3 and token_registry : {len(in_both)}")
    print(f"  • ONLY in topic3 (missing from DB)  : {len(only_in_topic3)}")
    print(f"  • ONLY in DB (missing from topic3)  : {len(only_in_db)}")
    print("-" * 80)

    only_in_topic3_details = sorted([
        {"address": a, "events": address_counts.get(a, 0)}
        for a in only_in_topic3
    ], key=lambda x: x["address"])

    only_in_db_details = sorted([
        {"address": a, "symbol": db_map[a]}
        for a in only_in_db
    ], key=lambda x: x["symbol"])

    if only_in_topic3_details:
        print("\n⚠️  ADDRESSES IN TOPIC3 BUT NOT IN TOKEN_REGISTRY:")
        for item in only_in_topic3_details:
            print(f"   - {item['address']} ({item['events']} events)")

    if only_in_db_details:
        print("\nℹ️  ADDRESSES IN TOKEN_REGISTRY BUT NOT IN TOPIC3:")
        for item in only_in_db_details:
            print(f"   - {item['address']} (Symbol: {item['symbol']})")

    # Save comparison report
    comp_report_path = os.path.join("data", "controller_topic3_vs_token_registry_comparison.json")
    report = {
        "controller_address": CONTROLLER_ADDRESS,
        "topic0": TOPIC0,
        "summary": {
            "total_topic3": len(topic3_set),
            "total_db": len(db_set),
            "in_both_count": len(in_both),
            "only_in_topic3_count": len(only_in_topic3),
            "only_in_db_count": len(only_in_db)
        },
        "only_in_topic3": only_in_topic3_details,
        "only_in_db": only_in_db_details
    }

    with open(comp_report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\n[✔] Comparison report saved to: {comp_report_path}")
    print("=" * 80)

if __name__ == "__main__":
    main()
