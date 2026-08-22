import re

with open(r"C:\Users\ayyas\.gemini\antigravity-ide\brain\c33227d6-4a6f-4433-9147-0148ff4c4554\.system_generated\steps\132\content.md", "r", encoding="utf-8") as f:
    text = f.read()

# Strip HTML tags
clean_text = re.sub(r'<[^>]+>', ' ', text)
clean_text = re.sub(r'\s+', ' ', clean_text)

addr = "0x57Cf0C29C2B7Bc7Cf5396568e25E34a1b687ea05"
m = re.search(re.escape(addr), clean_text)
if m:
    print(clean_text[max(0, m.start() - 300): m.end() + 600])
