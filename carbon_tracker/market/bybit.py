import socket
import requests
import json

DNS_CACHE = {}

def resolve_dns_over_https(domain):
    url = f"https://cloudflare-dns.com/dns-query?name={domain}&type=A"
    headers = {"accept": "application/dns-json"}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            ips = [answer["data"] for answer in response.json().get("Answer", []) if answer["type"] == 1]
            if ips:
                return ips[0]
    except Exception:
        pass
        
    url_google = f"https://dns.google/resolve?name={domain}&type=A"
    try:
        response = requests.get(url_google, timeout=5)
        if response.status_code == 200:
            ips = [answer["data"] for answer in response.json().get("Answer", []) if answer["type"] == 1]
            if ips:
                return ips[0]
    except Exception:
        pass
    return None

def apply_dns_bypass():
    ip = resolve_dns_over_https("api.bybit.id")
    if ip:
        DNS_CACHE["api.bybit.id"] = ip
        original_getaddrinfo = socket.getaddrinfo
        def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            if host in DNS_CACHE:
                return original_getaddrinfo(DNS_CACHE[host], port, family, type, proto, flags)
            return original_getaddrinfo(host, port, family, type, proto, flags)
        socket.getaddrinfo = patched_getaddrinfo

# Apply at module import time
apply_dns_bypass()

def clean_token_symbol(symbol):
    if not symbol:
        return ""
    s = symbol.upper().strip()
    s = s.replace("USD\u20ae", "USDT")
    s = s.replace("USD₮", "USDT")
    s = s.replace("₮", "T")
    for suffix in [".E", ".N", "0", "1", "2", "3", "4", "5"]:
        if s.endswith(suffix):
            s = s[:-len(suffix)]
    if s in ["WETH", "WETH9"]:
        s = "ETH"
    elif s in ["WSEI"]:
        s = "SEI"
    elif s in ["WTAC"]:
        s = "TAC"
    elif s in ["WBTC", "CBBTC", "LBTC"]:
        s = "BTC"
    return s

def query(tokens):
    """
    Query spot prices from Bybit API for given tokens.
    tokens: list of tuples (address, symbol, ...)
    """
    url = "https://api.bybit.id/v5/market/tickers?category=spot"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return {}
        data = r.json()
        if data.get("retCode") != 0:
            return {}
    except Exception:
        return {}
        
    ticker_list = data.get("result", {}).get("list", [])
    tickers_dict = {}
    for t in ticker_list:
        symbol = t.get("symbol")
        price = t.get("lastPrice")
        if symbol and price:
            tickers_dict[symbol] = float(price)
            
    out = {}
    for token_tuple in tokens:
        addr = token_tuple[0]
        sym = token_tuple[1]
        
        clean_sym = clean_token_symbol(sym)
        if not clean_sym:
            continue
            
        price_val = None
        if clean_sym == "USDT":
            price_val = 1.0
        else:
            price_val = tickers_dict.get(f"{clean_sym}USDT")
            if price_val is None:
                price_val = tickers_dict.get(f"{clean_sym}USDC")
                
        if price_val is not None:
            out[addr.lower()] = {
                "price_usd": price_val,
                "liquidity_usd": 100000.0,
                "is_bybit": True
            }
    return out
