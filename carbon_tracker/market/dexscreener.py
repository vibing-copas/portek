import requests
from collections import defaultdict

CHAINS = {
    1: "ethereum",
    1329: "sei",
    239: "tac",
    42220: "celo",
    2632500: "coti"
}

NATIVE_WRAPPED_MAP = {
    1: "0xC02aaA39b223FE8D0A0e5C4F27ead9083C756Cc2",       # WETH on Ethereum
    1329: "0xE30feDd158A2e3b13e9badaeABaFc5516e95e8C7",    # WSEI on Sei
    239: "0xb63b9f0eb4a6e6f191529d71d4d88cc8900df2c9",     # WTAC on TAC
    42220: "0x471EcE3750Da237f93B8E339c536989b8978a438",   # CELO on Celo
}

def query(chain_id, addresses, batch_size=30, base_url="https://api.dexscreener.com"):
    slug = CHAINS.get(chain_id)
    if not slug: return {}
    
    # Get wrapped native address for this chain, fallback to standard WETH
    wrapped_addr = NATIVE_WRAPPED_MAP.get(chain_id, "0xC02aaA39b223FE8D0A0e5C4F27ead9083C756Cc2")
    
    mapped_addresses = []
    for a in addresses:
        if a.lower() == "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee":
            mapped_addresses.append(wrapped_addr)
        else:
            mapped_addresses.append(a)
            
    out = {}
    for i in range(0, len(mapped_addresses), batch_size):
        batch = mapped_addresses[i:i+batch_size]
        url = f"{base_url}/tokens/v1/{slug}/" + ",".join(batch)
        r = requests.get(url, timeout=30); r.raise_for_status()
        groups = defaultdict(list)
        for p in r.json() or []:
            price = p.get("priceUsd")
            if price is None: continue
            liq = float((p.get("liquidity") or {}).get("usd") or 0)
            b = p.get("baseToken", {}).get("address", "").lower()
            q = p.get("quoteToken", {}).get("address", "").lower()
            groups[b].append((liq, float(price), p))
        for addr, rows in groups.items():
            liq, price, raw = max(rows, key=lambda x: x[0])
            out[addr] = {"price_usd": price, "liquidity_usd": liq, "pair": raw.get("pairAddress"), "dex": raw.get("dexId"), "url": raw.get("url")}
            
    # Map the price back to the native token address placeholder
    wrapped_lower = wrapped_addr.lower()
    native_lower = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    if wrapped_lower in out:
        out[native_lower] = out[wrapped_lower]
        
    return out

