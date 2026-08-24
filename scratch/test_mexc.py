import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from spot.mexc_spot_v3 import mexc_market

def main():
    market = mexc_market()
    
    print("1. Testing Ping...")
    try:
        ping_res = market.get_ping()
        print(f"Ping Response: {ping_res}")
    except Exception as e:
        print(f"Ping failed: {e}")
        
    print("\n2. Testing Server Time...")
    try:
        time_res = market.get_timestamp()
        print(f"Server Time Response: {time_res}")
    except Exception as e:
        print(f"Server Time failed: {e}")

    print("\n3. Testing Exchange Info for BTCUSDT...")
    try:
        info = market.get_exchangeInfo({"symbol": "BTCUSDT"})
        # Print a short snippet of exchange info
        if "symbols" in info and len(info["symbols"]) > 0:
            sym_info = info["symbols"][0]
            print(f"Symbol: {sym_info.get('symbol')}, Status: {sym_info.get('status')}")
        else:
            print(info)
    except Exception as e:
        print(f"Exchange Info failed: {e}")

    print("\n4. Testing Current Average Price for BTCUSDT (Signed request)...")
    try:
        avg_price = market.get_avgprice({"symbol": "BTCUSDT"})
        print(f"Average Price Response: {avg_price}")
    except Exception as e:
        print(f"Average Price failed: {e}")

if __name__ == "__main__":
    main()
