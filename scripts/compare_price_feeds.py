import os
import json
import time
import sqlite3
import requests
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Root and Env
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

# Safe Print helper for Windows Console encoding limits
def safe_str(s):
    if not s: return ""
    return str(s).encode('ascii', errors='replace').decode('ascii')

# Configurations
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
    total_batches = (len(mapped_addresses) + batch_size - 1) // batch_size if mapped_addresses else 0
    for idx, i in enumerate(range(0, len(mapped_addresses), batch_size)):
        batch = mapped_addresses[i:i+batch_size]
        print(f"      [~] DexScreener: querying batch {idx+1}/{total_batches} ({len(batch)} tokens)...")
        url = f"https://api.dexscreener.com/tokens/v1/{slug}/" + ",".join(batch)
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                resolved_count = 0
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
                        resolved_count += 1
                print(f"      [+] DexScreener: resolved {resolved_count} tokens from batch.")
            else:
                print(f"      [-] DexScreener: failed with status code {r.status_code}")
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
    
    print(f"      [~] Bancor: executing get_carbon_prices.js for {len(tokens)} tokens on-chain...")
    out = {}
    try:
        cmd = ["node", script_path, rpc_url, controller_addr, json.dumps(stables), json.dumps(targets)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=25)
        market_data = json.loads(result.stdout.strip())
        for k, v in market_data.items():
            out[k.lower()] = v["price_usd"]
        print(f"      [+] Bancor: resolved {len(market_data)} prices from strategies.")
    except subprocess.TimeoutExpired:
        print("      [-] Bancor: query timed out after 25 seconds.")
    except Exception as e:
        print(f"      [-] Bancor: execution failed: {e}")
    return out

def get_dia_price(symbol, dia_cache):
    if not symbol: return None
    sym_upper = symbol.upper()
    if sym_upper in dia_cache:
        return dia_cache[sym_upper]
    
    url = f"https://api.diadata.org/v1/quotation/{symbol}"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            price = r.json().get("Price")
            if price is not None:
                dia_cache[sym_upper] = float(price)
                return float(price)
    except Exception:
        pass
    dia_cache[sym_upper] = None
    return None

def main():
    # 1. Load symbols from user assets
    user_assets_path = ROOT / "config" / "user_assets.json"
    user_symbols = set()
    if user_assets_path.exists():
        with open(user_assets_path, 'r', encoding='utf-8') as f:
            assets = json.load(f)
            for item in assets:
                sym = item.get("Asset", {}).get("Symbol", "")
                if sym:
                    user_symbols.add(sym.lower())
    print(f"Loaded {len(user_symbols)} symbols for DIA pricing.")

    # 2. Get tokens from Database
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

    # Parse CLI flags/arguments to support per-chain benchmarking
    import sys
    args = sys.argv[1:]
    if args:
        requested = [arg.lower().strip() for arg in args]
        filtered = {cid: lst for cid, lst in tokens_by_chain.items() if chain_names[cid].lower() in requested}
        if not filtered:
            available = ", ".join(chain_names.values())
            print(f"[-] Error: None of the requested chains {requested} are configured. Available: {available}")
            sys.exit(1)
        tokens_by_chain = filtered
        print(f"[+] Benchmarking only: {', '.join(chain_names[cid] for cid in tokens_by_chain.keys())}")

    total_tokens_count = sum(len(lst) for lst in tokens_by_chain.values())
    print(f"Total tokens to price check: {total_tokens_count}")

    # ==========================================
    # RUN CASE 1: 2-layer (DexScreener + Carbon)
    # ==========================================
    print("\nStarting Case 1: 2-layer Price Feed (DexScreener -> Carbon)...")
    start_c1 = time.time()
    prices_c1 = {}
    resolved_layers_c1 = {"dex": 0, "carbon": 0, "failed": 0}
    
    for cid, tokens in tokens_by_chain.items():
        print(f"  [~] Processing {chain_names[cid]} Case 1...")
        # Query DexScreener for all
        addrs = [t["address"] for t in tokens]
        dex_prices = dexscreener_query(cid, addrs)
        
        # Identify missing tokens
        missing = []
        for t in tokens:
            addr_lower = t["address_lower"]
            if addr_lower in dex_prices:
                prices_c1[(cid, addr_lower)] = {
                    "price": dex_prices[addr_lower],
                    "layer": "DexScreener"
                }
                resolved_layers_c1["dex"] += 1
            else:
                missing.append(t)
                
        # Query Carbon on-chain for missing
        if missing:
            carbon_prices = estimate_carbon_prices(cid, missing)
            for t in missing:
                addr_lower = t["address_lower"]
                if addr_lower in carbon_prices:
                    prices_c1[(cid, addr_lower)] = {
                        "price": carbon_prices[addr_lower],
                        "layer": "Carbon Strategy"
                    }
                    resolved_layers_c1["carbon"] += 1
                else:
                    prices_c1[(cid, addr_lower)] = {
                        "price": None,
                        "layer": "Failed"
                    }
                    resolved_layers_c1["failed"] += 1
        else:
            print("    [+] No tokens missing on DexScreener.")
                    
    duration_c1 = time.time() - start_c1
    print(f"Case 1 completed in {duration_c1:.2f} seconds.")
    print("Resolved statistics:", resolved_layers_c1)

    # ======================================================
    # RUN CASE 2: 3-layer (DIA API + DexScreener + Carbon)
    # ======================================================
    print("\nStarting Case 2: 3-layer Price Feed (DIA API -> DexScreener -> Carbon)...")
    start_c2 = time.time()
    prices_c2 = {}
    resolved_layers_c2 = {"dia": 0, "dex": 0, "carbon": 0, "failed": 0}
    
    # 1. Collect all unique symbols matching DIA lists across all chains to query DIA API once globally first
    unique_dia_symbols = set()
    for cid, tokens in tokens_by_chain.items():
        for t in tokens:
            sym_lower = t["symbol"].lower()
            if sym_lower in user_symbols:
                unique_dia_symbols.add(t["symbol"]) # Keep original casing

    print(f"Querying {len(unique_dia_symbols)} unique symbols from DIA API globally...")
    dia_cache = {}
    for sym in sorted(list(unique_dia_symbols)):
        price = get_dia_price(sym, dia_cache)
        if price is not None:
            print(f"  [+] DIA Price: {safe_str(sym)} = ${price}")
        else:
            print(f"  [-] DIA Price: {safe_str(sym)} not found/failed")

    # 2. Chain loop - reads from dia_cache
    for cid, tokens in tokens_by_chain.items():
        print(f"  [~] Processing {chain_names[cid]} Case 2...")
        dia_tokens = []
        remaining = []
        
        # Separate DIA vs Remaining
        for t in tokens:
            sym_lower = t["symbol"].lower()
            if sym_lower in user_symbols:
                dia_tokens.append(t)
            else:
                remaining.append(t)
                
        # Read from DIA cache
        for t in dia_tokens:
            addr_lower = t["address_lower"]
            sym = t["symbol"]
            price = dia_cache.get(sym.upper())
            if price is not None:
                prices_c2[(cid, addr_lower)] = {
                    "price": price,
                    "layer": "DIA API"
                }
                resolved_layers_c2["dia"] += 1
            else:
                remaining.append(t)
                
        # Query DexScreener for remaining
        if remaining:
            addrs = [t["address"] for t in remaining]
            dex_prices = dexscreener_query(cid, addrs)
            still_missing = []
            for t in remaining:
                addr_lower = t["address_lower"]
                if addr_lower in dex_prices:
                    prices_c2[(cid, addr_lower)] = {
                        "price": dex_prices[addr_lower],
                        "layer": "DexScreener"
                    }
                    resolved_layers_c2["dex"] += 1
                else:
                    still_missing.append(t)
                    
            # Query Carbon for still missing
            if still_missing:
                carbon_prices = estimate_carbon_prices(cid, still_missing)
                for t in still_missing:
                    addr_lower = t["address_lower"]
                    if addr_lower in carbon_prices:
                        prices_c2[(cid, addr_lower)] = {
                            "price": carbon_prices[addr_lower],
                            "layer": "Carbon Strategy"
                        }
                        resolved_layers_c2["carbon"] += 1
                    else:
                        prices_c2[(cid, addr_lower)] = {
                            "price": None,
                            "layer": "Failed"
                        }
                        resolved_layers_c2["failed"] += 1
        else:
            print("    [+] No tokens remaining after DIA query.")
            
    duration_c2 = time.time() - start_c2
    print(f"Case 2 completed in {duration_c2:.2f} seconds.")
    print("Resolved statistics:", resolved_layers_c2)

    # ==========================================
    # COMPARE AND COMPILATE REPORT
    # ==========================================
    report_lines = []
    report_lines.append("# Price Feed Layers Comparison Report\n")
    report_lines.append("Comparison of **Case 1 (2-layer: DexScreener + Carbon)** and **Case 2 (3-layer: DIA API + DexScreener + Carbon)**.\n")
    
    report_lines.append("## 1. Performance and Resolution Summary\n")
    report_lines.append("| Metric | Case 1 (2-Layer) | Case 2 (3-Layer) | Difference |\n")
    report_lines.append("|---|---|---|---|\n")
    report_lines.append(f"| **Execution Time** | {duration_c1:.2f} seconds | {duration_c2:.2f} seconds | {duration_c2 - duration_c1:+.2f} seconds | \n")
    report_lines.append(f"| **Total Tokens Checked** | {total_tokens_count} | {total_tokens_count} | - |\n")
    report_lines.append(f"| **Resolved successfully** | {resolved_layers_c1['dex'] + resolved_layers_c1['carbon']} | {resolved_layers_c2['dia'] + resolved_layers_c2['dex'] + resolved_layers_c2['carbon']} | { (resolved_layers_c2['dia'] + resolved_layers_c2['dex'] + resolved_layers_c2['carbon']) - (resolved_layers_c1['dex'] + resolved_layers_c1['carbon']):+d} |\n")
    report_lines.append(f"| **- From DIA API** | - | {resolved_layers_c2['dia']} | +{resolved_layers_c2['dia']} |\n")
    report_lines.append(f"| **- From DexScreener** | {resolved_layers_c1['dex']} | {resolved_layers_c2['dex']} | {resolved_layers_c2['dex'] - resolved_layers_c1['dex']:+d} |\n")
    report_lines.append(f"| **- From Carbon Strategy** | {resolved_layers_c1['carbon']} | {resolved_layers_c2['carbon']} | {resolved_layers_c2['carbon'] - resolved_layers_c1['carbon']:+d} |\n")
    report_lines.append(f"| **Failed / Unresolved** | {resolved_layers_c1['failed']} | {resolved_layers_c2['failed']} | {resolved_layers_c2['failed'] - resolved_layers_c1['failed']:+d} |\n\n")

    report_lines.append("## 2. Price Differences (Side-by-Side)\n")
    report_lines.append("Listing tokens resolved by both price feeds to check for price deviations.\n")
    report_lines.append("| Chain | Symbol | Address | Case 1 Price (USD) | Case 2 Price (USD) | Source (C1 / C2) | Diff ($) | Diff (%) |\n")
    report_lines.append("|---|---|---|---|---|---|---|---|\n")
    
    comparable_prices = []
    
    # Compile comparison rows
    for cid, tokens in tokens_by_chain.items():
        cname = chain_names[cid]
        for t in tokens:
            addr_lower = t["address_lower"]
            info1 = prices_c1.get((cid, addr_lower))
            info2 = prices_c2.get((cid, addr_lower))
            
            if info1 and info2 and info1["price"] is not None and info2["price"] is not None:
                p1 = info1["price"]
                p2 = info2["price"]
                diff = p2 - p1
                pct_diff = (diff / p1 * 100.0) if p1 != 0 else 0.0
                
                comparable_prices.append({
                    "chain": cname,
                    "symbol": safe_str(t["symbol"]),
                    "address": t["address"],
                    "p1": p1,
                    "p2": p2,
                    "layer1": info1["layer"],
                    "layer2": info2["layer"],
                    "diff": diff,
                    "pct_diff": pct_diff
                })

    # Sort by absolute percentage difference descending
    for r in sorted(comparable_prices, key=lambda x: abs(x["pct_diff"]), reverse=True):
        report_lines.append(f"| {r['chain']} | {r['symbol']} | `{r['address']}` | ${r['p1']:,.6f} | ${r['p2']:,.6f} | {r['layer1']} / {r['layer2']} | {r['diff']:+,.6f} | {r['pct_diff']:+,.2f}% |\n")

    report_content = "".join(report_lines)
    
    # Save report
    report_path = ROOT / "data" / "price_comparison_report.md"
    report_path.write_text(report_content, encoding="utf-8")
    
    print("\n" + "="*50)
    print(f"COMPARISON COMPLETED AND SAVED TO: {report_path}")
    print("="*50)
    
if __name__ == "__main__":
    main()
