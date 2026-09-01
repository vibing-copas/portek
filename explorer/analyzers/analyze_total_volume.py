#!/usr/bin/env python3
import os
import json
import sqlite3

TOTALS_FILE = os.path.join("data", "vortex_eth_trade_totals.json")
DB_PATH = os.path.join("data", "tracker.db")

def analyze_volume():
    if not os.path.exists(TOTALS_FILE):
        print(f"[-] File {TOTALS_FILE} not found.")
        return

    with open(TOTALS_FILE, "r", encoding="utf-8") as f:
        totals_data = json.load(f)

    total_events = sum(t["trade_count"] for t in totals_data)
    total_usd = sum(t.get("volume_usd", 0.0) for t in totals_data)

    l1_tokens = [t for t in totals_data if t["level"] == 1]
    l2_tokens = [t for t in totals_data if t["level"] == 2]

    l1_usd = sum(t.get("volume_usd", 0.0) for t in l1_tokens)
    l1_events = sum(t["trade_count"] for t in l1_tokens)
    l1_source_eth = sum(t["total_source_amount"] for t in l1_tokens)

    l2_usd = sum(t.get("volume_usd", 0.0) for t in l2_tokens)
    l2_events = sum(t["trade_count"] for t in l2_tokens)
    l2_source_eth = sum(t["total_source_amount"] for t in l2_tokens)
    l2_target_bnt = sum(t["total_amount"] for t in l2_tokens)

    sorted_by_usd = sorted(totals_data, key=lambda x: x.get("volume_usd", 0.0), reverse=True)

    print("=" * 80)
    print("                VORTEX ETHEREUM - TOTAL VOLUME ANALYTICS                ")
    print("=" * 80)
    print(f"📊 Total Scanned Trade Events : {total_events:,} events")
    print(f"💎 Total Unique Tokens Traded : {len(totals_data)} tokens")
    print(f"💵 Overall Total Volume ($ USD) : ${total_usd:,.2f} USD")
    print("-" * 80)

    print("\n🔹 BREAKDOWN BY TRADE LEVEL:")
    print(f"  • Level 1 (Fee Token → ETH):")
    print(f"    - Unique Tokens : {len(l1_tokens)} tokens")
    print(f"    - Event Count   : {l1_events} trades ({ (l1_events/total_events)*100:.1f}% of all events)")
    print(f"    - Total Volume  : ${l1_usd:,.2f} USD ({ (l1_usd/total_usd)*100:.1f}% of total volume)")
    print(f"    - Total ETH Recv: {l1_source_eth:,.4f} ETH")

    print(f"\n  • Level 2 (ETH → BNT Final Burn):")
    print(f"    - Unique Tokens : {len(l2_tokens)} tokens (ETH/WETH)")
    print(f"    - Event Count   : {l2_events} trades ({ (l2_events/total_events)*100:.1f}% of all events)")
    print(f"    - Total Volume  : ${l2_usd:,.2f} USD ({ (l2_usd/total_usd)*100:.1f}% of total volume)")
    print(f"    - Total ETH Paid: {l2_source_eth:,.4f} ETH")
    print(f"    - Total BNT Recv: {l2_target_bnt:,.2f} BNT")
    print("-" * 80)

    print("\n🏆 TOP 15 TOKENS BY TOTAL VOLUME ($ USD):")
    print(f"{'#':<3} | {'SYMBOL':<10} | {'LEVEL':<6} | {'TRADES':<6} | {'VOLUME ($ USD)':<18} | {'% TOTAL':<8} | {'TARGET RELEASED':<20}")
    print("-" * 85)
    for idx, t in enumerate(sorted_by_usd[:15], 1):
        usd_val = t.get("volume_usd", 0.0)
        pct = (usd_val / total_usd) * 100 if total_usd > 0 else 0
        lvl_str = f"L{t['level']}"
        target_str = f"{t['total_amount']:,.2f} {t['symbol']}"
        print(f"{idx:<3} | {t['symbol']:<10} | {lvl_str:<6} | {t['trade_count']:<6} | ${usd_val:>16,.2f} | {pct:>6.2f}% | {target_str:<20}")

    print("-" * 85)

if __name__ == "__main__":
    analyze_volume()
