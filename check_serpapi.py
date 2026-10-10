"""
SerpApi Quickstart & Health Check Script
Run this script to verify your SerpApi setup and API key.

Usage:
    python check_serpapi.py
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
    """Validate the key and show the remaining quota. Costs no search credit.

    Uses SerpApi's account endpoint over plain HTTPS rather than an SDK: the
    legacy and current SDKs both claim the `serpapi` module name.
    """
    import requests

    print("\n[i] Checking the key against SerpApi's account endpoint (free)...")
    try:
        response = requests.get(
            "https://serpapi.com/account.json",
            params={"api_key": SERPAPI_API_KEY},
            timeout=20,
        )
        account = response.json()
    except Exception as e:
        print(f"[ERROR] Could not reach SerpApi: {e}")
        return False

    if "error" in account:
        print(f"[ERROR] SerpApi returned error: {account['error']}")
        return False

    print("[SUCCESS] Key is valid.")
    print(f"  Plan: {account.get('plan_name')}")
    print(f"  Searches left this month: {account.get('plan_searches_left')}"
          f" of {account.get('searches_per_month')}")
    return True

if __name__ == "__main__":
    if check_environment():
        test_search()
    else:
        print("[INFO] Run this script again after adding your key in .env.")
