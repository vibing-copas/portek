import os
import json
import time
import sqlite3
import requests
import subprocess
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

# Safe Print helper for Windows Console encoding limits
def safe_str(s):
    if not s: return ""
    return str(s).encode('ascii', errors='replace').decode('ascii')

STABLECOINS_MAP = {
    1: [
        ("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", 6),
        ("0xdAC17F958D2ee523a2206206994597C13D831ec7", 6),
    ],
    1329: [
        ("0xe15fC38F6D8c56aF07bbCBe3BAf5708A2Bf42392", 6),
        ("0x3894085ef7ff0f0aedf52e2a2704928d1ec074f1", 6),
    ],
    239: [
        ("0xAF988C3f7CB2AceAbB15f96b19388a259b6C438f", 6),
    ],
    42220: [
        ("0x765DE816845861e75A25fCA122bb6898B8B1282a", 18),
        ("0xef1ba8c77e1c9e328e100d8546b95ee34174adc1", 6),
    ],
    2632500: [
        ("0xf1Feebc4376c68B7003450ae66343Ae59AB37D3C", 6),
    ]
}

controllers = {
    1: "0xC537e898CD774e2dCBa3B14Ea6f34C93d5eA45e1",
    1329: "0xe4816658ad10bF215053C533cceAe3f59e1f1087",
    239: "0xA4682A2A5Fe02feFF8Bd200240A41AD0E6EaF8d5",
    42220: "0x6619871118D144c1c28eC3b23036FC1f0829ed3a",
    2632500: "0x59f21012B2E9BA67ce6a7605E74F945D0D4C84EA"
}

rpc_envs = {
    1: ("ETH_RPC_URL", "https://rpc.ankr.com/eth"),
    1329: ("SEI_RPC_URL", "https://evm-rpc.sei-apis.com"),
    239: ("TAC_RPC_URL", "https://rpc.tac.build"),
    42220: ("CELO_RPC_URL", "https://forno.celo.org"),
    2632500: ("COTI_RPC_URL", "https://mainnet.coti.io/rpc")
}

chain_names = {1: "Ethereum", 1329: "Sei", 239: "Tac", 42220: "Celo", 2632500: "Coti"}
chain_slugs = {1: "ethereum", 1329: "sei", 239: "tac", 42220: "celo", 2632500: "coti"}

def dexscreener_query(chain_id, addresses, batch_size=30):
    slug = chain_slugs.get(chain_id)
    if not slug: return {}
    
    native_map = {
        1: "0xC02aaA39b223FE8D0A0e5C4F27ead9083C756Cc2",
        1329: "0xE30feDd158A2e3b13e9badaeABaFc5516e95e8C7",
        239: "0xb63b9f0eb4a6e6f191529d71d4d88cc8900df2c9",
        42220: "0x471EcE3750Da237f93B8E339c536989b8978a438",
    }
    wrapped_addr = native_map.get(chain_id, "")
    
    mapped_addresses = []
    for a in addresses:
        if a.lower() == "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee" and wrapped_addr:
            mapped_addresses.append(wrapped_addr)
        else:
            mapped_addresses.append(a)
            
    out = {}
    for i in range(0, len(mapped_addresses), batch_size):
        batch = mapped_addresses[i:i+batch_size]
        url = f"https://api.dexscreener.com/tokens/v1/{slug}/" + ",".join(batch)
        print(f"      [~] Fetching DexScreener: {url}")
        try:
            r = requests.get(url, timeout=10)
            print(f"      [+] DexScreener status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                if data:
                    from collections import defaultdict
                    groups = defaultdict(list)
                    for p in data:
                        price = p.get("priceUsd")
                        if price is None: continue
                        liq = float((p.get("liquidity") or {}).get("usd") or 0)
                        b = p.get("baseToken", {}).get("address", "").lower()
                        groups[b].append((liq, float(price)))
                    for addr, rows in groups.items():
                        liq, price = max(rows, key=lambda x: x[0])
                        out[addr] = price
        except Exception as e:
            print(f"      [-] DexScreener query error for batch: {e}")
            
    if wrapped_addr.lower() in out:
        out["0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"] = out[wrapped_addr.lower()]
        
    return out

def estimate_carbon_prices(chain_id, tokens):
    script_path = str(ROOT / "scripts" / "get_carbon_prices.js")
    env_var, default_rpc = rpc_envs[chain_id]
    rpc_url = os.getenv(env_var, "").strip() or default_rpc
    controller_addr = controllers[chain_id]
    stables = STABLECOINS_MAP.get(chain_id, [])
    targets = [[t["address"], t["symbol"], t["decimals"]] for t in tokens]
    
    print(f"      [~] Executing get_carbon_prices.js for chain {chain_id}...")
    out = {}
    try:
        cmd = ["node", script_path, rpc_url, controller_addr, json.dumps(stables), json.dumps(targets)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=20)
        print("      [+] Bancor Node finished successfully.")
        market_data = json.loads(result.stdout.strip())
        for k, v in market_data.items():
            out[k.lower()] = v["price_usd"]
    except Exception as e:
        print(f"      [-] Bancor Node failed: {e}")
    return out

def get_dia_price(symbol, dia_cache):
    if not symbol: return None
    sym_upper = symbol.upper()
    if sym_upper in dia_cache:
        return dia_cache[sym_upper]
    
    url = f"https://api.diadata.org/v1/quotation/{symbol}"
    print(f"      [~] Fetching DIA quotation for: {safe_str(symbol)}")
    try:
        r = requests.get(url, timeout=5)
        print(f"      [+] DIA status: {r.status_code}")
        if r.status_code == 200:
            price = r.json().get("Price")
            if price is not None:
                dia_cache[sym_upper] = float(price)
                return float(price)
    except Exception as e:
        print(f"      [-] DIA error: {e}")
    dia_cache[sym_upper] = None
    return None

def main():
    # Get tokens from Database
    db_path = ROOT / "data" / "tracker.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT chain_id, MAX(ts) FROM snapshots GROUP BY chain_id")
    latest_snapshots = cursor.fetchall()

    tokens_by_chain = {}
    for chain_id, max_ts in latest_snapshots:
        cursor.execute("""
            SELECT chain_id, token_address, symbol, decimals
            FROM snapshots 
            LEFT JOIN token_registry USING (chain_id, token_address)
            WHERE chain_id = ? AND ts = ?
        """, (chain_id, max_ts))
        
        tokens_list = []
        seen = set()
        for row in cursor.fetchall():
            cid, addr, symbol, decimals = row
            if not symbol:
                cursor.execute("SELECT payload_json FROM snapshots WHERE chain_id = ? AND ts = ? AND token_address = ? LIMIT 1", (cid, max_ts, addr))
                p_row = cursor.fetchone()
                if p_row:
                    try:
                        symbol = json.loads(p_row[0]).get("symbol", "")
                    except: pass
            
            addr_lower = addr.lower()
            if addr_lower not in seen:
                seen.add(addr_lower)
                tokens_list.append({
                    "chain_id": cid,
                    "chain_name": chain_names[cid],
                    "address": addr,
                    "address_lower": addr_lower,
                    "symbol": symbol or "UNKNOWN",
                    "decimals": decimals or 18
                })
        tokens_by_chain[chain_id] = tokens_list
    conn.close()

    # Only check one chain to make it super fast for debugging (e.g. Celo)
    debug_chain = 42220
    print(f"Debugging chain {chain_names[debug_chain]} with {len(tokens_by_chain[debug_chain])} tokens...")
    tokens = tokens_by_chain[debug_chain]

    # Run Case 1
    print("\nRunning Case 1...")
    addrs = [t["address"] for t in tokens]
    dex_prices = dexscreener_query(debug_chain, addrs)
    print("Dex prices count:", len(dex_prices))

    # Run Case 2
    print("\nRunning Case 2...")
    dia_cache = {}
    for t in tokens[:3]: # Only try first 3 tokens
        get_dia_price(t["symbol"], dia_cache)
    print("Finished debugger successfully!")

if __name__ == "__main__":
    main()
