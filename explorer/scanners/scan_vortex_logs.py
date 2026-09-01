#!/usr/bin/env python3
import os
import json
import requests
import dotenv

dotenv.load_dotenv()

ETHERSCAN_API = os.getenv("ETHERSCAN_API")
CONTRACT_ADDRESS = "0xD053Dcd7037AF7204cecE544Ea9F227824d79801"
TOPIC0 = "0x16ddee9b3f1b2e6f797172fe2cd10a214e749294074e075e451f95aecd0b958c"
START_BLOCK = 20469390
TO_BLOCK = "latest"

API_URL = "https://api.etherscan.io/v2/api"

def decode_topic_address(topic_hex: str) -> str:
    """Extract 20-byte EVM address from 32-byte padded topic hex string."""
    if not topic_hex or not isinstance(topic_hex, str):
        return ""
    clean = topic_hex.lower()
    if clean.startswith("0x"):
        clean = clean[2:]
    if len(clean) >= 40:
        return "0x" + clean[-40:]
    return "0x" + clean

def fetch_logs(from_block, to_block):
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
    
    print(f"Fetching logs from block {from_block} to {to_block} via Etherscan V2 API...")
    res = requests.get(API_URL, params=params)
    res.raise_for_status()
    data = res.json()
    
    status = data.get("status")
    message = data.get("message")
    
    if status == "1" and isinstance(data.get("result"), list):
        return data["result"]
    elif message == "No records found":
        return []
    else:
        raise ValueError(f"Etherscan API Error: {message} - {data.get('result')}")

def main():
    os.makedirs("data", exist_ok=True)
    
    all_logs = fetch_logs(START_BLOCK, TO_BLOCK)
    print(f"\nSuccessfully fetched {len(all_logs)} raw log events.")
    
    # Save complete raw logs
    json_path = os.path.join("data", "vortex_eth_logs.json")
    jsonl_path = os.path.join("data", "vortex_eth_logs.jsonl")
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_logs, f, indent=2)
    print(f"Saved full raw logs to {json_path}")
    
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for log in all_logs:
            f.write(json.dumps(log) + "\n")
    print(f"Saved full raw logs to {jsonl_path}")
    
    # Extract unique addresses from topic2
    topic2_addresses = set()
    address_occurrences = {}
    
    for log in all_logs:
        topics = log.get("topics", [])
        if len(topics) > 2 and topics[2]:
            addr = decode_topic_address(topics[2])
            if addr and len(addr) == 42:
                topic2_addresses.add(addr)
                address_occurrences[addr] = address_occurrences.get(addr, 0) + 1

    sorted_unique_addresses = sorted(list(topic2_addresses))
    print(f"\nExtracted {len(sorted_unique_addresses)} unique addresses from topic2.")
    
    # Save unique addresses
    addresses_json_path = os.path.join("data", "vortex_eth_topic2_addresses.json")
    addresses_txt_path = os.path.join("data", "vortex_eth_topic2_addresses.txt")
    
    with open(addresses_json_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_unique": len(sorted_unique_addresses),
            "addresses": sorted_unique_addresses,
            "occurrences": address_occurrences
        }, f, indent=2)
        
    with open(addresses_txt_path, "w", encoding="utf-8") as f:
        for addr in sorted_unique_addresses:
            f.write(f"{addr}\n")
            
    print(f"Saved unique addresses to {addresses_json_path} and {addresses_txt_path}")
    
    print("\n--- Summary ---")
    print(f"Contract: {CONTRACT_ADDRESS}")
    print(f"Topic0: {TOPIC0}")
    print(f"Start Block: {START_BLOCK}")
    print(f"Total Log Events: {len(all_logs)}")
    print(f"Total Unique Topic2 Addresses: {len(sorted_unique_addresses)}")

if __name__ == "__main__":
    main()
