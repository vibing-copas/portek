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
from carbon_tracker.storage.db import connect as db_connect, upsert_token, snapshot, save_scan_progress
from carbon_tracker.blockchain.vortex import classify as classify_vortex

dotenv.load_dotenv()

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
CONTEXTS_PATH = os.path.join("data", "vortex_contexts.json")
METADATA_CACHE_FILE = os.path.join("data", "token_metadata.json")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API", "RI1364SKZMWSMCE2KD1NCHM7A354W6MSDS")
DB_PATH = os.getenv("DB_PATH", "data/tracker.db")
TOPIC0_FILTER = "0x16ddee9b3f1b2e6f797172fe2cd10a214e749294074e075e451f95aecd0b958c"

CREATION_BLOCKS = {
    "ethereum": 20469389,
    "sei": 105711575,
    "celo": 66870924,
    "tac": 24573345,
    "coti": 6609022
}

NATIVE_SYMBOLS = {
    "ethereum": "ETH",
    "sei": "SEI",
    "celo": "CELO",
    "tac": "TAC",
    "coti": "COTI"
}

FINAL_SYMBOLS = {
    "ethereum": "BNT",
    "sei": "WETH",
    "celo": "WETH",
    "tac": "WETH",
    "coti": "WETH"
}

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_contexts():
    if os.path.exists(CONTEXTS_PATH):
        with open(CONTEXTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

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

def fetch_logs_etherscan_v2(chain_name, chain_id, vortex_addr, from_block):
    print(f"\n[+] [{chain_name.upper()}] Fetching event logs via Etherscan V2 API...")
    print(f"    Vortex Address : {vortex_addr}")
    print(f"    Start Block    : {from_block:,}")
    
    url = "https://api.etherscan.io/v2/api"
    all_logs = []
    current_from = from_block
    
    while True:
        params = {
            "chainid": chain_id,
            "module": "logs",
            "action": "getLogs",
            "address": vortex_addr,
            "fromBlock": current_from,
            "toBlock": "latest",
            "topic0": TOPIC0_FILTER,
            "apikey": ETHERSCAN_API_KEY
        }
        
        try:
            res = requests.get(url, params=params, timeout=20).json()
            status = res.get("status")
            result = res.get("result", [])
            
            if status != "1" or not isinstance(result, list):
                msg = res.get("message", res)
                print(f"    [~] API response: {msg}")
                break
                
            all_logs.extend(result)
            print(f"    [+] Chunk fetched: {len(result)} logs. Total: {len(all_logs)} logs.")
            
            if len(result) < 1000:
                break
                
            last_block = int(result[-1]["blockNumber"], 16)
            current_from = last_block + 1
            time.sleep(0.2)
        except Exception as e:
            print(f"    [-] Error fetching logs chunk: {e}")
            break
            
    print(f"[+] [{chain_name.upper()}] Total raw event logs: {len(all_logs)}")
    return all_logs

def decode_bytes32_string(val_bytes):
    try:
        val_str = val_bytes.rstrip(b'\x00').decode('utf-8', errors='ignore').strip()
        return val_str if val_str else None
    except Exception:
        return None

def fetch_erc20_metadata_rpc(w3, chain_id, addresses, cache, native_sym):
    metadata = {}
    for addr in set(addresses):
        addr_lower = addr.lower()
        if addr_lower in ["0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", "0x0000000000000000000000000000000000000000"]:
            metadata[addr_lower] = {"symbol": native_sym, "decimals": 18}
            continue

        cache_key = f"{chain_id}:{addr_lower}"
        if cache_key in cache and cache[cache_key].get("symbol") and not cache[cache_key]["symbol"].startswith("0x"):
            metadata[addr_lower] = cache[cache_key]
            continue
            
        symbol = None
        decimals = 18

        if w3:
            # Query symbol()
            try:
                res = w3.eth.call({'to': Web3.to_checksum_address(addr), 'data': '0x95d89b41'})
                if res and len(res) >= 32:
                    try:
                        symbol = w3.codec.decode(['string'], res)[0].strip()
                    except Exception:
                        symbol = decode_bytes32_string(res)
            except Exception:
                pass

            # Query decimals()
            try:
                res = w3.eth.call({'to': Web3.to_checksum_address(addr), 'data': '0x313ce567'})
                if res and len(res) >= 32:
                    decimals = int(w3.codec.decode(['uint8'], res)[0])
            except Exception:
                pass

        if symbol and not symbol.startswith("0x"):
            symbol_clean = str(symbol).encode('ascii', 'ignore').decode('ascii').strip()
            if symbol_clean:
                meta = {"symbol": symbol_clean, "decimals": decimals}
                metadata[addr_lower] = meta
                cache[cache_key] = meta
                continue

        metadata[addr_lower] = {"symbol": addr[:6] + "..." + addr[-4:], "decimals": decimals}
            
    return metadata

def fetch_dexscreener_metadata_fallback(chain_id, addresses, cache):
    unresolved = [a.lower() for a in addresses if cache.get(f"{chain_id}:{a.lower()}", {}).get("symbol", "").startswith("0x") or not cache.get(f"{chain_id}:{a.lower()}")]
    if not unresolved:
        return

    for i in range(0, len(unresolved), 30):
        chunk = unresolved[i:i+30]
        url = f"https://api.dexscreener.com/latest/dex/tokens/{','.join(chunk)}"
        try:
            res = requests.get(url, timeout=10).json()
            pairs = res.get("pairs", [])
            for p in pairs:
                base = p.get("baseToken", {})
                b_addr = base.get("address", "").lower()
                b_sym = str(base.get("symbol", "")).encode('ascii', 'ignore').decode('ascii').strip()
                if b_addr and b_sym and not b_sym.startswith("0x"):
                    cache[f"{chain_id}:{b_addr}"] = {"symbol": b_sym, "decimals": 18}
        except Exception:
            pass

def fetch_prices_defilllama(chain_name, token_addresses):
    prefix_map = {"ethereum": "ethereum", "sei": "sei", "celo": "celo", "tac": "tac"}
    prefix = prefix_map.get(chain_name, chain_name)
    
    prices = {}
    keys = [f"{prefix}:{addr}" for addr in token_addresses]
    
    for i in range(0, len(keys), 80):
        chunk = keys[i:i+80]
        url = f"https://coins.llama.fi/prices/current/{','.join(chunk)}"
        try:
            res = requests.get(url, timeout=10).json()
            coins = res.get("coins", {})
            for k, val in coins.items():
                addr = k.split(":")[-1].lower()
                prices[addr] = float(val.get("price", 0.0))
        except Exception:
            pass
            
    return prices

def process_chain(chain_name, chain_cfg, chain_ctx, cache):
    chain_id = chain_cfg["chain_id"]
    vortex_addr = chain_cfg["carbon_vortex"]
    rpc_url = os.getenv(chain_cfg.get("rpc_env", ""), chain_cfg.get("public_rpc"))
    creation_block = CREATION_BLOCKS.get(chain_name, 0)
    
    native_sym = NATIVE_SYMBOLS.get(chain_name, "NATIVE")
    final_sym = FINAL_SYMBOLS.get(chain_name, "WETH")
    
    target_token_addr = chain_ctx.get("target_token", "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee")
    final_target_token_addr = chain_ctx.get("final_target_token", "0x160345fc359604fc6e70e3c5facbde5f7a9342d8" if chain_name=="sei" else "0x1f573d6fb3f13d689ff844b4ce37794d79a7ff1c")
    target_sym = chain_ctx.get("target_symbol") or native_sym
    
    raw_logs = fetch_logs_etherscan_v2(chain_name, chain_id, vortex_addr, creation_block)
    if not raw_logs:
        return
        
    json_path = os.path.join("data", f"vortex_{chain_name}_logs.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(raw_logs, f, indent=2)
        
    topic2_addresses = []
    for log in raw_logs:
        topics = log.get("topics", [])
        if len(topics) >= 3:
            clean_addr = "0x" + topics[2][-40:].lower()
            if clean_addr not in topic2_addresses:
                topic2_addresses.append(clean_addr)
                
    w3 = Web3(Web3.HTTPProvider(rpc_url)) if rpc_url else None
    metadata = fetch_erc20_metadata_rpc(w3, chain_id, topic2_addresses, cache, native_sym)
    fetch_dexscreener_metadata_fallback(chain_id, topic2_addresses, cache)
    
    # Re-apply cache to metadata
    for addr in topic2_addresses:
        ckey = f"{chain_id}:{addr}"
        if ckey in cache and cache[ckey].get("symbol") and not cache[ckey]["symbol"].startswith("0x"):
            metadata[addr] = cache[ckey]

    prices = fetch_prices_defilllama(chain_name, topic2_addresses)
    
    token_trades = {}
    db = db_connect(DB_PATH)
    min_block = None
    max_block = None
    
    v_ctx = {
        "target_token": target_token_addr,
        "final_target_token": final_target_token_addr
    }
    
    for log in raw_logs:
        topics = log.get("topics", [])
        data_hex = log.get("data", "0x")[2:]
        block_num = int(log.get("blockNumber", "0x0"), 16)
        tx_hash = log.get("transactionHash", "")
        ts_raw = int(log.get("timeStamp", "0x0"), 16)
        ts_formatted = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(ts_raw)) if ts_raw else "N/A"
        
        if min_block is None or block_num < min_block: min_block = block_num
        if max_block is None or block_num > max_block: max_block = block_num
        
        caller = "0x" + topics[1][-40:].lower() if len(topics) >= 2 else "0x"
        token_addr = "0x" + topics[2][-40:].lower() if len(topics) >= 3 else "0x"
        
        source_raw_int = int(data_hex[0:64], 16) if len(data_hex) >= 64 else 0
        target_raw_int = int(data_hex[64:128], 16) if len(data_hex) >= 128 else 0
        
        class_res = classify_vortex(token_addr, v_ctx)
        level = class_res["level"] or 1
        
        meta = metadata.get(token_addr, {"symbol": token_addr[:8], "decimals": 18})
        symbol = meta["symbol"]
        if token_addr == "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee":
            symbol = native_sym
        decimals = meta["decimals"]
        
        target_formatted = target_raw_int / (10 ** decimals)
        source_symbol = final_sym if level == 2 else native_sym
        source_decimals = 18
        source_formatted = source_raw_int / (10 ** source_decimals)
        
        unit_price = prices.get(token_addr, 0.0)
        usd_value = target_formatted * unit_price
        if usd_value == 0 and source_formatted > 0 and native_sym.lower() in prices:
            usd_value = source_formatted * prices.get(native_sym.lower(), 0.0)
            
        trade_entry = {
            "tx_hash": tx_hash,
            "block_number": block_num,
            "timestamp": ts_formatted,
            "timestamp_raw": ts_raw,
            "caller": caller,
            "level": level,
            "pair_name": f"{native_sym} → {final_sym}" if level == 2 else f"{symbol} → {native_sym}",
            "source_symbol": source_symbol,
            "source_raw": str(source_raw_int),
            "source_formatted": source_formatted,
            "target_symbol": symbol,
            "target_raw": str(target_raw_int),
            "target_formatted": target_formatted,
            "usd_value": usd_value
        }
        
        if token_addr not in token_trades:
            token_trades[token_addr] = {
                "symbol": symbol,
                "decimals": decimals,
                "address": token_addr,
                "level": level,
                "source_symbol": source_symbol,
                "total_amount": 0.0,
                "total_source_amount": 0.0,
                "total_raw": 0,
                "volume_usd": 0.0,
                "avg_unit_price": unit_price,
                "trade_count": 0,
                "trades": []
            }
            
        t_obj = token_trades[token_addr]
        t_obj["trade_count"] += 1
        t_obj["total_amount"] += target_formatted
        t_obj["total_source_amount"] += source_formatted
        t_obj["total_raw"] += target_raw_int
        t_obj["volume_usd"] += usd_value
        t_obj["trades"].append(trade_entry)
        
        snapshot_payload = {
            "chain_id": chain_id,
            "token_address": token_addr,
            "symbol": symbol,
            "level": level,
            "pair_name": trade_entry["pair_name"],
            "tx_hash": tx_hash,
            "block_number": block_num,
            "caller": caller,
            "source_symbol": source_symbol,
            "source_formatted": source_formatted,
            "target_formatted": target_formatted,
            "usd_value": usd_value
        }
        snapshot(db, ts_raw, chain_id, "vortex_trade_event", level, token_addr, snapshot_payload)
        
    totals_list = list(token_trades.values())
    totals_json_path = os.path.join("data", f"vortex_{chain_name}_trade_totals.json")
    with open(totals_json_path, "w", encoding="utf-8") as f:
        json.dump(totals_list, f, indent=2)
        
    for t_obj in totals_list:
        t_addr = t_obj["address"]
        t_trades = t_obj["trades"]
        blocks = [t["block_number"] for t in t_trades]
        first_seen = min(blocks) if blocks else None
        last_seen = max(blocks) if blocks else None
        last_tr = t_trades[0] if t_trades else {}
        
        meta_db = {"symbol": t_obj["symbol"], "decimals": t_obj["decimals"]}
        info_db = {
            "first_seen_block": first_seen,
            "last_seen_block": last_seen,
            "events": t_obj["trade_count"],
            "last_fee_raw": str(t_obj["total_raw"]),
            "last_trade_source": t_obj["source_symbol"],
            "last_trade_target": t_obj["symbol"],
            "last_trade_source_amount": str(last_tr.get("source_formatted", "")),
            "last_trade_target_amount": str(last_tr.get("target_formatted", "")),
            "last_trade_block": last_seen
        }
        upsert_token(db, chain_id, t_addr, meta_db, info_db)
        
    if min_block and max_block:
        save_scan_progress(db, chain_id, min_block, max_block)
        
    db.commit()
    db.close()
    print(f"[+] [{chain_name.upper()}] Consolidated {len(totals_list)} unique tokens & {len(raw_logs)} events into {DB_PATH}.")

def main():
    config = load_config()
    contexts = load_contexts()
    cache = load_metadata_cache()
    target_chains = ["sei", "celo"]
    
    if len(sys.argv) > 1:
        req = [a.lower() for a in sys.argv[1:]]
        target_chains = [c for c in req if c in config["chains"]]
        
    for chain_name in target_chains:
        chain_cfg = config["chains"][chain_name]
        chain_ctx = contexts.get(chain_name, {})
        process_chain(chain_name, chain_cfg, chain_ctx, cache)

    save_metadata_cache(cache)

if __name__ == "__main__":
    main()
