import requests
import json

# List of 42 covered token symbols from the latest snapshots
symbols = ["AAVE", "ANDY", "ARB", "BIFI", "BNT", "cbBTC", "CELO", "COTI", "CRV", "DAI", "ETH", "GUSD", "LBTC", "LDO", "LINK", "MATIC", "PAXG", "PEPE", "RAIL", "SEI", "sfrxUSD", "SHIB", "sUSDS", "TON", "UNI", "USDC", "USDC.e", "USDGLO", "USDm", "USDS", "USDT", "USD₮", "USD₮0", "WBTC", "WETH", "wstETH", "XAUt"]

print(f"Starting queries for {len(symbols)} symbols on DIA price feed...")

for symbol in symbols:
    url = f"https://api.diadata.org/v1/quotation/{symbol}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            price = data.get("Price")
            print(f"{symbol}: ${price} (resolved)")
        else:
            print(f"{symbol}: Failed (status {response.status_code})")
    except Exception as e:
        print(f"{symbol}: Error ({str(e)})")
