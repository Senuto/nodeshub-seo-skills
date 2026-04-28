"""SERP response parsing — extract organic results and snippet types."""


def extract_organic(serp_data):
    """Extract organic results with url, domain, position."""
    results = []
    try:
        organic = serp_data["data"]["results"].get("organic_results", [])
        for r in organic[:10]:
            url = r.get("url", "").strip().rstrip("/").lower()
            domain = r.get("domain", "").strip().lower()
            pos = r.get("pos", r.get("pos_internal", 0))
            title = r.get("title", "")
            if url:
                results.append({"url": url, "domain": domain, "pos": pos, "title": title})
    except (KeyError, TypeError, AttributeError):
        pass
    return results


def extract_snippets(serp_data):
    """Extract snippet types from SERP."""
    snippet_types = []
    try:
        snippets = serp_data["data"]["results"].get("snippets", {})
        if isinstance(snippets, dict):
            snippet_types = list(snippets.keys())
    except (KeyError, TypeError):
        pass
    return snippet_types
