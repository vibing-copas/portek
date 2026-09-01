#!/usr/bin/env python3
import os
import json
import requests
import dotenv
from datetime import datetime

dotenv.load_dotenv()

RPC_URL = os.getenv("ETH_RPC_URL", "https://rpc.ankr.com/eth")
LOGS_FILE = os.path.join("data", "vortex_eth_logs.json")
METADATA_FILE = os.path.join("data", "token_metadata.json")
PRICES_FILE = os.path.join("data", "token_prices_usd.json")
OUTPUT_JSON = os.path.join("data", "vortex_eth_trade_totals.json")
OUTPUT_CSV = os.path.join("data", "vortex_eth_trade_totals.csv")

ETH_ADDR = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
WETH_ADDR = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
BNT_ADDR = "0x1f573d6fb3f13d689ff844b4ce37794d79a7ff1c"

def decode_topic_address(topic_hex: str) -> str:
    if not topic_hex or not isinstance(topic_hex, str):
        return ""
    clean = topic_hex.lower()
    if clean.startswith("0x"):
        clean = clean[2:]
    if len(clean) >= 40:
        return "0x" + clean[-40:]
    return "0x" + clean

def main():
    if not os.path.exists(LOGS_FILE):
        print(f"Error: {LOGS_FILE} not found.")
        return

    with open(LOGS_FILE, "r", encoding="utf-8") as f:
        logs = json.load(f)

    print(f"Loaded {len(logs)} logs from {LOGS_FILE}.")

    # Load metadata
    metadata = {}
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            metadata = json.load(f)

    # Load USD prices
    prices_map = {}
    if os.path.exists(PRICES_FILE):
        with open(PRICES_FILE, "r", encoding="utf-8") as f:
            prices_map = json.load(f)

    eth_usd_price = prices_map.get(WETH_ADDR, prices_map.get(ETH_ADDR, 2600.0))
    if eth_usd_price <= 0:
        eth_usd_price = 2600.0

    # Process all trade logs into detailed individual trade records & token summaries
    token_trades = {}
    token_stats = {}

    for log in logs:
        topics = log.get("topics", [])
        data_str = log.get("data", "")
        
        if len(topics) <= 2 or not topics[2] or not data_str or len(data_str) < 130:
            continue
            
        caller = decode_topic_address(topics[1])
        token_addr = decode_topic_address(topics[2])
        
        # Word 1: sourceAmount (first 64 hex chars after 0x)
        source_hex = data_str[2:66]
        source_raw = int(source_hex, 16)
        
        # Word 2: targetAmount (last 64 hex chars of data)
        target_hex = data_str[-64:]
        target_raw = int(target_hex, 16)
        
        # Parse blockNumber and timestamp
        block_num = int(log.get("blockNumber", "0x0"), 16)
        timestamp_sec = int(log.get("timeStamp", "0x0"), 16)
        dt_str = datetime.utcfromtimestamp(timestamp_sec).strftime("%Y-%m-%d %H:%M:%S UTC") if timestamp_sec > 0 else "N/A"
        tx_hash = log.get("transactionHash", "")
        
        # Token metadata
        token_meta = metadata.get(token_addr, {"symbol": f"{token_addr[:6]}...", "decimals": 18})
        decimals = token_meta.get("decimals", 18)
        symbol = token_meta.get("symbol", f"{token_addr[:6]}...")
        
        # Rule classification:
        # Level 2 if token_addr is ETH or WETH (targetToken -> finalTargetToken: ETH -> BNT)
        # Level 1 if token_addr is any other token (feeToken -> targetToken: Token -> ETH)
        if token_addr.lower() in (ETH_ADDR, WETH_ADDR):
            level = 2
            source_symbol = "BNT"
            source_decimals = 18
            pair_name = "ETH → BNT"
        else:
            level = 1
            source_symbol = "ETH"
            source_decimals = 18
            pair_name = f"{symbol} → ETH"

        target_formatted = target_raw / (10 ** decimals)
        source_formatted = source_raw / (10 ** source_decimals)
        
        # Unit price
        unit_price = (source_formatted / target_formatted) if target_formatted > 0 else 0.0
        
        # USD value of trade
        token_price_usd = prices_map.get(token_addr.lower(), 0.0)
        if token_price_usd > 0:
            trade_usd_val = target_formatted * token_price_usd
        else:
            # Fallback to source ETH value
            trade_usd_val = source_formatted * eth_usd_price

        trade_record = {
            "tx_hash": tx_hash,
            "block_number": block_num,
            "timestamp": dt_str,
            "timestamp_raw": timestamp_sec,
            "caller": caller,
            "level": level,
            "pair_name": pair_name,
            "source_symbol": source_symbol,
            "source_raw": str(source_raw),
            "source_formatted": source_formatted,
            "target_raw": str(target_raw),
            "target_formatted": target_formatted,
            "unit_price": unit_price,
            "usd_value": trade_usd_val
        }
        
        if token_addr not in token_trades:
            token_trades[token_addr] = []
            token_stats[token_addr] = {
                "address": token_addr,
                "symbol": symbol,
                "decimals": decimals,
                "level": level,
                "pair_name": pair_name,
                "price_usd": token_price_usd,
                "total_target_raw": 0,
                "total_source_raw": 0,
                "total_volume_usd": 0.0,
                "trade_count": 0,
                "trades": []
            }
            
        token_trades[token_addr].append(trade_record)
        token_stats[token_addr]["trades"].append(trade_record)
        token_stats[token_addr]["total_target_raw"] += target_raw
        token_stats[token_addr]["total_source_raw"] += source_raw
        token_stats[token_addr]["total_volume_usd"] += trade_usd_val
        token_stats[token_addr]["trade_count"] += 1

    # Format summary list
    summary_list = []
    for token_addr, stats in token_stats.items():
        dec = stats["decimals"]
        total_target_formatted = stats["total_target_raw"] / (10 ** dec)
        total_source_formatted = stats["total_source_raw"] / (10 ** 18)
        
        avg_unit_price = (total_source_formatted / total_target_formatted) if total_target_formatted > 0 else 0.0
        
        summary_list.append({
            "symbol": stats["symbol"],
            "total_amount": total_target_formatted,
            "total_source_amount": total_source_formatted,
            "source_symbol": "BNT" if stats["level"] == 2 else "ETH",
            "volume_usd": stats["total_volume_usd"],
            "price_usd": stats["price_usd"],
            "avg_unit_price": avg_unit_price,
            "total_raw": str(stats["total_target_raw"]),
            "decimals": dec,
            "level": stats["level"],
            "pair_name": stats["pair_name"],
            "trade_count": stats["trade_count"],
            "address": token_addr,
            "trades": stats["trades"]
        })

    # Sort default by volume_usd descending
    summary_list.sort(key=lambda x: x["volume_usd"], reverse=True)

    # Save JSON with detailed trades and USD volume
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(summary_list, f, indent=2)
    print(f"Saved detailed JSON trade totals & history to {OUTPUT_JSON}")

    # Save CSV summary
    with open(OUTPUT_CSV, "w", encoding="utf-8") as f:
        f.write("Symbol,Volume USD,Total Target Amount,Total Source Paid,Source Symbol,Price USD,Level,Trade Count,Decimals,Address\n")
        for item in summary_list:
            f.write(f'"{item["symbol"]}",{item["volume_usd"]:.2f},{item["total_amount"]},{item["total_source_amount"]},"{item["source_symbol"]}",{item["price_usd"]},{item["level"]},{item["trade_count"]},{item["decimals"]},"{item["address"]}"\n')
    print(f"Saved CSV trade totals to {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
