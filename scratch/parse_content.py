import re

with open(r"C:\Users\ayyas\.gemini\antigravity-ide\brain\c33227d6-4a6f-4433-9147-0148ff4c4554\.system_generated\steps\132\content.md", "r", encoding="utf-8") as f:
    text = f.read()

# Let's search for "sei" (case-insensitive) and look at the characters around it
for m in re.finditer(r'sei', text, re.IGNORECASE):
    # Print the index and a small snippet of 100 chars
    start = max(0, m.start() - 50)
    end = min(len(text), m.end() + 150)
    snippet = text[start:end].replace("\n", " ")
    print(f"Index {m.start()}: {snippet}")
    # Only print first 15 to avoid flooding
