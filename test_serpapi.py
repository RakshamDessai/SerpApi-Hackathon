"""
SerpApi Quickstart & Health Check Script
Run this script to verify your SerpApi setup and API key.

Usage:
    python test_serpapi.py
"""

import os
import sys
from dotenv import load_dotenv

# Load variables from .env
load_dotenv()

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

def check_environment():
    print("=" * 60)
    print("  SERPAPI INDIA HACKATHON 2026 - SETUP VERIFICATION")
    print("=" * 60)
    print(f"Python Version: {sys.version.split()[0]}")
    
    if not SERPAPI_API_KEY or SERPAPI_API_KEY == "your_serpapi_api_key_here":
        print("\n[!] SERPAPI_API_KEY is NOT set in your .env file.")
        print("  -> Step 1: Copy .env.example to .env (if not already done)")
        print("  -> Step 2: Sign up / log in at https://serpapi.com/")
        print("  -> Step 3: Get your free API key at https://serpapi.com/manage-api-key")
        print("  -> Step 4: Paste it into .env as SERPAPI_API_KEY=your_actual_key\n")
        return False
    else:
        masked_key = SERPAPI_API_KEY[:4] + "..." + SERPAPI_API_KEY[-4:] if len(SERPAPI_API_KEY) > 8 else "***"
        print(f"\n[OK] Found SERPAPI_API_KEY: {masked_key}")
        return True

def test_search():
    import serpapi
    print("\n[i] Testing connection to SerpApi with a sample Google Search query...")
    try:
        client = serpapi.Client(api_key=SERPAPI_API_KEY)
        params = {
            "engine": "google",
            "q": "SerpApi India Hackathon 2026",
            "location": "India",
            "hl": "en",
            "gl": "in",
            "num": 3
        }
        results = client.search(params)

        if "error" in results:
            print(f"[ERROR] SerpApi returned error: {results['error']}")
            return False

        search_metadata = results.get("search_metadata", {})
        print(f"[SUCCESS] Search completed successfully!")
        print(f"  Status: {search_metadata.get('status')}")
        print(f"  Total time taken: {search_metadata.get('total_time_taken')}s")
        print("\nTop Results:")
        for idx, res in enumerate(results.get("organic_results", [])[:3], 1):
            print(f"  {idx}. {res.get('title')} ({res.get('link')})")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to execute SerpApi query: {e}")
        return False

if __name__ == "__main__":
    if check_environment():
        test_search()
    else:
        print("[INFO] Run this script again after adding your key in .env.")
