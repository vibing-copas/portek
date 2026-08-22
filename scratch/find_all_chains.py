import re

with open(r"C:\Users\ayyas\.gemini\antigravity-ide\brain\c33227d6-4a6f-4433-9147-0148ff4c4554\.system_generated\steps\132\content.md", "r", encoding="utf-8") as f:
    text = f.read()

# Let's find all headings with "... EVM contracts" or "... contracts"
clean_text = re.sub(r'<[^>]+>', ' ', text)
clean_text = re.sub(r'\s+', ' ', clean_text)

# Find all segments that look like "[Name] EVM contracts" or "[Name] contracts"
# Let's search for patterns like:
# "TAC EVM contracts", "Base contracts", "Fantom contracts", "Mantle contracts", "Linea contracts", "Blast contracts", "Telos contracts", "IOTA contracts", "Celo EVM contracts", "Coti EVM contracts", "Manta contracts", etc.
headings = re.findall(r'(\b\w+[\w\s\-]+ (?:EVM )?contracts)\b', clean_text)
# Filter unique headings and print
seen = set()
for h in headings:
    h = h.strip()
    if h.lower() not in seen and any(keyword in h.lower() for keyword in ["evm contracts", "contracts"]):
        seen.add(h.lower())
        # Let's print the heading and try to find the next few contract names and addresses
        print(f"\nHeading: {h}")
        # Search in clean_text
        m = re.search(re.escape(h), clean_text)
        if m:
            snippet = clean_text[m.start(): m.end() + 1000]
            print(f"Snippet: {snippet[:800]}...")
