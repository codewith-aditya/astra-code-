"""Tool: web_search -- Search the web using DuckDuckGo."""

from __future__ import annotations

import json
import urllib.request
import urllib.parse

from astra.tools.registry import ToolDefinition


def handle_web_search(
    query: str,
    max_results: int = 5,
) -> dict:
    """Search the web using DuckDuckGo instant answer API."""
    try:
        encoded = urllib.parse.urlencode({"q": query, "format": "json", "no_html": "1"})
        url = f"https://api.duckduckgo.com/?{encoded}"
        req = urllib.request.Request(url, headers={"User-Agent": "Astra-Agent/0.1"})

        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = []

        # Abstract
        if data.get("Abstract"):
            results.append({
                "title": data.get("Heading", ""),
                "snippet": data["Abstract"],
                "url": data.get("AbstractURL", ""),
            })

        # Related topics
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and "Text" in topic:
                results.append({
                    "title": topic.get("Text", "")[:100],
                    "snippet": topic.get("Text", ""),
                    "url": topic.get("FirstURL", ""),
                })

        if not results:
            return {"results": [], "note": "No results found. Try a different query."}

        return {"query": query, "results": results[:max_results]}

    except Exception as exc:
        return {"error": f"Search failed: {exc}"}


WEB_SEARCH_TOOL = ToolDefinition(
    name="web_search",
    description="Search the web and return results with titles, snippets, and URLs.",
    parameters={
        "query": {
            "type": "string",
            "description": "The search query.",
        },
        "max_results": {
            "type": "integer",
            "description": "Max results to return. Default 5.",
            "optional": True,
        },
    },
    handler=handle_web_search,
)
