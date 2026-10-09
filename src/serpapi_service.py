"""
SerpApi Service Wrapper
Provides structured, resilient access to multiple SerpApi search engines.
"""

from typing import Dict, Any, Optional
import serpapi
from src.config import SERPAPI_API_KEY


class SerpApiService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or SERPAPI_API_KEY
        self.client = serpapi.Client(api_key=self.api_key) if self.api_key else None

    def _ensure_api_key(self):
        if not self.api_key or self.api_key == "your_serpapi_api_key_here":
            raise ValueError(
                "SERPAPI_API_KEY is not configured. Please set it in your .env file."
            )
        if not self.client:
            self.client = serpapi.Client(api_key=self.api_key)

    def search_web(self, query: str, location: str = "India", num: int = 5) -> Dict[str, Any]:
        """Perform standard Google Web search."""
        self._ensure_api_key()
        params = {
            "engine": "google",
            "q": query,
            "location": location,
            "hl": "en",
            "gl": "in",
            "num": num,
        }
        return self.client.search(params)

    def search_news(self, query: str, location: str = "India", num: int = 5) -> Dict[str, Any]:
        """Fetch real-time news articles via Google News engine."""
        self._ensure_api_key()
        params = {
            "engine": "google_news",
            "q": query,
            "gl": "in",
            "hl": "en",
        }
        return self.client.search(params)

    def search_shopping(self, query: str, location: str = "India", num: int = 5) -> Dict[str, Any]:
        """Search products and prices via Google Shopping engine."""
        self._ensure_api_key()
        params = {
            "engine": "google_shopping",
            "q": query,
            "location": location,
            "gl": "in",
            "hl": "en",
        }
        return self.client.search(params)

    def search_scholar(self, query: str, num: int = 5) -> Dict[str, Any]:
        """Search academic papers, citations, and patents via Google Scholar."""
        self._ensure_api_key()
        params = {
            "engine": "google_scholar",
            "q": query,
            "hl": "en",
        }
        return self.client.search(params)

    def search_maps(self, query: str, location: str = "India") -> Dict[str, Any]:
        """Search places, businesses, ratings, and coordinates via Google Maps."""
        self._ensure_api_key()
        params = {
            "engine": "google_maps",
            "q": query,
        }
        return self.client.search(params)

    def search_jobs(self, query: str, location: str = "India") -> Dict[str, Any]:
        """Search active job openings via Google Jobs."""
        self._ensure_api_key()
        params = {
            "engine": "google_jobs",
            "q": query,
            "location": location,
            "hl": "en",
        }
        return self.client.search(params)
