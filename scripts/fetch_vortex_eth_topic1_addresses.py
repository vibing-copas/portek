#!/usr/bin/env python3
import os
import sys
import json
import time
import requests
import dotenv
from web3 import Web3

# Load environment variables
dotenv.load_dotenv()

ETHERSCAN_API = os.getenv("ETHERSCAN_API", "RI1364SKZMWSMCE2KD1NCHM7A354W6MSDS")
ETH_RPC_URL = os.getenv("ETH_RPC_URL", "https://rpc.ankr.com/eth")

CONTRACT_ADDRESS = Web3.to_checksum_address("0xD053Dcd7037AF7204cecE544Ea9F227824d79801")
TOPIC0 = "0x5a387f90e98064d45229fc077854834539bef69df2b1447346ce29f8761a158f".lower()
CREATION_BLOCK = 20469389

ETHERSCAN_URL = "https://api.etherscan.io/v2/api"

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
    """Fetch event logs via Etherscan V2 API."""
    params = {
        "chainid": 1,
        "module": "logs",
        "action": "getLogs",
        "address": CONTRACT_ADDRESS,
        "fromBlock": from_block,
        "toBlock": to_block,
        "topic0": TOPIC0,
        "apikey": ETHERSCAN_API
    }
    
    print(f"[*] Fetching logs from Etherscan V2 API (Block {from_block} -> {to_block})...")
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
    """Fetch event logs via Web3 RPC fallback in chunks."""
    w3 = Web3(Web3.HTTPProvider(ETH_RPC_URL))
    if not w3.is_connected():
        print(f"[X] Cannot connect to RPC: {ETH_RPC_URL}")
        return []
    
    if to_block_num == "latest":
        to_block_num = w3.eth.block_number

    all_logs = []
    curr = from_block
    print(f"[*] Fetching logs via RPC in chunks of {chunk_size} from block {curr} to {to_block_num}...")
    
    while curr <= to_block_num:
        end = min(curr + chunk_size - 1, to_block_num)
        print(f"    - Chunk {curr} -> {end}...")
        try:
            logs = w3.eth.get_logs({
                "address": CONTRACT_ADDRESS,
                "fromBlock": curr,
                "toBlock": end,
                "topics": [TOPIC0]
            })
            for l in logs:
                # Convert AttributeDict to standard dict
                log_dict = json.loads(Web3.to_json(l))
                all_logs.append(log_dict)
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
    print("VORTEX ETHEREUM - LOG EVENT TOPIC1 ADDRESS EXTRACTOR")
    print("=" * 80)
    print(f"Contract Address : {CONTRACT_ADDRESS}")
    print(f"Topic0 Filter    : {TOPIC0}")
    print(f"Start Block      : {CREATION_BLOCK} (Contract Creation)")
    print("-" * 80)

    # 1. Attempt fetching via Etherscan
    logs = fetch_logs_etherscan(CREATION_BLOCK, "latest")
    
    # 2. If Etherscan failed or truncated, use Web3 RPC
    if logs is None:
        w3 = Web3(Web3.HTTPProvider(ETH_RPC_URL))
        latest_blk = w3.eth.block_number if w3.is_connected() else "latest"
        logs = fetch_logs_rpc(CREATION_BLOCK, latest_blk)

    print(f"\n[+] Total raw log events retrieved: {len(logs)}")

    # 3. Extract unique addresses from topic1
    address_counts = {}
    topic1_addresses = set()
    
    for log in logs:
        topics = log.get("topics", [])
        if len(topics) > 1 and topics[1]:
            addr = decode_topic_address(topics[1])
            if addr and len(addr) == 42:
                topic1_addresses.add(addr)
                address_counts[addr] = address_counts.get(addr, 0) + 1

    sorted_addresses = sorted(list(topic1_addresses))
    
    print(f"[+] Total unique topic1 addresses: {len(sorted_addresses)}\n")

    # 4. Save results
    logs_file = os.path.join("data", "vortex_eth_topic1_logs.json")
    addresses_json = os.path.join("data", "vortex_eth_topic1_addresses.json")
    addresses_txt = os.path.join("data", "vortex_eth_topic1_addresses.txt")

    with open(logs_file, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2)

    output_data = {
        "contract": CONTRACT_ADDRESS,
        "topic0": TOPIC0,
        "start_block": CREATION_BLOCK,
        "total_logs": len(logs),
        "total_unique_topic1_addresses": len(sorted_addresses),
        "unique_addresses": sorted_addresses,
        "address_occurrences": address_counts
    }

    with open(addresses_json, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    with open(addresses_txt, "w", encoding="utf-8") as f:
        for addr in sorted_addresses:
            f.write(f"{addr}\n")

    print(f"[✔] Raw logs saved to           : {logs_file}")
    print(f"[✔] Structured data saved to    : {addresses_json}")
    print(f"[✔] Address list saved to       : {addresses_txt}")
    
    print("\n" + "=" * 80)
    print("LIST OF UNIQUE TOPIC1 ADDRESSES:")
    print("=" * 80)
    if sorted_addresses:
        for idx, addr in enumerate(sorted_addresses, 1):
            count = address_counts[addr]
            print(f"{idx:3d}. {addr}  ({count} event{'s' if count > 1 else ''})")
    else:
        print("No topic1 addresses found for the given topic0.")
    print("=" * 80)

if __name__ == "__main__":
    main()
