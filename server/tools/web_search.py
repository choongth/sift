import os
from tavily import AsyncTavilyClient


async def web_search(query: str, max_results: int = 5) -> list[dict]:
    api_key = os.environ["TAVILY_API_KEY"]
    client = AsyncTavilyClient(api_key=api_key)

    response = await client.search(
        query=query,
        max_results=max_results,
        include_answer=False,
    )

    results = []
    for r in response.get("results", []):
        results.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("content", ""),
        })

    return results
