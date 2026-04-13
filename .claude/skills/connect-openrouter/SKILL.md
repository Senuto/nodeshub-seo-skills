---
name: connect-openrouter
description: |
  Step-by-step guide to connect OpenRouter API so you can use LLM-powered skills
  (SERP clustering with cluster naming, PAA question clustering, semantic clustering).
  Use when user says "connect OpenRouter," "set up OpenRouter," "OpenRouter setup,"
  "OpenRouter API key," or "how to connect to OpenRouter." No API cost — setup only.
license: MIT
compatibility: "Requires internet access for OpenRouter API key registration"
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Connect with OpenRouter

**First action:** Run the banner:
```bash
python3 -c "import sys; sys.path.insert(0,'.claude/skills/nod-nodeshub-api/scripts'); from banner import print_banner; print_banner('Connect OpenRouter')"
```

Walk the user through connecting OpenRouter so they can use LLM-powered features in skills like `nod-serp-clusters` and `nod-paa-miner`. Do it **step by step**, asking for confirmation before continuing.

**Privacy:** The API key is stored in `.claude/settings.local.json` (gitignored).

---

## Step 0: Check if OpenRouter is already connected

Run:

```bash
python3 -c "
import sys, os
sys.path.insert(0, '.claude/skills/nod-nodeshub-api/scripts')
from openrouter_client import _load_key_from_settings
key, source = _load_key_from_settings()
if key:
    print(f'OpenRouter key found in {source}')
    print(f'Key: {key[:12]}...')
    print('Already connected.')
else:
    print('No OpenRouter key found.')
"
```

- **If key found:** Ask the user: "OpenRouter is already connected. Do you want to **change** the key or are you done?"
- **If no key:** Continue with Step 1.

---

## Step 1: Get your API key

1. Ask the user to open **[openrouter.ai/keys](https://openrouter.ai/keys)**.
2. Sign in (Google, GitHub, or email).
3. Click **"Create Key"**.
4. Copy the key (starts with `sk-or-v1-...`).

**Pricing:** OpenRouter is pay-per-use. Most skills use `google/gemini-2.5-flash-lite` which costs fractions of a cent per call. Add $5 credit to start — it lasts a long time for cluster naming.

**Ask:** "Have you copied your API key? Paste it here when ready."

---

## Step 2: Save the key

When the user pastes the key, run:

```bash
python3 .claude/skills/nod-nodeshub-api/scripts/save_openrouter_key.py "PASTE_THE_KEY_HERE"
```

This saves the key to `.claude/settings.local.json` under `env.OPENROUTER_API_KEY` and runs a quick verification call.

Expected output:
```
Saved OpenRouter API key to .claude/settings.local.json
Test response: OK
Setup OK.
```

**If verification fails:** Check that the key is correct and has credit. The test call uses ~1 token.

**Ask:** "Did you see 'Setup OK'? If you see any error, paste it here."

---

## Step 3: Verify with a real skill

Suggest a quick test:

```bash
# Quick test: cluster 3 keywords (costs ~1 NodesHub token + tiny OpenRouter cost)
python3 .claude/skills/nod-serp-clusters/scripts/cluster.py \
  --keywords "seo tools,keyword research,serp analysis" \
  --output /tmp/test-cluster \
  --levels 1
```

Or if they don't have NodesHub tokens, test OpenRouter directly:

```bash
python3 -c "
import sys
sys.path.insert(0, '.claude/skills/nod-nodeshub-api/scripts')
from openrouter_client import OpenRouterClient
client = OpenRouterClient()
print(client.chat('Name this group of topics in 2-3 words: SEO, keywords, SERP analysis'))
"
```

---

## Summary

- **Get key:** [openrouter.ai/keys](https://openrouter.ai/keys) → Create Key → copy.
- **Save:** `python3 .claude/skills/nod-nodeshub-api/scripts/save_openrouter_key.py "sk-or-v1-..."` — saves to gitignored `.claude/settings.local.json`.
- **Used by:** `nod-serp-clusters` (cluster naming), `nod-paa-miner` (question clustering), semantic clustering.
- **Default model:** `google/gemini-2.5-flash-lite` — fast and cheap.

## Which skills need OpenRouter?

| Skill | Required? | What for |
|-------|-----------|----------|
| `nod-serp-clusters` | Yes | LLM names each cluster |
| `nod-paa-miner --cluster` | Optional | Groups questions by topic |
| Semantic clustering | Yes | Embeddings + cluster naming |
