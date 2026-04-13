# NodesHub API Reference

Base URL: `https://api.serpdata.io/v1`
Auth: `Authorization: Bearer YOUR_API_KEY`
Required header: `User-Agent` (any value)

## GET /search — SERPdata

Extract Google SERP results for a keyword.

| Param | Required | Values | Description |
|-------|----------|--------|-------------|
| keyword | Yes | string | Search phrase |
| gl | Yes | us, pl, de, uk, fr... | Country code |
| hl | Yes | en, pl, de... | Language code |
| device | No | desktop, mobile | Device type |
| num | No | 10-100 | Result count (temporarily unavailable) |

**Cost:** 1 token

**Response structure:**
```json
{
  "data": {
    "search_engine": "google",
    "location": "us",
    "language": "en",
    "timestamp": "2026-02-17T...",
    "search_url": "https://google.com/search?...",
    "total_results_count": 1234567,
    "results": {
      "query": "keyword",
      "success": true,
      "organic_results": [
        {
          "pos": 1,
          "global_pos": 1,
          "url": "https://example.com/page",
          "domain": "example.com",
          "title": "Page Title",
          "description": "Snippet text...",
          "page": 1,
          "pos_internal": 1
        }
      ],
      "snippets": {
        "ads": [],
        "ai_overview": {
          "boundingBox": {},
          "content_links": [],
          "content_text": "AI-generated summary..."
        },
        "answer_box": [],
        "people_also_ask": { "items": [...] },
        "perspectives": [],
        "perspectives_carousel": [{ "items": [...] }],
        "related_searches": {
          "queries": ["related query 1", "related query 2"]
        },
        "videos_pack": [{ "title": "...", "videos": [...] }]
      },
      "snippets_found": ["related_searches", "ai_overview", "videos_pack"]
    }
  },
  "totalResponseTime": 2786
}
```

**Key paths:**
- Organic results: `data.results.organic_results[]`
- SERP features: `data.results.snippets.*`
- AI Overview text: `data.results.snippets.ai_overview.content_text`
- Related searches: `data.results.snippets.related_searches.queries[]`
- Total results: `data.total_results_count`
- Feature list: `data.results.snippets_found[]`

## GET /query-fanout — Query Fan-out

Expand a keyword into related queries and questions.

| Param | Required | Values | Description |
|-------|----------|--------|-------------|
| keyword | Yes | string | Base keyword |
| hl | Yes | en, pl, de... | Language code |
| mode | Yes | standard, reasoning | Quality vs cost tradeoff |
| add_questions | No | true, false | Include question queries |
| add_topic_leaders | No | true, false | Include topic leader queries |
| include_reasoning | No | true, false | Include reasoning in output |

**Cost:** 7.5 tokens (standard) / 30 tokens (reasoning)

## GET /intent-classifier — Intent Classifier

Classify keyword search intent. **Status: Beta — may produce inaccurate results.**

| Param | Required | Values | Description |
|-------|----------|--------|-------------|
| keyword | Yes | string | Keyword to classify |
| gl | Yes | us, pl, de... | Country code |
| hl | Yes | en, pl, de... | Language code |

**Cost:** 2 tokens

**Intents:** informational, transactional, navigational, commercial

## GET /api-key/balance — Check Balance

Returns `{ "limit": 5000, "left": 4850 }`. **Cost: 0 tokens.**

## GET /products — List Plans

Returns available pricing plans. **Cost: 0 tokens.**

## GET /google-params/gl — Countries

Returns list of available country codes. **Cost: 0 tokens. Public (no auth needed).**

## GET /google-params/hl — Languages

Returns list of available language codes. **Cost: 0 tokens. Public (no auth needed).**
