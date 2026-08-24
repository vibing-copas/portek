import asyncio
import sqlite3
import os
import aiohttp
from pathlib import Path
from dotenv import load_dotenv
from collections import defaultdict

import sys
sys.stdout.reconfigure(encoding='utf-8')

# DexScreener chain slugs mapping from carbon_tracker/market/dexscreener.py
CHAINS = {
    1: "ethereum",
    1329: "sei",
    239: "tac",
    42220: "celo",
    2632500: "coti"
}

# Wrapped native tokens mapping
NATIVE_WRAPPED_MAP = {
    1: "0xC02aaA39b223FE8D0A0e5C4F27ead9083C756Cc2",       # WETH on Ethereum
    1329: "0xE30feDd158A2e3b13e9badaeABaFc5516e95e8C7",    # WSEI on Sei
    239: "0xb63b9f0eb4a6e6f191529d71d4d88cc8900df2c9",     # WTAC on TAC
    42220: "0x471EcE3750Da237f93B8E339c536989b8978a438",   # CELO on Celo
}

async def fetch_dexscreener_batch(session, chain_slug, addresses, base_url="https://api.dexscreener.com"):
    """Fetch prices for a batch of addresses from DexScreener asynchronously."""
    url = f"{base_url}/tokens/v1/{chain_slug}/" + ",".join(addresses)
    try:
        async with session.get(url, timeout=30) as response:
            if response.status == 200:
                data = await response.json()
                return chain_slug, data
            else:
                print(f"[Error] HTTP {response.status} for {chain_slug} batch.")
                return chain_slug, []
    except Exception as e:
        print(f"[Exception] Error fetching batch for {chain_slug}: {e}")
        return chain_slug, []

async def get_all_prices_async():
    # Load environment variables
    ROOT = Path(__file__).resolve().parents[1]
    load_dotenv(ROOT / ".env", override=True)
    db_path = os.getenv("DB_PATH", "data/tracker.db")
    
    # Connect to database and fetch tokens
    conn = sqlite3.connect(ROOT / db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT chain_id, token_address, symbol FROM token_registry")
    tokens = cursor.fetchall()
    conn.close()
    
    print(f"Loaded {len(tokens)} tokens from token_registry.\n")
    
    # Group tokens by chain
    chain_tokens = defaultdict(list)
    token_symbols = {} # Map address to symbol for reporting
    
    for chain_id, addr, symbol in tokens:
        chain_tokens[chain_id].append(addr)
        token_symbols[(chain_id, addr.lower())] = symbol

    # Build tasks
    tasks = []
    batch_size = 30
    
    # We will use a single aiohttp ClientSession
    async with aiohttp.ClientSession() as session:
        for chain_id, addresses in chain_tokens.items():
            chain_slug = CHAINS.get(chain_id)
            if not chain_slug:
                print(f"Skipping chain {chain_id} (no slug mapped).")
                continue
                
            wrapped_addr = NATIVE_WRAPPED_MAP.get(chain_id)
            
            # Map native placeholders to wrapped equivalents for DexScreener querying
            mapped_addresses = []
            for addr in addresses:
                if addr.lower() == "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee":
                    if wrapped_addr:
                        mapped_addresses.append(wrapped_addr)
                    else:
                        mapped_addresses.append(addr)
                else:
                    mapped_addresses.append(addr)
            
            # Split into batches of 30
            for i in range(0, len(mapped_addresses), batch_size):
                batch = mapped_addresses[i:i+batch_size]
                tasks.append(fetch_dexscreener_batch(session, chain_slug, batch))
                
        print(f"Dispatched {len(tasks)} concurrent async requests to DexScreener.")
        
        # Await all tasks concurrently
        results = await asyncio.gather(*tasks)
        
        # Process results
        prices_by_chain = defaultdict(dict)
        for chain_slug, pairs in results:
            # Reconstruct chain_id from slug
            chain_id = next((k for k, v in CHAINS.items() if v == chain_slug), None)
            if not chain_id:
                continue
                
            groups = defaultdict(list)
            for pair in pairs or []:
                price = pair.get("priceUsd")
                if price is None:
                    continue
                liq = float((pair.get("liquidity") or {}).get("usd") or 0)
                base_addr = pair.get("baseToken", {}).get("address", "").lower()
                groups[base_addr].append((liq, float(price), pair))
                
            # Pick highest liquidity pool for each base address
            for addr, rows in groups.items():
                liq, price, raw = max(rows, key=lambda x: x[0])
                prices_by_chain[chain_id][addr] = {
                    "price_usd": price,
                    "liquidity_usd": liq,
                    "dex": raw.get("dexId"),
                    "pair": raw.get("pairAddress")
                }
                
        # Print results nicely
        print("\n" + "="*80)
        print(f"{'Chain':<10} | {'Symbol':<10} | {'Address':<44} | {'Price (USD)':<15}")
        print("="*80)
        
        total_fetched = 0
        for chain_id, addresses in chain_tokens.items():
            chain_slug = CHAINS.get(chain_id)
            wrapped_addr = NATIVE_WRAPPED_MAP.get(chain_id, "").lower()
            
            for addr in addresses:
                addr_lower = addr.lower()
                query_addr = addr_lower
                
                # Check for mapped native token
                if addr_lower == "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee" and wrapped_addr:
                    query_addr = wrapped_addr
                    
                symbol = token_symbols.get((chain_id, addr_lower), "Unknown")
                price_data = prices_by_chain[chain_id].get(query_addr)
                
                if price_data:
                    price_str = f"${price_data['price_usd']:.6f}"
                    total_fetched += 1
                else:
                    price_str = "Not Found / No Liq"
                    
                # Shorten address for display
                display_addr = addr if len(addr) <= 42 else addr[:42]
                print(f"{chain_slug:<10} | {symbol:<10} | {display_addr:<44} | {price_str:<15}")
                
        print("="*80)
        print(f"Successfully retrieved prices for {total_fetched}/{len(tokens)} tokens.")

if __name__ == "__main__":
    asyncio.run(get_all_prices_async())
