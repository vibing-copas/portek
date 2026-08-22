from web3 import Web3
from ..constants import NATIVE_ETH

ABI = [
 {"name":"symbol","outputs":[{"type":"string"}],"inputs":[],"stateMutability":"view","type":"function"},
 {"name":"name","outputs":[{"type":"string"}],"inputs":[],"stateMutability":"view","type":"function"},
 {"name":"decimals","outputs":[{"type":"uint8"}],"inputs":[],"stateMutability":"view","type":"function"},
]

def metadata(w3, address):
    address = Web3.to_checksum_address(address)
    if address.lower() == NATIVE_ETH.lower():
        return {"address": address, "symbol": "ETH", "name": "Ether", "decimals": 18, "native": True}
    c = w3.eth.contract(address=address, abi=ABI)
    out = {"address": address, "symbol": address[:10], "name": address, "decimals": 18, "native": False}
    for fn, key in [(c.functions.symbol, "symbol"),(c.functions.name, "name"),(c.functions.decimals, "decimals")]:
        try: out[key] = fn().call()
        except Exception: pass
    return out
