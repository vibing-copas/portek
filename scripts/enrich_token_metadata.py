#!/usr/bin/env python3
import os
import sys
import json
import time
import requests
import yaml
import dotenv
from web3 import Web3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from carbon_tracker.storage.db import connect as db_connect, upsert_token

dotenv.load_dotenv()
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
METADATA_CACHE_FILE = os.path.join("data", "token_metadata.json")
DB_PATH = os.getenv("DB_PATH", "data/tracker.db")

def safe_print(msg):
    try:
        print(msg)
    except UnicodeEncodeError:
        safe_msg = msg.encode('ascii', 'ignore').decode('ascii')
        print(safe_msg)

def load_metadata_cache():
    if os.path.exists(METADATA_CACHE_FILE):
        try:
            with open(METADATA_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_metadata_cache(cache):
    with open(METADATA_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)

def decode_bytes32_string(val_bytes):
    try:
        val_str = val_bytes.rstrip(b'\x00').decode('utf-8', errors='ignore').strip()
        return val_str if val_str else None
    except Exception:
        return None

def fetch_erc20_metadata_raw(w3, token_addr):
    addr_lower = token_addr.lower()
    if addr_lower in ["0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", "0x0000000000000000000000000000000000000000"]:
        return {"symbol": "NATIVE", "decimals": 18}

    symbol = None
    decimals = 18

    # 1. Query symbol() selector 0x95d89b41
    try:
        res = w3.eth.call({'to': Web3.to_checksum_address(token_addr), 'data': '0x95d89b41'})
        if res and len(res) >= 32:
            try:
                symbol = w3.codec.decode(['string'], res)[0].strip()
            except Exception:
                symbol = decode_bytes32_string(res)
    except Exception:
        pass

    # 2. Query decimals() selector 0x313ce567
    try:
        res = w3.eth.call({'to': Web3.to_checksum_address(token_addr), 'data': '0x313ce567'})
        if res and len(res) >= 32:
            decimals = int(w3.codec.decode(['uint8'], res)[0])
    except Exception:
        pass

    if symbol and not symbol.startswith("0x"):
        # Clean non-ascii
        symbol = str(symbol).encode('ascii', 'ignore').decode('ascii').strip()
        if symbol:
            return {"symbol": symbol, "decimals": decimals}

    return None

def fetch_dexscreener_metadata(token_addresses):
    found = {}
    for i in range(0, len(token_addresses), 30):
        chunk = token_addresses[i:i+30]
        url = f"https://api.dexscreener.com/latest/dex/tokens/{','.join(chunk)}"
        try:
            res = requests.get(url, timeout=10).json()
            pairs = res.get("pairs", [])
            for p in pairs:
                base = p.get("baseToken", {})
                b_addr = base.get("address", "").lower()
                b_sym = str(base.get("symbol", "")).encode('ascii', 'ignore').decode('ascii').strip()
                if b_addr and b_sym and not b_sym.startswith("0x"):
                    found[b_addr] = {"symbol": b_sym, "decimals": 18}
        except Exception as e:
            safe_print(f"[-] DexScreener metadata error: {e}")
    return found

def resolve_all_token_metadata():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    cache = load_metadata_cache()
    safe_print("=" * 80)
    safe_print("ENRICHING & RESOLVING TOKEN TICKERS/SYMBOLS ACROSS ALL CHAINS")
    safe_print("=" * 80)

    for chain_name, chain_cfg in config["chains"].items():
        chain_id = chain_cfg["chain_id"]
        totals_file = os.path.join("data", f"vortex_{chain_name}_trade_totals.json")
        if not os.path.exists(totals_file):
            continue

        safe_print(f"\n[+] [{chain_name.upper()}] Processing {totals_file}...")
        with open(totals_file, "r", encoding="utf-8") as f:
            totals_data = json.load(f)

        rpc_env = chain_cfg.get("rpc_env", "")
        rpc_url = os.getenv(rpc_env, "").strip() if rpc_env else ""
        if not rpc_url:
            rpc_url = chain_cfg.get("public_rpc", "").strip()

        w3 = Web3(Web3.HTTPProvider(rpc_url)) if rpc_url else None
        
        # Native symbol override
        native_symbols = {"ethereum": "ETH", "sei": "SEI", "celo": "CELO", "tac": "TAC", "coti": "COTI"}
        native_sym = native_symbols.get(chain_name, "NATIVE")

        # Collect un-resolved addresses
        addresses_to_fetch = []
        for t_obj in totals_data:
            addr = t_obj["address"].lower()
            if addr == "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee":
                t_obj["symbol"] = native_sym
                cache[f"{chain_id}:{addr}"] = {"symbol": native_sym, "decimals": 18}
                continue

            current_sym = t_obj.get("symbol", "")
            if current_sym.startswith("0x") or not current_sym:
                addresses_to_fetch.append(addr)

        safe_print(f"    - Tokens needing symbol resolution: {len(addresses_to_fetch)} / {len(totals_data)}")

        # 1. Try raw RPC eth_call
        if w3 and addresses_to_fetch:
            safe_print("    - Attempting raw RPC eth_call symbol resolution...")
            for addr in list(addresses_to_fetch):
                meta = fetch_erc20_metadata_raw(w3, addr)
                if meta and meta.get("symbol"):
                    cache[f"{chain_id}:{addr}"] = meta
                    addresses_to_fetch.remove(addr)
                    safe_print(f"      [RPC SUCCESS] {addr} -> {meta['symbol']} (decimals {meta['decimals']})")

        # 2. Try DexScreener API fallback
        if addresses_to_fetch:
            safe_print(f"    - Attempting DexScreener API fallback for remaining {len(addresses_to_fetch)} tokens...")
            dex_meta = fetch_dexscreener_metadata(addresses_to_fetch)
            for addr, meta in dex_meta.items():
                cache[f"{chain_id}:{addr}"] = meta
                if addr in addresses_to_fetch:
                    addresses_to_fetch.remove(addr)
                safe_print(f"      [DEXSCREENER SUCCESS] {addr} -> {meta['symbol']}")

        # Apply updated symbols back to totals_data
        updated_count = 0
        for t_obj in totals_data:
            addr = t_obj["address"].lower()
            cached_meta = cache.get(f"{chain_id}:{addr}")
            if cached_meta and cached_meta.get("symbol"):
                if t_obj["symbol"] != cached_meta["symbol"]:
                    t_obj["symbol"] = cached_meta["symbol"]
                    t_obj["decimals"] = cached_meta.get("decimals", t_obj.get("decimals", 18))
                    updated_count += 1
                
                # Update inner trades
                for tr in t_obj.get("trades", []):
                    tr["target_symbol"] = t_obj["symbol"]
                    if tr["level"] == 1:
                        tr["pair_name"] = f"{t_obj['symbol']} → {native_sym}"

        with open(totals_file, "w", encoding="utf-8") as f:
            json.dump(totals_data, f, indent=2)

        safe_print(f"    [+] Updated {updated_count} token symbols in {totals_file}")

        # Update SQLite DB token_registry
        db = db_connect(DB_PATH)
        for t_obj in totals_data:
            addr = t_obj["address"].lower()
            sym = t_obj["symbol"]
            dec = t_obj["decimals"]
            db.execute("UPDATE token_registry SET symbol=?, decimals=? WHERE chain_id=? AND LOWER(token_address)=?", (sym, dec, chain_id, addr))
        db.commit()
        db.close()

    save_metadata_cache(cache)
    safe_print("\n[+] Saved consolidated metadata cache to data/token_metadata.json.")

if __name__ == "__main__":
    resolve_all_token_metadata()
