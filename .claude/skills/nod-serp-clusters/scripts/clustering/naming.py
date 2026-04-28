"""LLM-based cluster naming via OpenRouter."""

import json
import sys


def name_clusters(clusters, llm_client, model, language="Polish"):
    """Use LLM to generate cluster names.

    Args:
        clusters: list of (cluster_id, keywords_list)
        llm_client: OpenRouterClient instance
        model: LLM model string
        language: language for cluster names

    Returns:
        dict of {cluster_id: name}
    """
    # Import locally to avoid hard dependency at import time
    from openrouter_client import OpenRouterError

    names = {}
    batch_size = 10
    for batch_start in range(0, len(clusters), batch_size):
        batch = clusters[batch_start:batch_start + batch_size]
        cluster_descriptions = []
        for idx, (cid, kws) in enumerate(batch):
            sample = kws[:15]
            cluster_descriptions.append(f"Cluster {idx}: {', '.join(sample)}")

        prompt = f"""Name each keyword cluster with a short, descriptive label (2-5 words) in {language}.
The name should capture the main topic/intent of the keywords.

{chr(10).join(cluster_descriptions)}

Respond ONLY with JSON: {{"0": "name", "1": "name"}}"""

        try:
            response = llm_client.chat(prompt, model=model, temperature=0.2, max_tokens=1000)
            response = response.strip()
            if response.startswith("```"):
                response = response.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            parsed = json.loads(response)
            for key, name in parsed.items():
                names[batch[int(key)][0]] = name
        except (json.JSONDecodeError, OpenRouterError, ValueError, IndexError) as e:
            print(f"  LLM naming error: {e}", file=sys.stderr)
            for cid, kws in batch:
                names.setdefault(cid, f"Cluster {cid}")

    return names
