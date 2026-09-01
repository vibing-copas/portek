#!/usr/bin/env python3
import os
import requests
import dotenv

dotenv.load_dotenv()
API_KEY = os.getenv("ETHERSCAN_API", "RI1364SKZMWSMCE2KD1NCHM7A354W6MSDS")

CONTRACTS = {
    "ethereum": {
        "chain_id": 1,
        "vortex": "0xD053Dcd7037AF7204cecE544Ea9F227824d79801"
    },
    "celo": {
        "chain_id": 42220,
        "vortex": "0xD9D89e8A0dfE549e5B424D5b511cB3b84A764857"
    },
    "sei": {
        "chain_id": 1329,
        "vortex": "0x5715203B16F15d7349Cb1E3537365E9664EAf933"
    }
}

def find_creation_blocks():
    print("=" * 80)
    print("FINDING CONTRACT CREATION BLOCKS VIA BLOCK EXPLORER APIS")
    print("=" * 80)

    for chain, info in CONTRACTS.items():
        chain_id = info["chain_id"]
        vortex_addr = info["vortex"]

        url = "https://api.etherscan.io/v2/api"
        params = {
            "chainid": chain_id,
            "module": "contract",
            "action": "getcontractcreation",
            "contractaddresses": vortex_addr,
            "apikey": API_KEY
        }

        try:
            res = requests.get(url, params=params, timeout=10).json()
            if res.get("status") == "1" and res.get("result"):
                item = res["result"][0]
                creator = item.get("contractCreator")
                tx_hash = item.get("txHash")
                
                # Fetch tx info to get exact block number
                tx_url = "https://api.etherscan.io/v2/api"
                tx_params = {
                    "chainid": chain_id,
                    "module": "proxy",
                    "action": "eth_getTransactionByHash",
                    "txhash": tx_hash,
                    "apikey": API_KEY
                }
                tx_res = requests.get(tx_url, params=tx_params, timeout=10).json()
                block_hex = tx_res.get("result", {}).get("blockNumber")
                block_num = int(block_hex, 16) if block_hex else None

                print(f"[+] {chain.upper()} (Chain ID {chain_id}):")
                print(f"    Vortex Address : {vortex_addr}")
                print(f"    Creator        : {creator}")
                print(f"    Tx Hash        : {tx_hash}")
                print(f"    Creation Block : {block_num}")
            else:
                print(f"[-] {chain.upper()} (Chain ID {chain_id}): Etherscan getcontractcreation returned: {res.get('message', res)}")
        except Exception as e:
            print(f"[-] {chain.upper()} Exception: {e}")

if __name__ == "__main__":
    find_creation_blocks()
