from duckduckgo_search import DDGS
import json

q = "IPL DC vs CSK toss today May 5 2026"
print(f"Searching for: {q}")
try:
    with DDGS() as ddgs:
        results = list(ddgs.text(q, max_results=5, backend="lite", region="in-en"))
        print(f"Results: {len(results)}")
        for i, r in enumerate(results):
            print(f"[{i}] {r['title']}")
            print(f"    {r['body']}")
except Exception as e:
    print(f"Error: {e}")
