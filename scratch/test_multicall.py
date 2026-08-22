import os
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()

# We can connect to Celo public RPC
rpc_url = "https://forno.celo.org"
w3 = Web3(Web3.HTTPProvider(rpc_url))

# Multicall3
MULTICALL_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "target", "type": "address"},
                    {"internalType": "bool", "name": "allowFailure", "type": "bool"},
                    {"internalType": "bytes", "name": "callData", "type": "bytes"}
                ],
                "internalType": "struct Multicall3.Call3[]",
                "name": "calls",
                "type": "tuple[]"
            }
        ],
        "name": "aggregate3",
        "outputs": [
            {
                "components": [
                    {"internalType": "bool", "name": "success", "type": "bool"},
                    {"internalType": "bytes", "name": "returnData", "type": "bytes"}
                ],
                "internalType": "struct Multicall3.Result[]",
                "name": "returnData",
                "type": "tuple[]"
            }
        ],
        "stateMutability": "payable",
        "type": "function"
    }
]

ERC20_ABI = [
    {"name":"symbol","outputs":[{"type":"string"}],"inputs":[],"stateMutability":"view","type":"function"},
    {"name":"name","outputs":[{"type":"string"}],"inputs":[],"stateMutability":"view","type":"function"},
    {"name":"decimals","outputs":[{"type":"uint8"}],"inputs":[],"stateMutability":"view","type":"function"},
]

tokens = [
    "0x471EcE3750Da237f93B8E33Ec53639851817e593", # CELO
    "0x765DE816845861e75A25fCA122bb6898B8B1282a", # cUSD
]

multicall = w3.eth.contract(address=Web3.to_checksum_address("0xcA11bde05977b3631167028862bE2a173976CA11"), abi=MULTICALL_ABI)

calls = []
for token in tokens:
    c = w3.eth.contract(address=Web3.to_checksum_address(token), abi=ERC20_ABI)
    
    # Use encode_abi on the contract instance and convert to bytes
    sym_calldata = w3.to_bytes(hexstr=c.encode_abi("symbol"))
    dec_calldata = w3.to_bytes(hexstr=c.encode_abi("decimals"))
    
    calls.append({
        "target": c.address,
        "allowFailure": True,
        "callData": sym_calldata
    })
    calls.append({
        "target": c.address,
        "allowFailure": True,
        "callData": dec_calldata
    })

print(f"Sending {len(calls)} calls in multicall...")
results = multicall.functions.aggregate3(calls).call()

# Parse
for i, token in enumerate(tokens):
    sym_success, sym_data = results[i*2]
    dec_success, dec_data = results[i*2 + 1]
    
    symbol = w3.codec.decode(["string"], sym_data)[0] if sym_success else "FAIL"
    decimals = w3.codec.decode(["uint8"], dec_data)[0] if dec_success else 0
    
    print(f"Token: {token} | Symbol: {symbol} | Decimals: {decimals}")
