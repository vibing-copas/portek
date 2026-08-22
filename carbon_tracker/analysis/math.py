import math

def human(raw, decimals): return raw / (10 ** decimals)

def unit_price(source_raw, target_raw, source_decimals, target_decimals):
    return (source_raw / 10**source_decimals) / (target_raw / 10**target_decimals)

def discount(auction_usd, market_usd):
    if auction_usd is None or market_usd is None or market_usd <= 0: return None
    return (1 - auction_usd / market_usd) * 100

def eta_days(auction_usd, market_usd, half_life_s):
    if auction_usd is None or market_usd is None or market_usd <= 0 or half_life_s <= 0: return None
    if auction_usd <= market_usd: return 0.0
    return (half_life_s / 86400) * math.log(auction_usd / market_usd, 2)
