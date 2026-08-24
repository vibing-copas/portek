import os, sys, time
from web3 import Web3
from .config import load_config, ROOT
from .blockchain.client import connect, contract
from .blockchain.discovery import discover_fee_tokens
from .blockchain.vortex import context, classify
from .market.dexscreener import query as dexscreener_query
from .market.bybit import query as bybit_query

ERC20_ABI = [
    {"name":"symbol","outputs":[{"type":"string"}],"inputs":[],"stateMutability":"view","type":"function"},
    {"name":"name","outputs":[{"type":"string"}],"inputs":[],"stateMutability":"view","type":"function"},
    {"name":"decimals","outputs":[{"type":"uint8"}],"inputs":[],"stateMutability":"view","type":"function"},
]

MULTICALL_ADDRESS = "0xcA11bde05977b3631167028862bE2a173976CA11"
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

CHAIN_NAMES = {
    1: "ethereum",
    1329: "sei",
    239: "tac",
    42220: "celo",
    2632500: "coti"
}

STABLECOINS_MAP = {
    1: [
        ("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", 6),  # USDC on Ethereum
        ("0xdAC17F958D2ee523a2206206994597C13D831ec7", 6),  # USDT on Ethereum
    ],
    1329: [
        ("0xe15fC38F6D8c56aF07bbCBe3BAf5708A2Bf42392", 6),  # Native USDC on Sei
        ("0x3894085ef7ff0f0aedf52e2a2704928d1ec074f1", 6),  # Noble USDC on Sei
    ],
    239: [
        ("0xAF988C3f7CB2AceAbB15f96b19388a259b6C438f", 6),  # USDT on TAC
    ],
    42220: [
        ("0x765DE816845861e75A25fCA122bb6898B8B1282a", 18), # cUSD on Celo
        ("0xef1ba8c77e1c9e328e100d8546b95ee34174adc1", 6),  # USDC on Celo
    ],
    2632500: [
        ("0xf1Feebc4376c68B7003450ae66343Ae59AB37D3C", 6),  # USDC.e on COTI V2
    ]
}


def decode_result(w3, type_str, success, data, fallback):
    if not success or not data:
        return fallback
    try:
        return w3.codec.decode([type_str], data)[0]
    except Exception:
        return fallback


def estimate_blocks_for_duration(w3, duration_seconds=86400, default_block_time=12.0):
    try:
        latest = w3.eth.get_block('latest')
        latest_num = latest.number
        latest_ts = latest.timestamp
        
        lookback_sample = min(2000, latest_num)
        if lookback_sample <= 0:
            return int(duration_seconds / default_block_time)
            
        older = w3.eth.get_block(latest_num - lookback_sample)
        older_ts = older.timestamp
        
        time_diff = latest_ts - older_ts
        if time_diff <= 0:
            return int(duration_seconds / default_block_time)
            
        avg_block_time = time_diff / lookback_sample
        return int(duration_seconds / avg_block_time)
    except Exception as e:
        fallback_blocks = int(duration_seconds / default_block_time)
        print(f"[-] Warning: Failed to estimate blocks dynamically: {e}. Using chain fallback {fallback_blocks} blocks.")
        return fallback_blocks


def fetch_token_metadata(w3, token, chain_name):
    if token.lower() == "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee":
        native_map = {
            "ethereum": {"symbol": "ETH", "name": "Ether", "decimals": 18},
            "sei": {"symbol": "SEI", "name": "Sei", "decimals": 18},
            "tac": {"symbol": "TAC", "name": "Tac", "decimals": 18},
            "celo": {"symbol": "CELO", "name": "Celo", "decimals": 18},
            "coti": {"symbol": "COTI", "name": "Coti", "decimals": 18},
        }
        return native_map.get(chain_name.lower(), {"symbol": "ETH", "name": "Ether", "decimals": 18})
    try:
        contract_obj = w3.eth.contract(address=Web3.to_checksum_address(token), abi=ERC20_ABI)
        symbol = contract_obj.functions.symbol().call()
        decimals = contract_obj.functions.decimals().call()
        return {"symbol": symbol, "decimals": int(decimals)}
    except Exception as e:
        print(f"[-] Failed to fetch ERC20 metadata for {token}: {e}")
        return {"symbol": token[:6], "decimals": 18}


def fetch_tokens_metadata_batched(w3, tokens, chain_name, multicall_address):
    native_addr = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    native_map = {
        "ethereum": {"symbol": "ETH", "decimals": 18},
        "sei": {"symbol": "SEI", "decimals": 18},
        "tac": {"symbol": "TAC", "decimals": 18},
        "celo": {"symbol": "CELO", "decimals": 18},
        "coti": {"symbol": "COTI", "decimals": 18},
    }
    
    token_metadata = {}
    tokens_to_fetch = []
    
    for t in tokens:
        t_lower = t.lower()
        if t_lower == native_addr:
            token_metadata[t_lower] = native_map.get(chain_name.lower(), {"symbol": "ETH", "decimals": 18})
        else:
            tokens_to_fetch.append(t)
            
    if not tokens_to_fetch:
        return token_metadata

    try:
        multicall = w3.eth.contract(address=Web3.to_checksum_address(multicall_address), abi=MULTICALL_ABI)
        erc20 = w3.eth.contract(abi=ERC20_ABI)
        calls = []
        for t in tokens_to_fetch:
            checksum_t = Web3.to_checksum_address(t)
            calls.append({
                "target": checksum_t,
                "allowFailure": True,
                "callData": w3.to_bytes(hexstr=erc20.encode_abi("symbol", []))
            })
            calls.append({
                "target": checksum_t,
                "allowFailure": True,
                "callData": w3.to_bytes(hexstr=erc20.encode_abi("decimals", []))
            })
            
        results = multicall.functions.aggregate3(calls).call()
        
        for i, t in enumerate(tokens_to_fetch):
            symbol_success, symbol_data = results[i * 2]
            decimals_success, decimals_data = results[i * 2 + 1]
            
            symbol = decode_result(w3, "string", symbol_success, symbol_data, None)
            if not symbol and symbol_success and symbol_data:
                try:
                    symbol = w3.codec.decode(["bytes32"], symbol_data)[0].decode('utf-8', errors='ignore').strip('\x00')
                except Exception:
                    pass
            if not symbol:
                symbol = t[:6]
                
            decimals = decode_result(w3, "uint8", decimals_success, decimals_data, 18)
            token_metadata[t.lower()] = {
                "symbol": symbol,
                "decimals": int(decimals)
            }
    except Exception as e:
        print(f"[-] Batch metadata multicall failed: {e}. Falling back to sequential.")
        for t in tokens_to_fetch:
            token_metadata[t.lower()] = fetch_token_metadata(w3, t, chain_name)
            
    return token_metadata



def estimate_fallback_price(token_addr, chain_tokens, market):
    token_info = next((t for t in chain_tokens if t[0].lower() == token_addr.lower()), None)
    if not token_info or len(token_info) < 8:
        return None
        
    src_addr = token_info[3]
    tgt_addr = token_info[4]
    if not src_addr or not tgt_addr:
        return None
        
    try:
        src_amount = int(token_info[5])
        tgt_amount = int(token_info[6])
    except (ValueError, TypeError):
        return None
        
    if src_amount <= 0 or tgt_amount <= 0:
        return None
        
    src_meta = next((t for t in chain_tokens if t[0].lower() == src_addr.lower()), None)
    src_dec = src_meta[2] if src_meta else 18
    
    tgt_meta = next((t for t in chain_tokens if t[0].lower() == tgt_addr.lower()), None)
    tgt_dec = tgt_meta[2] if tgt_meta else 18
    
    if token_addr.lower() == src_addr.lower():
        tgt_price = market.get(tgt_addr.lower(), {}).get("price_usd")
        if tgt_price is not None:
            rate = (tgt_amount / 10**tgt_dec) / (src_amount / 10**src_dec)
            return rate * tgt_price
    elif token_addr.lower() == tgt_addr.lower():
        src_price = market.get(src_addr.lower(), {}).get("price_usd")
        if src_price is not None:
            rate = (src_amount / 10**src_dec) / (tgt_amount / 10**tgt_dec)
            return rate * src_price
            
def fetch_global_prices():
    prices = {"eth": 2400.0, "btc": 70000.0}
    try:
        import requests
        url = "https://api.dexscreener.com/tokens/v1/ethereum/0xC02aaA39b223FE8D0A0e5C4F27ead9083C756Cc2,0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            for pair in data:
                base_addr = pair.get("baseToken", {}).get("address", "").lower()
                price_usd = pair.get("priceUsd")
                if price_usd is not None:
                    if base_addr == "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2":
                        prices["eth"] = float(price_usd)
                    elif base_addr == "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599":
                        prices["btc"] = float(price_usd)
    except Exception as e:
        print(f"  [-] Failed to fetch global mainnet prices: {e}. Using defaults.")
    return prices


def estimate_carbon_prices(w3, controller, multicall, chain_id, tokens):
    import subprocess
    import json
    
    # 1. Ensure node_modules is installed
    node_modules_path = ROOT / "node_modules"
    if not node_modules_path.exists():
        print("  [~] Node dependencies (node_modules) not found. Running npm install...")
        try:
            npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
            subprocess.run([npm_cmd, "install"], cwd=str(ROOT), check=True)
            print("  [+] Node dependencies installed successfully.")
        except Exception as e:
            print(f"  [-] Failed to install node dependencies: {e}. Falling back to default on-chain pricing.")
            return estimate_carbon_prices_fallback(w3, controller, multicall, chain_id, tokens)
            
    # 2. Find RPC URL
    rpc_url = ""
    if hasattr(w3.provider, "endpoint_uri"):
        rpc_url = w3.provider.endpoint_uri
    if not rpc_url:
        cfg = load_config()
        for name, c in cfg["chains"].items():
            if c["chain_id"] == chain_id:
                rpc_url = os.getenv(c["rpc_env"], "").strip()
                if not rpc_url:
                    rpc_url = c.get("public_rpc", "").strip()
                break
                
    if not rpc_url:
        print("  [-] Could not resolve RPC URL. Falling back to default on-chain pricing.")
        return estimate_carbon_prices_fallback(w3, controller, multicall, chain_id, tokens)

    stables = STABLECOINS_MAP.get(chain_id, [])
    tokens_input = [(t[0], t[1], t[2]) for t in tokens]
    
    # 3. Call get_carbon_prices.js
    script_path = str(ROOT / "scripts" / "get_carbon_prices.js")
    try:
        print(f"  [~] pricing: executing @bancor/carbon-sdk price feed for chain {chain_id}...")
        result = subprocess.run(
            ["node", script_path, rpc_url, controller.address, json.dumps(stables), json.dumps(tokens_input)],
            capture_output=True,
            text=True,
            check=True
        )
        market = json.loads(result.stdout.strip())
        print(f"  [+] @bancor/carbon-sdk resolved {len(market)} pricing entries: {list(market.keys())}")
        return market
    except subprocess.CalledProcessError as cpe:
        print(f"  [-] @bancor/carbon-sdk pricing failed (status {cpe.returncode}): {cpe.stderr.strip()}. Falling back to default on-chain pricing.")
        return estimate_carbon_prices_fallback(w3, controller, multicall, chain_id, tokens)
    except Exception as e:
        print(f"  [-] @bancor/carbon-sdk pricing failed: {e}. Falling back to default on-chain pricing.")
        return estimate_carbon_prices_fallback(w3, controller, multicall, chain_id, tokens)


def estimate_carbon_prices_fallback(w3, controller, multicall, chain_id, tokens):
    prices = {}
    chain_stables = STABLECOINS_MAP.get(chain_id, [])
    for addr, dec in chain_stables:
        prices[addr.lower()] = 1.0
        
    native_addr = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    native_dec = 18
    
    try:
        existing_pairs_raw = controller.functions.pairs().call()
        existing_pairs = [(p[0].lower(), p[1].lower()) for p in existing_pairs_raw]
    except Exception:
        existing_pairs = []
        
    if not existing_pairs:
        return {}
        
    target_addresses = {t[0].lower() for t in tokens}
    target_addresses.add(native_addr)
    stable_addresses = {s[0].lower() for s in chain_stables}
    
    relevant_pairs = []
    for t0, t1 in existing_pairs:
        is_t0_target = t0 in target_addresses
        is_t1_target = t1 in target_addresses
        is_t0_stable = t0 in stable_addresses or t0 == native_addr
        is_t1_stable = t1 in stable_addresses or t1 == native_addr
        
        if (is_t0_target and is_t1_stable) or (is_t1_target and is_t0_stable):
            relevant_pairs.append((t0, t1))
            
    if not relevant_pairs:
        return {}
        
    calls1 = []
    for t0, t1 in relevant_pairs:
        calls1.append({
            "target": controller.address,
            "allowFailure": True,
            "callData": w3.to_bytes(hexstr=controller.encode_abi("strategiesByPairCount", [
                Web3.to_checksum_address(t0), 
                Web3.to_checksum_address(t1)
            ]))
        })
        
    print(f"  [~] pricing: querying strategy counts for {len(relevant_pairs)} relevant token pairs...")
    try:
        results1 = multicall.functions.aggregate3(calls1).call()
    except Exception:
        results1 = [(False, b"")] * len(calls1)
        
    pairs_with_strategies = []
    for idx, (t0, t1) in enumerate(relevant_pairs):
        success, data = results1[idx]
        count = decode_result(w3, "uint256", success, data, 0)
        if count > 0:
            pairs_with_strategies.append(((t0, t1), count))
            
    if not pairs_with_strategies:
        return {}
        
    calls2 = []
    for (t0, t1), count in pairs_with_strategies:
        calls2.append({
            "target": controller.address,
            "allowFailure": True,
            "callData": w3.to_bytes(hexstr=controller.encode_abi("strategiesByPair", [
                Web3.to_checksum_address(t0), 
                Web3.to_checksum_address(t1),
                0,
                count
            ]))
        })
        
    print(f"  [~] pricing: fetching active strategy parameters for {len(pairs_with_strategies)} active pairs...")
    try:
        results2 = multicall.functions.aggregate3(calls2).call()
    except Exception:
        results2 = [(False, b"")] * len(calls2)
        
    strategy_type = "(uint256,address,address[2],(uint128,uint128,uint64,uint64)[2])[]"
    
    pair_strategies = {}
    for idx, ((t0, t1), count) in enumerate(pairs_with_strategies):
        success, data = results2[idx]
        if success and data:
            try:
                strats = w3.codec.decode([strategy_type], data)[0]
                pair_strategies[(t0, t1)] = strats
            except Exception as dec_err:
                print(f"[-] Decode error for strategies of pair ({t0}, {t1}): {dec_err}")
                
    if not pair_strategies:
        return {}
        
    decimals_map = {t[0].lower(): t[2] for t in tokens}
    decimals_map[native_addr] = native_dec
    for addr, dec in chain_stables:
        decimals_map[addr.lower()] = dec
        
    combos_to_quote = []
    if native_addr not in prices:
        for stable_addr, stable_dec in chain_stables:
            combos_to_quote.append((native_addr, stable_addr.lower(), native_dec, stable_dec))
            
    for t_tuple in tokens:
        t_addr = t_tuple[0].lower()
        if t_addr in prices:
            continue
        t_dec = t_tuple[2]
        for stable_addr, stable_dec in chain_stables:
            combos_to_quote.append((t_addr, stable_addr.lower(), t_dec, stable_dec))
        combos_to_quote.append((t_addr, native_addr, t_dec, native_dec))
        
    calls3 = []
    combo_metadata = []
    
    for src, tgt, src_dec, tgt_dec in combos_to_quote:
        strategies = pair_strategies.get((src, tgt))
        is_token0 = True
        if not strategies:
            strategies = pair_strategies.get((tgt, src))
            is_token0 = False
            
        if not strategies:
            continue
            
        trade_actions = []
        total_source_amount = 0
        
        for strat in strategies:
            strat_id = strat[0]
            order0 = strat[3][0]
            order1 = strat[3][1]
            if is_token0:
                y = order1[0]
                if y > 0:
                    amount = 10**(src_dec - 3) if src_dec >= 3 else 1
                    trade_actions.append({"strategyId": strat_id, "amount": amount})
                    total_source_amount += amount
            else:
                y = order0[0]
                if y > 0:
                    amount = 10**(src_dec - 3) if src_dec >= 3 else 1
                    trade_actions.append({"strategyId": strat_id, "amount": amount})
                    total_source_amount += amount
                    
        if not trade_actions:
            continue
            
        calls3.append({
            "target": controller.address,
            "allowFailure": True,
            "callData": w3.to_bytes(hexstr=controller.encode_abi("calculateTradeTargetAmount", [
                Web3.to_checksum_address(src),
                Web3.to_checksum_address(tgt),
                trade_actions
            ]))
        })
        combo_metadata.append((src, tgt, src_dec, tgt_dec, total_source_amount))
        
    if not calls3:
        return {}
        
    print(f"  [~] pricing: simulating calculateTradeTargetAmount swaps for {len(calls3)} active directions...")
    try:
        results3 = multicall.functions.aggregate3(calls3).call()
    except Exception:
        results3 = [(False, b"")] * len(calls3)
        
    for idx, (src, tgt, src_dec, tgt_dec, total_src) in enumerate(combo_metadata):
        success, data = results3[idx]
        if success and data:
            try:
                target_amount = w3.codec.decode(["uint128"], data)[0]
                rate = (target_amount / 10**tgt_dec) / (total_src / 10**src_dec)
                if tgt in prices:
                    prices[src] = rate * prices[tgt]
            except Exception as parse_err:
                print(f"[-] Failed to decode trade simulation return: {parse_err}")
                
    for src, tgt, src_dec, tgt_dec, total_src in combo_metadata:
        if src not in prices and tgt in prices:
            try:
                idx = combo_metadata.index((src, tgt, src_dec, tgt_dec, total_src))
                success, data = results3[idx]
                if success and data:
                    target_amount = w3.codec.decode(["uint128"], data)[0]
                    rate = (target_amount / 10**tgt_dec) / (total_src / 10**src_dec)
                    prices[src] = rate * prices[tgt]
            except Exception:
                pass

    market = {}
    for t_tuple in tokens:
        t_addr = t_tuple[0].lower()
        price = prices.get(t_addr)
        if price is not None:
            market[t_addr] = {
                "price_usd": price,
                "liquidity_usd": 100000.0,
                "is_carbon_native": True
            }
            
    return market


def calculate_opportunities(chain_id, w3, controller, vortex, multicall, tokens, stablecoins):
    if not tokens:
        return {"trade_l1": [], "trade_l2": [], "execute": []}
        
    ctx = context(vortex)
    ppm = int(vortex.functions.rewardsPPM().call())
    
    target_token = ctx["target_token"]
    final_token = ctx["final_target_token"]
    
    all_tokens = list(tokens)
    active_addresses = {t[0].lower() for t in all_tokens}
    
    chain_name = CHAIN_NAMES.get(chain_id, "ethereum")
    for t_addr in [target_token, final_token]:
        if t_addr.lower() not in active_addresses:
            meta = fetch_token_metadata(w3, t_addr, chain_name)
            all_tokens.append((t_addr, meta["symbol"], meta["decimals"], None, None, None, None, None))
            active_addresses.add(t_addr.lower())
            
    calls1 = []
    token_indices = {}
    call_idx = 0
    for t_tuple in all_tokens:
        t_addr = t_tuple[0]
        token_indices[t_addr] = {}
        checksum_token = Web3.to_checksum_address(t_addr)
        
        calls1.append({
            "target": vortex.address,
            "allowFailure": True,
            "callData": w3.to_bytes(hexstr=vortex.encode_abi("availableTokens", [checksum_token]))
        })
        token_indices[t_addr]["available_idx"] = call_idx
        call_idx += 1
        
        calls1.append({
            "target": vortex.address,
            "allowFailure": True,
            "callData": w3.to_bytes(hexstr=vortex.encode_abi("tradingEnabled", [checksum_token]))
        })
        token_indices[t_addr]["trading_enabled_idx"] = call_idx
        call_idx += 1
        
        calls1.append({
            "target": vortex.address,
            "allowFailure": True,
            "callData": w3.to_bytes(hexstr=vortex.encode_abi("amountAvailableForTrading", [checksum_token]))
        })
        token_indices[t_addr]["amount_available_idx"] = call_idx
        call_idx += 1
        
    print(f"  [~] opportunities: querying available execute and trade inventory from Vortex...")
    try:
        results1 = multicall.functions.aggregate3(calls1).call()
    except Exception:
        results1 = [(False, b"")] * len(calls1)
    
    parsed_tokens = {}
    for t_tuple in all_tokens:
        t_addr = t_tuple[0]
        symbol = t_tuple[1]
        decimals = t_tuple[2]
        idx_info = token_indices[t_addr]
        
        success, data = results1[idx_info["available_idx"]]
        available_execute_raw = decode_result(w3, "uint256", success, data, 0)
        
        success, data = results1[idx_info["trading_enabled_idx"]]
        trading_enabled = decode_result(w3, "bool", success, data, False)
        
        success, data = results1[idx_info["amount_available_idx"]]
        available_trade_raw = decode_result(w3, "uint256", success, data, 0)
        
        parsed_tokens[t_addr] = {
            "symbol": symbol,
            "decimals": decimals,
            "available_execute_raw": available_execute_raw,
            "trading_enabled": trading_enabled,
            "available_trade_raw": available_trade_raw,
        }
        
    calls2 = []
    quote_indices = {}
    call_idx2 = 0
    for t_tuple in all_tokens:
        t_addr = t_tuple[0]
        checksum_token = Web3.to_checksum_address(t_addr)
        cls = classify(checksum_token, ctx)
        t_data = parsed_tokens[t_addr]
        
        if not cls["tradable"] or not t_data["trading_enabled"] or t_data["available_trade_raw"] <= 0:
            t_data["quote_status"] = "SKIP"
            t_data["quote_reason"] = "finalTargetToken" if not cls["tradable"] else ("tradingDisabled" if not t_data["trading_enabled"] else "noInventory")
            continue
            
        calls2.append({
            "target": vortex.address,
            "allowFailure": True,
            "callData": w3.to_bytes(hexstr=vortex.encode_abi("expectedTradeInput", [checksum_token, t_data["available_trade_raw"]]))
        })
        quote_indices[t_addr] = call_idx2
        call_idx2 += 1
        
    results2 = []
    if calls2:
        print(f"  [~] opportunities: simulating Vortex expectedTradeInput for {len(calls2)} tokens...")
        try:
            results2 = multicall.functions.aggregate3(calls2).call()
        except Exception:
            results2 = [(False, b"")] * len(calls2)
            
    for t_tuple in all_tokens:
        t_addr = t_tuple[0]
        t_data = parsed_tokens[t_addr]
        if "quote_status" in t_data:
            continue
            
        if t_addr in quote_indices:
            call_idx = quote_indices[t_addr]
            success, data = results2[call_idx]
            if success and data:
                required_source_raw = w3.codec.decode(["uint256"], data)[0]
                t_data["quote_status"] = "OK"
                t_data["required_source_raw"] = required_source_raw
            else:
                t_data["quote_status"] = "SKIP"
                t_data["quote_reason"] = "quoteError:Revert"
        else:
            t_data["quote_status"] = "SKIP"
            t_data["quote_reason"] = "unknown"
            
    # 3-Layer Pricing System
    # Layer 1: Bybit API
    print(f"  [~] opportunities: querying Bybit prices for {len(all_tokens)} tokens...")
    market = {}
    try:
        bybit_prices = bybit_query(all_tokens)
        print(f"  [+] Bybit resolved {len(bybit_prices)} pricing entries")
        for k, v in bybit_prices.items():
            market[k.lower()] = v
    except Exception as bybit_err:
        print(f"  [-] Bybit query failed: {bybit_err}")
        
    # Layer 2: DexScreener (for tokens not found on Bybit)
    missing_from_bybit = [t for t in all_tokens if t[0].lower() not in market or market[t[0].lower()].get("price_usd") is None]
    if missing_from_bybit:
        print(f"  [~] opportunities: querying DexScreener prices for {len(missing_from_bybit)} tokens...")
        try:
            cfg = load_config()
            ds_prices = dexscreener_query(chain_id, [t[0] for t in missing_from_bybit], cfg["market"]["batch_size"])
            print(f"  [+] DexScreener resolved {len(ds_prices)} pricing entries")
            for k, v in ds_prices.items():
                market[k.lower()] = v
        except Exception as ds_err:
            print(f"  [-] DexScreener query failed: {ds_err}")
            
    # Layer 3: Carbon (for tokens not found on Bybit or DexScreener)
    missing_from_all = [t for t in all_tokens if t[0].lower() not in market or market[t[0].lower()].get("price_usd") is None]
    if missing_from_all:
        print(f"  [~] opportunities: resolving on-chain carbon DEX strategy prices for {len(missing_from_all)} missing tokens...")
        try:
            sdk_market = estimate_carbon_prices(w3, controller, multicall, chain_id, missing_from_all)
            for k, v in sdk_market.items():
                market[k.lower()] = v
        except Exception as carbon_pricing_err:
            print(f"  [-] Carbon on-chain pricing failed for missing tokens: {carbon_pricing_err}")
            
    for t_tuple in all_tokens:
        t_addr = t_tuple[0]
        addr_lower = t_addr.lower()
        if addr_lower not in market or market[addr_lower].get("price_usd") is None:
            fallback_price = estimate_fallback_price(t_addr, all_tokens, market)
            if fallback_price is not None:
                if addr_lower not in market:
                    market[addr_lower] = {}
                market[addr_lower]["price_usd"] = fallback_price
                market[addr_lower]["is_fallback"] = True

    # Pricing post-processing: enforce accurate global prices for standard assets and sync native/wrapped
    print("  [~] opportunities: normalizing and correcting standard token prices...")
    global_prices = fetch_global_prices()
    
    # Sync native and wrapped native prices first
    NATIVE_WRAPPED_MAP = {
        1: "0xC02aaA39b223FE8D0A0e5C4F27ead9083C756Cc2",       # WETH on Ethereum
        1329: "0xE30feDd158A2e3b13e9badaeABaFc5516e95e8C7",    # WSEI on Sei
        239: "0xb63b9f0eb4a6e6f191529d71d4d88cc8900df2c9",     # WTAC on TAC
        42220: "0x471EcE3750Da237f93B8E339c536989b8978a438",   # CELO on Celo
    }
    wrapped_native_addr = NATIVE_WRAPPED_MAP.get(chain_id, "").lower()
    native_addr = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    
    if native_addr in market and market[native_addr].get("price_usd") is not None:
        if wrapped_native_addr:
            if wrapped_native_addr not in market:
                market[wrapped_native_addr] = {}
            market[wrapped_native_addr]["price_usd"] = market[native_addr]["price_usd"]
            market[wrapped_native_addr]["is_corrected"] = True
    elif wrapped_native_addr in market and market[wrapped_native_addr].get("price_usd") is not None:
        if native_addr not in market:
            market[native_addr] = {}
        market[native_addr]["price_usd"] = market[wrapped_native_addr]["price_usd"]
        market[native_addr]["is_corrected"] = True

    for t_tuple in all_tokens:
        t_addr = t_tuple[0].lower()
        symbol = t_tuple[1].upper() if t_tuple[1] else ""
        
        if t_addr not in market:
            market[t_addr] = {}
            
        # 1. Enforce stablecoin price to $1.0
        if symbol in ["USDC", "USDT", "CUSD", "USDC.N", "USDC.E", "USDT.E", "USDT.N"]:
            market[t_addr]["price_usd"] = 1.0
            market[t_addr]["is_corrected"] = True
            
        # 2. Enforce ETH/WETH price to global mainnet ETH price
        elif symbol in ["WETH", "ETH", "WETH.E", "ETH.E"] and symbol not in ["TAC", "WTAC", "SEI", "WSEI", "CELO", "WCELO"]:
            market[t_addr]["price_usd"] = global_prices["eth"]
            market[t_addr]["is_corrected"] = True
            
        # 3. Enforce BTC/WBTC price to global mainnet BTC price
        elif symbol in ["WBTC", "BTC", "WBTC.E"]:
            market[t_addr]["price_usd"] = global_prices["btc"]
            market[t_addr]["is_corrected"] = True

    execute_list = []
    trade_l1_list = []
    trade_l2_list = []
    
    from carbon_tracker.analysis.scanner import execute_row_multicall, trade_row_multicall
    for t_tuple in all_tokens:
        t_addr = t_tuple[0]
        symbol = t_tuple[1]
        decimals = t_tuple[2]
        
        checksum_token = Web3.to_checksum_address(t_addr)
        t_data = parsed_tokens[t_addr]
        meta = {
            "address": t_addr,
            "symbol": symbol,
            "decimals": decimals,
            "native": (t_addr.lower() == "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee")
        }
        
        ex_row = execute_row_multicall(t_addr, meta, t_data["available_execute_raw"], ppm, market)
        if market.get(t_addr.lower(), {}).get("is_fallback"):
            ex_row["symbol"] = f"{symbol} ⚡"
        execute_list.append(ex_row)
        
        cls = classify(checksum_token, ctx)
        if t_data["quote_status"] == "SKIP" or not cls["source"] or not cls["target"]:
            tr_row = {
                "token": t_addr,
                "symbol": symbol,
                "level": cls["level"],
                "status": "SKIP",
                "reason": t_data.get("quote_reason", "SKIP"),
                "available": 0
            }
        else:
            src_meta = next(({"symbol": t[1], "decimals": t[2], "address": t[0]} for t in all_tokens if t[0].lower() == cls["source"].lower()), None)
            if not src_meta:
                src_meta = {"symbol": cls["source"][:6], "decimals": 18, "address": cls["source"]}
                
            tgt_meta = next(({"symbol": t[1], "decimals": t[2], "address": t[0]} for t in all_tokens if t[0].lower() == cls["target"].lower()), None)
            if not tgt_meta:
                tgt_meta = {"symbol": cls["target"][:6], "decimals": 18, "address": cls["target"]}
                
            tr_row = trade_row_multicall(t_addr, meta, src_meta, tgt_meta, cls, t_data, ctx, market)
            
        if market.get(t_addr.lower(), {}).get("is_fallback"):
            tr_row["symbol"] = f"{symbol} ⚡"
            
        if cls["level"] == 2:
            trade_l2_list.append(tr_row)
        elif cls["level"] == 1:
            trade_l1_list.append(tr_row)
            
    return {"trade_l1": trade_l1_list, "trade_l2": trade_l2_list, "execute": execute_list}


def main():
    cfg = load_config()
    
    target_chains = cfg["chains"]
    
    # Parse CLI flags/arguments
    args = sys.argv[1:]
    skip_log_sync = False
    if "--fast" in args or "--skip-log-sync" in args:
        skip_log_sync = True
        args = [arg for arg in args if arg not in ("--fast", "--skip-log-sync")]

    force_rescan = False
    if "--force" in args:
        force_rescan = True
        args = [arg for arg in args if arg != "--force"]

    if args:
        requested = [arg.lower().strip() for arg in args]
        filtered = {name: c for name, c in cfg["chains"].items() if name in requested}
        if not filtered:
            available = ", ".join(cfg["chains"].keys())
            print(f"[-] Error: None of the requested chains {requested} are configured. Available: {available}")
            sys.exit(1)
        target_chains = filtered
        print(f"[+] Syncing only: {', '.join(target_chains.keys())}")
        
    db_path = os.getenv("DB_PATH", str(ROOT/"data/tracker.db"))
    from .storage.db import connect as db_connect, upsert_token, get_scan_progress, save_scan_progress, snapshot
    db = db_connect(db_path)
    
    for name, c in target_chains.items():
        rpc_url = os.getenv(c["rpc_env"], "").strip()
        if not rpc_url:
            rpc_url = c.get("public_rpc", "").strip()
            
        if not rpc_url:
            print(f"[-] Skipping chain {name}: RPC env var {c['rpc_env']} not set and no public fallback configured.")
            continue
            
        print(f"\n[+] Connecting to {name} EVM via {rpc_url}...")
        try:
            w3 = connect(rpc_url)
            controller = contract(w3, c["carbon_controller"], "CarbonController.json")
            vortex = contract(w3, c["carbon_vortex"], "CarbonVortex.json")
            latest = w3.eth.block_number
        except Exception as e:
            print(f"[-] Connection failed for {name} on {rpc_url}: {e}. Skipping this chain.")
            continue
            
        if not skip_log_sync:
            # Determine target scan range from config/env
            start_block_env = os.getenv("START_BLOCK", "").strip()
            lookback_start = 0
            if start_block_env:
                try:
                    lookback_start = int(start_block_env)
                except ValueError:
                    pass
                    
            if lookback_start <= 0:
                lookback_hours = float(os.getenv("LOOKBACK_HOURS", "24"))
                default_bt = float(c.get("average_block_time", 12.0))
                estimated_lookback = estimate_blocks_for_duration(w3, int(lookback_hours * 3600), default_bt)
                lookback_start = max(0, latest - estimated_lookback)
                print(f"[+] LOOKBACK_HOURS={lookback_hours} -> Estimated lookback for {name}: {estimated_lookback} blocks (Start block: {lookback_start})")
            else:
                print(f"[+] Using configured START_BLOCK={lookback_start} for {name}")

            # Get scan progress from DB
            progress = None if force_rescan else get_scan_progress(db, c["chain_id"])
            if progress:
                first_scanned = progress.get("first_scanned_block")
                last_scanned = progress.get("last_scanned_block")
                if first_scanned is None:
                    first_scanned = last_scanned
            else:
                first_scanned = None
                last_scanned = None

            # Split scan into forward updates and backward history gaps
            ranges_to_scan = []
            if last_scanned is None:
                # First scan: query full range
                ranges_to_scan.append((lookback_start, latest, False))
            else:
                # Forward range (new blocks)
                if last_scanned < latest:
                    ranges_to_scan.append((last_scanned + 1, latest, False))
                # Backward range (historical backfill)
                if lookback_start < first_scanned:
                    ranges_to_scan.append((lookback_start, first_scanned - 1, True))

            # Run crawler for all ranges
            block_chunk = int(os.getenv("BLOCK_CHUNK", str(cfg["scanner"]["block_chunk"])))
            tokens_info = {}
            
            for r_start, r_end, is_backfill in ranges_to_scan:
                if r_start > r_end:
                    continue
                desc = "backward backfill" if is_backfill else "forward sync"
                try:
                    print(f"[+] Syncing logs ({desc}) on {name} from block {r_start} to {r_end}...")
                    found_range = discover_fee_tokens(controller, r_start, r_end, block_chunk)
                    
                    for token, info in found_range.items():
                        if token in tokens_info:
                            tokens_info[token]["first_seen_block"] = min(tokens_info[token]["first_seen_block"], info["first_seen_block"])
                            tokens_info[token]["last_seen_block"] = max(tokens_info[token]["last_seen_block"], info["last_seen_block"])
                            tokens_info[token]["events"] += info["events"]
                            if info["last_seen_block"] >= tokens_info[token]["last_seen_block"]:
                                tokens_info[token]["last_fee_raw"] = info["last_fee_raw"]
                                tokens_info[token]["last_trade_source"] = info.get("last_trade_source")
                                tokens_info[token]["last_trade_target"] = info.get("last_trade_target")
                                tokens_info[token]["last_trade_source_amount"] = info.get("last_trade_source_amount")
                                tokens_info[token]["last_trade_target_amount"] = info.get("last_trade_target_amount")
                                tokens_info[token]["last_trade_block"] = info.get("last_trade_block")
                        else:
                            tokens_info[token] = info
                except Exception as e:
                    print(f"[-] Failed to scan logs range [{r_start}, {r_end}] on {name}: {e}. Skipping range.")

            if tokens_info:
                print(f"[+] Found {len(tokens_info)} fee tokens total in scan range. Checking metadata...")
                missing_tokens = []
                token_metas = {}
                for token in tokens_info.keys():
                    exist = db.execute("SELECT symbol, decimals FROM token_registry WHERE chain_id=? AND token_address=?", (c["chain_id"], token)).fetchone()
                    if exist:
                        token_metas[token.lower()] = {"symbol": exist[0], "decimals": exist[1]}
                    else:
                        missing_tokens.append(token)
                        
                if missing_tokens:
                    print(f"  [~] Batch querying ERC20 metadata for {len(missing_tokens)} new tokens via Multicall3...")
                    batch_metas = fetch_tokens_metadata_batched(w3, missing_tokens, name, MULTICALL_ADDRESS)
                    token_metas.update(batch_metas)
                    
                for token, info in tokens_info.items():
                    try:
                        meta = token_metas.get(token.lower(), {"symbol": token[:6], "decimals": 18})
                        upsert_token(db, c["chain_id"], token, meta, info)
                    except Exception as upsert_err:
                        print(f"  [-] Failed to upsert token {token}: {upsert_err}")
                        
            # Save progress
            new_first = min(lookback_start, first_scanned) if first_scanned is not None else lookback_start
            new_last = max(latest, last_scanned) if last_scanned is not None else latest
            save_scan_progress(db, c["chain_id"], new_first, new_last)
            db.commit()
            print(f"[+] {name}: Sync successful. Progress tracked range: [{new_first}, {new_last}]")
        else:
            print(f"[+] Skipping log crawler sync for {name} (--fast active)")
            
        # Opportunity Multicall Scan
        # Load all registered tokens for this chain from database
        cursor = db.cursor()
        cursor.execute("""
            SELECT token_address, symbol, decimals, 
                   last_trade_source, last_trade_target, 
                   last_trade_source_amount, last_trade_target_amount, 
                   last_trade_block 
            FROM token_registry WHERE chain_id=?
        """, (c["chain_id"],))
        tokens = cursor.fetchall()
        
        if not tokens:
            print(f"[-] No tokens registered in database for {name}. Skipping opportunity scan.")
            continue
            
        multicall = w3.eth.contract(address=Web3.to_checksum_address(MULTICALL_ADDRESS), abi=MULTICALL_ABI)
        
        stables = STABLECOINS_MAP.get(c["chain_id"], [])
        
        try:
            print(f"[+] Calculating opportunities live for {len(tokens)} tokens on {name}...")
            opportunities = calculate_opportunities(
                c["chain_id"], w3, controller, vortex, multicall, tokens, stables
            )
            
            # Save snapshots to database
            ts = int(time.time())
            
            # Save L1 trades
            for row in opportunities["trade_l1"]:
                snapshot(db, ts, c["chain_id"], "trade", 1, row["token"], row)
            # Save L2 trades
            for row in opportunities["trade_l2"]:
                snapshot(db, ts, c["chain_id"], "trade", 2, row["token"], row)
            # Save execute
            for row in opportunities["execute"]:
                snapshot(db, ts, c["chain_id"], "execute", None, row["token"], row)
                
            db.commit()
            print(f"[+] Saved opportunities snapshots for {name} to database.")
        except Exception as opportunity_err:
            print(f"[-] Failed to calculate opportunities for {name}: {opportunity_err}")


if __name__ == "__main__":
    main()
