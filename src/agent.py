"""
Core Agent Pipeline
Demonstrates multi-step reasoning, query generation, SerpApi search retrieval,
and citation synthesis.
"""

from typing import Dict, Any, List
from src.serpapi_service import SerpApiService


class ResearchAgent:
    def __init__(self, serpapi_service: SerpApiService):
        self.serpapi = serpapi_service

    def plan_subqueries(self, topic: str) -> List[str]:
        """
        Decomposes a broad topic into targeted search subqueries.
        (Can be connected to an LLM or run heuristic search planning).
        """
        return [
            f"{topic} latest updates 2026",
            f"{topic} key facts and statistics",
            f"{topic} analysis and market trends"
        ]

    def execute_research(self, topic: str, location: str = "India") -> Dict[str, Any]:
        """
        Executes multi-step research by querying SerpApi across subtopics,
        extracting organic results, and compiling structured citations.
        """
        queries = self.plan_subqueries(topic)
        collected_sources = []
        snippets = []

        for q in queries:
            try:
                res = self.serpapi.search_web(q, location=location, num=3)
                organic = res.get("organic_results", [])
                for item in organic:
                    source_entry = {
                        "query": q,
                        "title": item.get("title"),
                        "link": item.get("link"),
                        "snippet": item.get("snippet", "")
                    }
                    collected_sources.append(source_entry)
                    if item.get("snippet"):
                        snippets.append(f"[{item.get('title')}]: {item.get('snippet')}")
            except Exception as e:
                snippets.append(f"Error querying '{q}': {e}")

        # Structured synthesis
        summary = f"Synthesized research for '{topic}' across {len(collected_sources)} live search results."

        return {
            "topic": topic,
            "queries_executed": queries,
            "total_sources": len(collected_sources),
            "sources": collected_sources,
            "summary": summary,
            "extracted_knowledge": snippets
        }
