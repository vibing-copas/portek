#!/usr/bin/env python3
import os
import requests
import dotenv

dotenv.load_dotenv()
API_KEY = os.getenv("ETHERSCAN_API", "RI1364SKZMWSMCE2KD1NCHM7A354W6MSDS")

VORTEX_ADDRESS = "0xD9D89e8A0dfE549e5B424D5b511cB3b84A764857"
CONTROLLER_ADDRESS = "0x6619871118D144c1c28eC3b23036FC1f0829ed3a"
PRICE_UPDATED_TOPIC0 = "0x5a387f90e98064d45229fc077854834539bef69df2b1447346ce29f8761a158f"
TOKENS_TRADED_TOPIC0 = "0x95f3b01351225fea0e69a46f68b164c9dea10284f12cd4a907ce66510ab7af6a"

def main():
    print("=" * 80)
    print("TESTING ETHERSCAN V2 API FOR CELO (CHAINID 42220)")
    print("=" * 80)
    print(f"API Key: {API_KEY}\n")

    url = "https://api.etherscan.io/v2/api"

    # Test 1: Vortex PriceUpdated
    params_vortex = {
        "chainid": 42220,
        "module": "logs",
        "action": "getLogs",
        "address": VORTEX_ADDRESS,
        "fromBlock": 66870000,
        "toBlock": "latest",
        "topic0": PRICE_UPDATED_TOPIC0,
        "apikey": API_KEY
    }
    
    print("[1] Testing Vortex PriceUpdated (chainid=42220)...")
    res1 = requests.get(url, params=params_vortex, timeout=15).json()
    print("    Response:", res1)

    # Test 2: Controller TokensTraded
    params_ctrl = {
        "chainid": 42220,
        "module": "logs",
        "action": "getLogs",
        "address": CONTROLLER_ADDRESS,
        "fromBlock": 66870000,
        "toBlock": "latest",
        "topic0": TOKENS_TRADED_TOPIC0,
        "apikey": API_KEY
    }

    print("\n[2] Testing Controller TokensTraded (chainid=42220)...")
    res2 = requests.get(url, params=params_ctrl, timeout=15).json()
    print("    Response:", res2)

    # Test 3: Celoscan API Key test
    celo_url = "https://api.celoscan.io/api"
    params_celoscan = {
        "module": "logs",
        "action": "getLogs",
        "address": VORTEX_ADDRESS,
        "fromBlock": 66870000,
        "toBlock": "latest",
        "topic0": PRICE_UPDATED_TOPIC0,
        "apikey": API_KEY
    }
    print("\n[3] Testing Direct Celoscan (api.celoscan.io)...")
    res3 = requests.get(celo_url, params=params_celoscan, timeout=15).json()
    print("    Response:", res3)

if __name__ == "__main__":
    main()
