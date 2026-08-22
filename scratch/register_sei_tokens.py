import os
import sys
import sqlite3
from web3 import Web3
from pathlib import Path

# Add project root to path to reuse modules if needed
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from carbon_tracker.storage.db import connect as db_connect, upsert_token

ERC20_ABI = [
    {"name":"symbol","outputs":[{"type":"string"}],"inputs":[],"stateMutability":"view","type":"function"},
    {"name":"decimals","outputs":[{"type":"uint8"}],"inputs":[],"stateMutability":"view","type":"function"},
]

def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
        
    rpc_url = "https://evm-rpc.sei-apis.com"
    print(f"Connecting to Sei RPC: {rpc_url}...")
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    if not w3.is_connected():
        print("Error: Could not connect to Sei RPC.")
        sys.exit(1)
        
    db_path = PROJECT_ROOT / "data" / "tracker.db"
    print(f"Opening database: {db_path}...")
    db = db_connect(str(db_path))
    
    tokens = [
        "0xe30fedd158a2e3b13e9badaeabafc5516e95e8c7",
        "0x0555e30da8f98308edb960aa94c0db47230d2b9c",
        "0x3894085ef7ff0f0aedf52e2a2704928d1ec074f1",
        "0x5f0e07dfee5832faa00c63f2d33a0d79150e8598",
        "0x9151434b16b9763660705744891fa906f660ecc5"
    ]
    
    chain_id = 1329 # Sei chain_id
    
    for t_addr in tokens:
        checksum_addr = Web3.to_checksum_address(t_addr)
        print(f"\nProcessing token: {checksum_addr}...")
        contract = w3.eth.contract(address=checksum_addr, abi=ERC20_ABI)
        
        try:
            symbol = contract.functions.symbol().call()
        except Exception as e:
            print(f"  [-] Failed to fetch symbol, trying alternate: {e}")
            symbol = "UNKNOWN"
            
        try:
            decimals = contract.functions.decimals().call()
        except Exception as e:
            print(f"  [-] Failed to fetch decimals, defaulting to 18: {e}")
            decimals = 18
            
        print(f"  Symbol: {symbol}")
        print(f"  Decimals: {decimals}")
        
        meta = {
            "symbol": symbol,
            "decimals": decimals
        }
        info = {} # empty info since no scanned trade logs exist yet for manually added tokens
        
        try:
            upsert_token(db, chain_id, checksum_addr, meta, info)
            print(f"  [+] Registered in database successfully!")
        except Exception as e:
            print(f"  [-] Failed to register in database: {e}")
            
    db.commit()
    print("\n[+] All tokens processed and database changes committed.")

if __name__ == "__main__":
    main()
