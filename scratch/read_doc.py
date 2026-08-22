import re

with open(r"C:\Users\ayyas\.gemini\antigravity-ide\brain\c33227d6-4a6f-4433-9147-0148ff4c4554\.system_generated\steps\132\content.md", "r", encoding="utf-8") as f:
    text = f.read()

# Let's search for lines containing these addresses or look for JSON structure where they are defined.
# Let's write a regex that matches the addresses and gives 500 characters before and after in raw text.
target_addrs = [
    "0x57Cf0C29C2B7Bc7Cf5396568e25E34a1b687ea05",
    "0x5715203B16F15d7349Cb1E3537365E9664EAf933",
    "0xa15E3295465439A361dBcac79C1DBCE6Cd01E562",
    "0xA4682A2A5Fe02feFF8Bd200240A41AD0E6EaF8d5",
    "0xf7c7d7507041977aB0328CAf449f1e80085709a9",
    "0xb0d39990E1C38B50D0b7f6911525535Fbacb4C26",
    "0xe4816658ad10bF215053C533cceAe3f59e1f1087"
]

for addr in target_addrs:
    print(f"\n==================================================")
    print(f"Address: {addr}")
    for m in re.finditer(re.escape(addr), text):
        start = max(0, m.start() - 300)
        end = min(len(text), m.end() + 300)
        snippet = text[start:end]
        # Clean HTML slightly but keep text structure
        snippet = re.sub(r'<[^>]+>', ' ', snippet)
        snippet = re.sub(r'\s+', ' ', snippet)
        print(f"Snippet: ... {snippet} ...")
        break
