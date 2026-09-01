#!/usr/bin/env python3
import os
import time
import json
import requests
import dotenv
from web3 import Web3

dotenv.load_dotenv()
CELO_RPC = os.getenv("CELO_RPC_URL") or "https://rpc.ankr.com/celo/a0834bb80047cb660d1506390713260441065f52f48dd8dc410b1af99a86bf1d"

def test_celo_fast():
    w3 = Web3(Web3.HTTPProvider(CELO_RPC))
    if not w3.is_connected():
        print("Cannot connect to Celo RPC")
        return

    latest = w3.eth.block_number
    start = 30349600  # Celo Vortex contract deployment block
    chunk = 100000

    print(f"[*] Scanning Celo from creation block {start} to latest {latest} (Chunk: {chunk})...")
    curr = start
    total_logs = 0
    t0 = time.time()

    vortex_addr = Web3.to_checksum_address("0xD9D89e8A0dfE549e5B424D5b511cB3b84A764857")
    topic0 = "0x5a387f90e98064d45229fc077854834539bef69df2b1447346ce29f8761a158f"

    while curr <= latest:
        end = min(curr + chunk - 1, latest)
        try:
            logs = w3.eth.get_logs({
                "address": vortex_addr,
                "fromBlock": curr,
                "toBlock": end,
                "topics": [topic0]
            })
            total_logs += len(logs)
        except Exception as e:
            print(f"Error chunk {curr}-{end}: {e}")
        curr = end + 1

    t1 = time.time()
    print(f"[✔] Completed in {t1 - t0:.2f}s! Found {total_logs} PriceUpdated logs on Celo.")

if __name__ == "__main__":
    test_celo_fast()
