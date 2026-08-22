import json
from pathlib import Path
from web3 import Web3

ROOT = Path(__file__).resolve().parents[2]

def load_abi(name):
    return json.loads((ROOT / "abis" / name).read_text())

def connect(rpc_url):
    if rpc_url.startswith("ws://") or rpc_url.startswith("wss://"):
        w3 = Web3(Web3.LegacyWebSocketProvider(rpc_url))
    else:
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={
            "timeout": 30
        }))
    try:
        w3.eth.block_number
    except Exception as e:
        raise ConnectionError(f"RPC connection failed: {e}")
    return w3

def contract(w3, address, abi_name):
    return w3.eth.contract(address=Web3.to_checksum_address(address), abi=load_abi(abi_name))
