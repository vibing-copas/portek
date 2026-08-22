import os
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from web3 import Web3
import requests
from requests.adapters import HTTPAdapter

_thread_local = threading.local()

def get_thread_w3(rpc_url):
    """Retrieve or create a thread-local Web3 client with connection pooling configured."""
    if not hasattr(_thread_local, "w3"):
        if rpc_url.startswith("ws://") or rpc_url.startswith("wss://"):
            _thread_local.w3 = Web3(Web3.LegacyWebSocketProvider(rpc_url))
        else:
            session = requests.Session()
            # Each thread requires 1 active connection.
            adapter = HTTPAdapter(pool_connections=1, pool_maxsize=1)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            
            _thread_local.w3 = Web3(Web3.HTTPProvider(rpc_url, session=session, request_kwargs={
                "timeout": 30
            }))
    return _thread_local.w3


def get_logs_with_backoff(event, start_block, end_block, max_retries=5):
    """Fetch logs with exponential backoff and jitter on request failure."""
    backoff = 1.0
    for attempt in range(max_retries):
        try:
            return event.get_logs(from_block=start_block, to_block=end_block)
        except Exception as e:
            err_str = str(e).lower()
            if hasattr(e, "response") and e.response is not None:
                try:
                    err_str += " " + e.response.text.lower()
                except Exception:
                    pass
            
            # Identify earliest block restriction error to raise immediately
            is_earliest_block_error = any(msg in err_str for msg in [
                "earliest available block", "earliest block", "before earliest"
            ])
            if is_earliest_block_error:
                raise ValueError(err_str) from e

            # Identify size limits or chunk error messages commonly returned by RPC providers
            is_limit_error = any(msg in err_str for msg in [
                "more than", "limit exceeded", "exceed", "too many", "size limit", "chunk", 
                "parse error", "too large", "range", "-32062", "-32005", "-32600", "upgrade", "free tier"
            ])
            if is_limit_error:
                # Raise limit error immediately so that the caller can bisect the chunk
                raise ValueError("LOG_LIMIT_EXCEEDED") from e
            
            if attempt == max_retries - 1:
                raise
            
            sleep_time = backoff * (0.8 + random.random() * 0.4)
            print(f"[-] RPC error in range [{start_block}, {end_block}]: {e}. Retrying in {sleep_time:.2f}s... (Attempt {attempt+1}/{max_retries})")
            time.sleep(sleep_time)
            backoff *= 2.0


def fetch_range(rpc_url, contract_address, contract_abi, start_block, end_block, min_chunk_size=10, state=None):
    """Retrieve logs for a block range. Bisect range recursively if size limits are hit."""
    if state is not None:
        with state["lock"]:
            max_allowed_chunk = state["current_chunk_size"]
        
        range_size = end_block - start_block + 1
        if range_size > max_allowed_chunk:
            logs = []
            sub_start = start_block
            while sub_start <= end_block:
                sub_end = min(sub_start + max_allowed_chunk - 1, end_block)
                logs.extend(fetch_range(rpc_url, contract_address, contract_abi, sub_start, sub_end, min_chunk_size, state))
                sub_start = sub_end + 1
            return logs

    w3 = get_thread_w3(rpc_url)
    contract = w3.eth.contract(address=contract_address, abi=contract_abi)
    event = contract.events.TokensTraded()
    
    try:
        return get_logs_with_backoff(event, start_block, end_block)
    except ValueError as ve:
        if str(ve) == "LOG_LIMIT_EXCEEDED":
            current_range = end_block - start_block + 1
            if current_range <= min_chunk_size:
                raise
            
            # Bisect the range in half
            new_chunk_size = current_range // 2
            if state is not None:
                with state["lock"]:
                    if new_chunk_size < state["current_chunk_size"]:
                        state["current_chunk_size"] = max(min_chunk_size, new_chunk_size)
                        print(f"[-] RPC log limit hit. Adapting initial chunk size down to {state['current_chunk_size']} blocks.")
            
            mid = start_block + (end_block - start_block) // 2
            print(f"[-] RPC log limit exceeded for block range [{start_block}, {end_block}]: {ve.__cause__}. Bisecting range in half...")
            logs_left = fetch_range(rpc_url, contract_address, contract_abi, start_block, mid, min_chunk_size, state)
            logs_right = fetch_range(rpc_url, contract_address, contract_abi, mid + 1, end_block, min_chunk_size, state)
            return logs_left + logs_right
        else:
            raise


def discover_fee_tokens_sequential(controller, from_block, to_block, chunk=10000, _orig_from=None):
    """Fallback sequential fee token discovery if the provider doesn't support endpoint_uri lookup."""
    if _orig_from is None:
        _orig_from = from_block
    event = controller.events.TokensTraded()
    found = {}
    start = from_block
    total_range = to_block - _orig_from + 1
    
    try:
        while start <= to_block:
            end = min(start + chunk - 1, to_block)
            try:
                logs = event.get_logs(from_block=start, to_block=end)
            except Exception:
                if chunk <= 500:
                    raise
                new_chunk = max(500, chunk // 2)
                print(f"[-] RPC log limit exceeded for chunk size {chunk}. Reducing chunk size to {new_chunk}...")
                rem = discover_fee_tokens_sequential(controller, start, to_block, new_chunk, _orig_from)
                for token, info in rem.items():
                    if token in found:
                        found[token]["first_seen_block"] = min(found[token]["first_seen_block"], info["first_seen_block"])
                        found[token]["last_seen_block"] = max(found[token]["last_seen_block"], info["last_seen_block"])
                        found[token]["events"] += info["events"]
                        if info["last_seen_block"] >= found[token]["last_seen_block"]:
                            found[token]["last_fee_raw"] = info["last_fee_raw"]
                            found[token]["last_trade_source"] = info.get("last_trade_source")
                            found[token]["last_trade_target"] = info.get("last_trade_target")
                            found[token]["last_trade_source_amount"] = info.get("last_trade_source_amount")
                            found[token]["last_trade_target_amount"] = info.get("last_trade_target_amount")
                            found[token]["last_trade_block"] = info.get("last_trade_block")
                    else:
                        found[token] = info
                return found
            for log in logs:
                a = log["args"]
                fee = int(a["tradingFeeAmount"])
                if fee == 0: continue
                fee_token = a["targetToken"] if bool(a["byTargetAmount"]) else a["sourceToken"]
                fee_token = Web3.to_checksum_address(fee_token)
                
                source_token = Web3.to_checksum_address(a["sourceToken"])
                target_token = Web3.to_checksum_address(a["targetToken"])
                source_amount = int(a["sourceAmount"])
                target_amount = int(a["targetAmount"])
                
                if fee_token not in found:
                    found[fee_token] = {
                        "first_seen_block": log["blockNumber"],
                        "last_seen_block": log["blockNumber"],
                        "events": 1,
                        "last_fee_raw": fee,
                        "last_trade_source": source_token,
                        "last_trade_target": target_token,
                        "last_trade_source_amount": str(source_amount),
                        "last_trade_target_amount": str(target_amount),
                        "last_trade_block": log["blockNumber"]
                    }
                else:
                    info = found[fee_token]
                    info["first_seen_block"] = min(info["first_seen_block"], log["blockNumber"])
                    info["last_seen_block"] = max(info["last_seen_block"], log["blockNumber"])
                    info["events"] += 1
                    if log["blockNumber"] >= info["last_seen_block"]:
                        info["last_fee_raw"] = fee
                        info["last_trade_source"] = source_token
                        info["last_trade_target"] = target_token
                        info["last_trade_source_amount"] = str(source_amount)
                        info["last_trade_target_amount"] = str(target_amount)
                        info["last_trade_block"] = log["blockNumber"]
            progress = (end - _orig_from + 1) / total_range * 100 if total_range > 0 else 100.0
            print(f"[+] Scanned blocks {start} to {end} ({progress:.2f}%) | Found {len(found)} fee tokens | Chunk size: {chunk}")
            start = end + 1
    except Exception as exc:
        err_str = str(exc).lower()
        if hasattr(exc, "response") and exc.response is not None:
            try:
                err_str += " " + exc.response.text.lower()
            except Exception:
                pass
        if "earliest available block" in err_str or "earliest block" in err_str:
            import re
            match = re.search(r"(?:earliest available block|earliest block)(?:\s+is)?\s+(\d+)", err_str)
            if match:
                earliest_block = int(match.group(1))
                safe_start = earliest_block + 500
                if safe_start > from_block and safe_start < to_block:
                    print(f"[-] RPC node restricts historical logs. Earliest available block is {earliest_block}. Adjusting scan range with safety buffer to {safe_start}...")
                    return discover_fee_tokens_sequential(controller, safe_start, to_block, chunk, _orig_from)
        raise exc
        
    return found


def discover_fee_tokens(controller, from_block, to_block, chunk=10000, _orig_from=None):
    """Discover the token denomination of Carbon's trading fee from TokensTraded in parallel."""
    if _orig_from is None:
        _orig_from = from_block
        
    rpc_url = getattr(controller.w3.provider, "endpoint_uri", None)
    if not rpc_url:
        print("[-] Warning: controller.w3.provider has no endpoint_uri. Falling back to sequential crawling.")
        return discover_fee_tokens_sequential(controller, from_block, to_block, chunk, _orig_from)

    contract_address = controller.address
    contract_abi = controller.abi

    # Generate initial chunk ranges
    chunks = []
    start = from_block
    while start <= to_block:
        end = min(start + chunk - 1, to_block)
        chunks.append((start, end))
        start = end + 1

    if not chunks:
        return {}

    max_workers = int(os.getenv("CRAWLER_MAX_WORKERS", "8"))
    min_chunk = int(os.getenv("CRAWLER_MIN_CHUNK_SIZE", "10"))
    
    found = {}
    lock = threading.Lock()
    processed_chunks = 0
    total_chunks = len(chunks)
    
    # State for dynamic chunk size adaptation across threads
    state = {
        "current_chunk_size": chunk,
        "lock": threading.Lock()
    }
    
    print(f"[+] Starting concurrent crawler ({max_workers} threads) for {total_chunks} chunks...")

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    fetch_range, 
                    rpc_url, 
                    contract_address, 
                    contract_abi, 
                    c_start, 
                    c_end, 
                    min_chunk,
                    state
                ): (c_start, c_end) for c_start, c_end in chunks
            }
            
            for future in as_completed(futures):
                c_start, c_end = futures[future]
                try:
                    logs = future.result()
                    local_found = {}
                    for log in logs:
                        a = log["args"]
                        fee = int(a["tradingFeeAmount"])
                        if fee == 0: 
                            continue
                        fee_token = a["targetToken"] if bool(a["byTargetAmount"]) else a["sourceToken"]
                        fee_token = Web3.to_checksum_address(fee_token)
                        
                        source_token = Web3.to_checksum_address(a["sourceToken"])
                        target_token = Web3.to_checksum_address(a["targetToken"])
                        source_amount = int(a["sourceAmount"])
                        target_amount = int(a["targetAmount"])
                        
                        if fee_token not in local_found:
                            local_found[fee_token] = {
                                "first_seen_block": log["blockNumber"],
                                "last_seen_block": log["blockNumber"],
                                "events": 1,
                                "last_fee_raw": fee,
                                "last_trade_source": source_token,
                                "last_trade_target": target_token,
                                "last_trade_source_amount": str(source_amount),
                                "last_trade_target_amount": str(target_amount),
                                "last_trade_block": log["blockNumber"]
                            }
                        else:
                            info = local_found[fee_token]
                            info["first_seen_block"] = min(info["first_seen_block"], log["blockNumber"])
                            info["last_seen_block"] = max(info["last_seen_block"], log["blockNumber"])
                            info["events"] += 1
                            if log["blockNumber"] >= info["last_seen_block"]:
                                info["last_fee_raw"] = fee
                                info["last_trade_source"] = source_token
                                info["last_trade_target"] = target_token
                                info["last_trade_source_amount"] = str(source_amount)
                                info["last_trade_target_amount"] = str(target_amount)
                                info["last_trade_block"] = log["blockNumber"]

                    with lock:
                        for token, info in local_found.items():
                            if token in found:
                                found[token]["first_seen_block"] = min(found[token]["first_seen_block"], info["first_seen_block"])
                                found[token]["last_seen_block"] = max(found[token]["last_seen_block"], info["last_seen_block"])
                                found[token]["events"] += info["events"]
                                if info["last_seen_block"] >= found[token]["last_seen_block"]:
                                    found[token]["last_fee_raw"] = info["last_fee_raw"]
                                    found[token]["last_trade_source"] = info.get("last_trade_source")
                                    found[token]["last_trade_target"] = info.get("last_trade_target")
                                    found[token]["last_trade_source_amount"] = info.get("last_trade_source_amount")
                                    found[token]["last_trade_target_amount"] = info.get("last_trade_target_amount")
                                    found[token]["last_trade_block"] = info.get("last_trade_block")
                            else:
                                found[token] = info
                    
                    processed_chunks += 1
                    progress = (processed_chunks / total_chunks) * 100
                    print(f"[+] Scanned blocks {c_start} to {c_end} ({progress:.2f}%) | Found {len(found)} fee tokens")
                except Exception as exc:
                    print(f"[-] Error scanning block range [{c_start}, {c_end}]: {exc}")
                    raise exc
    except Exception as exc:
        err_str = str(exc).lower()
        if hasattr(exc, "response") and exc.response is not None:
            try:
                err_str += " " + exc.response.text.lower()
            except Exception:
                pass
        
        if "earliest available block" in err_str or "earliest block" in err_str:
            import re
            match = re.search(r"(?:earliest available block|earliest block)(?:\s+is)?\s+(\d+)", err_str)
            if match:
                earliest_block = int(match.group(1))
                safe_start = earliest_block + 500
                if safe_start > from_block and safe_start < to_block:
                    print(f"[-] RPC node restricts historical logs. Earliest available block is {earliest_block}. Adjusting scan range with safety buffer to {safe_start}...")
                    return discover_fee_tokens(controller, safe_start, to_block, chunk, _orig_from)
        raise exc
                    
    return found

