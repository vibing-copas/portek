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
    return None

ip = resolve_dns_over_https("api.bybit.id")
if ip:
    DNS_CACHE["api.bybit.id"] = ip

original_getaddrinfo = socket.getaddrinfo
def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host in DNS_CACHE:
        return original_getaddrinfo(DNS_CACHE[host], port, family, type, proto, flags)
    return original_getaddrinfo(host, port, family, type, proto, flags)
socket.getaddrinfo = patched_getaddrinfo

# Query all spot tickers
url = "https://api.bybit.id/v5/market/tickers?category=spot"
print("Fetching all spot tickers from Bybit...")
try:
    res = requests.get(url, timeout=10)
    print("Status:", res.status_code)
    data = res.json()
    print("retCode:", data.get("retCode"))
    print("retMsg:", data.get("retMsg"))
    ticker_list = data.get("result", {}).get("list", [])
    print(f"Total tickers returned: {len(ticker_list)}")
    if ticker_list:
        print("First 3 tickers:")
        print(json.dumps(ticker_list[:3], indent=2))
except Exception as e:
    print("Error:", e)
