#!/usr/bin/env python3
import os
import requests
import dotenv

dotenv.load_dotenv()
API_KEY = os.getenv("ETHERSCAN_API", "RI1364SKZMWSMCE2KD1NCHM7A354W6MSDS")

def test_celo_etherscan():
    url = "https://api.etherscan.io/v2/api"
    params = {
        "chainid": 42220,
        "module": "logs",
        "action": "getLogs",
        "address": "0xD9D89e8A0dfE549e5B424D5b511cB3b84A764857",
        "fromBlock": 66870000,
        "toBlock": "latest",
        "topic0": "0x5a387f90e98064d45229fc077854834539bef69df2b1447346ce29f8761a158f",
        "apikey": API_KEY
    }
    
    print("Testing Etherscan V2 API for Celo (chainid=42220)...")
    res = requests.get(url, params=params, timeout=15).json()
    print("Response:", res)

    print("\nTesting Celoscan direct API (api.celoscan.io)...")
    celo_url = "https://api.celoscan.io/api"
    celo_params = {
        "module": "logs",
        "action": "getLogs",
        "address": "0xD9D89e8A0dfE549e5B424D5b511cB3b84A764857",
        "fromBlock": 66870000,
        "toBlock": "latest",
        "topic0": "0x5a387f90e98064d45229fc077854834539bef69df2b1447346ce29f8761a158f",
        "apikey": API_KEY
    }
    res2 = requests.get(celo_url, params=celo_params, timeout=15).json()
    print("Response 2:", res2)

if __name__ == "__main__":
    test_celo_etherscan()
