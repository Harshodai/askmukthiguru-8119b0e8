from duckduckgo_search import DDGS

def test_search():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    with DDGS(headers=headers) as ddgs:
        query = "what are the upcoming programs of sri krishnaji and preethaji"
        try:
            results = list(ddgs.text(query, max_results=15))
            print(f"Query: '{query}' | Results: {len(results)}")
            for r in results:
                print(f"  - URL: {r.get('href')} | Title: {r.get('title')}")
        except Exception as e:
            print(f"Query '{query}' failed: {e}")

if __name__ == "__main__":
    test_search()
