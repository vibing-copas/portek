import asyncio
import sys
import os
import socket
import requests
import json
import sqlite3
from pathlib import Path
from dotenv import load_dotenv
import aiohttp

# Force UTF-8 stdout output for Windows CLI
sys.stdout.reconfigure(encoding='utf-8')

# 1. DNS-OVER-HTTPS (DoH) BYPASS FOR BYBIT ID
DNS_CACHE = {}
DOMAINS_TO_PATCH = ["api.bybit.id"]

def resolve_dns_over_https(domain):
    url = f"https://cloudflare-dns.com/dns-query?name={domain}&type=A"
    headers = {"accept": "application/dns-json"}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            ips = [answer["data"] for answer in response.json().get("Answer", []) if answer["type"] == 1]
            if ips:
                return ips[0]
    except Exception:
        pass
    return None

print("--- Initializing DNS Bypass ---")
for domain in DOMAINS_TO_PATCH:
    ip = resolve_dns_over_https(domain)
    if ip:
        DNS_CACHE[domain] = ip
        print(f"Resolved: {domain} -> {ip}")

# Apply socket patch
original_getaddrinfo = socket.getaddrinfo
def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host in DNS_CACHE:
        return original_getaddrinfo(DNS_CACHE[host], port, family, type, proto, flags)
    return original_getaddrinfo(host, port, family, type, proto, flags)
socket.getaddrinfo = patched_getaddrinfo
print("DNS Bypass active.\n")


# 2. SYMBOL CLEANING & MAPPING FOR BYBIT SPOT MARKET
def clean_token_symbol(symbol):
    if not symbol:
        return ""
    s = symbol.upper().strip()
    # Replace special Unicode characters
    s = s.replace("USD₮", "USDT")
    s = s.replace("₮", "T")
    
    # Strip common wraps/suffixes
    for suffix in [".E", ".N", "0", "1", "2", "3", "4", "5"]:
        if s.endswith(suffix):
            s = s[:-len(suffix)]
            
    # Normalize native assets and their wrapped versions
    if s in ["WETH", "WETH9"]:
        s = "ETH"
    elif s in ["WSEI"]:
        s = "SEI"
    elif s in ["WTAC"]:
        s = "TAC"
    elif s in ["WBTC", "CBBTC", "LBTC"]:
        s = "BTC"
        
    return s

async def fetch_bybit_ticker(session, token_symbol, base_url="https://api.bybit.id"):
    """Fetch spot ticker for a token symbol from Bybit API asynchronously."""
    # USDT itself is pegged to 1.0 USD
    if token_symbol == "USDT":
        return token_symbol, 1.0
        
    symbol = f"{token_symbol}USDT"
    url = f"{base_url}/v5/market/tickers?category=spot&symbol={symbol}"
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    try:
        async with session.get(url, headers=headers, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("retCode") == 0:
                    ticker_list = data.get("result", {}).get("list", [])
                    if ticker_list:
                        last_price = ticker_list[0].get("lastPrice")
                        if last_price:
                            return token_symbol, float(last_price)
            return token_symbol, None
    except Exception:
        return token_symbol, None

async def main():
    # Load env
    ROOT = Path(__file__).resolve().parents[1]
    load_dotenv(ROOT / ".env", override=True)
    db_path = os.getenv("DB_PATH", "data/tracker.db")
    
    # Get all tokens from database
    conn = sqlite3.connect(ROOT / db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT chain_id, token_address, symbol FROM token_registry")
    tokens = cursor.fetchall()
    conn.close()
    
    print(f"Loaded {len(tokens)} tokens from token_registry.")
    
    # Extract unique symbols and their clean counterparts
    from collections import defaultdict
    unique_symbols = sorted(list(set(t[2] for t in tokens if t[2])))
    cleaned_to_raws = defaultdict(list)
    
    for raw in unique_symbols:
        clean = clean_token_symbol(raw)
        if clean:
            cleaned_to_raws[clean].append(raw)
            
    print(f"Mapped to {len(cleaned_to_raws)} unique Bybit spot symbols to query.\n")
    
    # Run async requests
    print("Dispatching async requests to Bybit...")
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_bybit_ticker(session, clean) for clean in cleaned_to_raws.keys()]
        results = await asyncio.gather(*tasks)
        
    # Map results
    prices_map = {}
    for clean_sym, price in results:
        if price is not None:
            for raw_sym in cleaned_to_raws[clean_sym]:
                prices_map[raw_sym] = price
            
    # Print results table
    print("\n" + "="*80)
    print(f"{'Original Symbol':<18} | {'Bybit Spot Query':<18} | {'Price (USD)':<20}")
    print("="*80)
    
    total_found = 0
    for raw in unique_symbols:
        clean = clean_token_symbol(raw)
        price = prices_map.get(raw)
        
        price_str = f"${price:,.6f}" if price is not None else "Not Found on Bybit"
        if price is not None:
            total_found += 1
            
        print(f"{raw:<18} | {clean + 'USDT':<18} | {price_str:<20}")
        
    print("="*80)
    print(f"Successfully retrieved Bybit prices for {total_found}/{len(unique_symbols)} unique symbols.")

if __name__ == "__main__":
    asyncio.run(main())
