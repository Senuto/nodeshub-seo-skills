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

## ⛔ CRITICAL SECURITY RULE — NEVER ASK THE USER TO PASTE THE API KEY INTO CHAT

Anything the user types into the chat leaves their machine — it's sent to the LLM provider, written to local session logs (`~/.claude/projects/<slug>/*.jsonl`) in plain text, and may appear in telemetry, backups, or IDE sync. **A secret that touches the chat context is a leaked secret.** An OpenRouter key with credit attached can be burned by anyone who gets it.

You MUST:
- Never write "paste it here," "paste the key," "send me the key," or similar.
- Never offer to save a key the user pastes.
- If the user pastes a key anyway, stop, refuse to use it, tell them the key is now compromised and they should revoke it at openrouter.ai/keys immediately, then re-run setup with a new key saved locally.

The user saves the key themselves (Step 2). You only read the file afterwards to verify.

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

Tell the user — **do not** ask them to paste anything here:

1. Open **[openrouter.ai/keys](https://openrouter.ai/keys)**.
2. Sign in (Google, GitHub, or email).
3. Click **"Create Key"**.
4. Copy the key (starts with `sk-or-v1-...`).

**Pricing:** OpenRouter is pay-per-use. Most skills use `google/gemini-2.5-flash-lite` which costs fractions of a cent per call. Add $5 credit to start — it lasts a long time for cluster naming.

Then say: "Copy the key to your clipboard. **Do not paste it into this chat.** Go to Step 2."

---

## Step 2: The user saves the key locally (NOT via chat)

Give the user these two options. They run one themselves — you never see the key.

**Option A — one-line terminal command (recommended):**

Tell the user to open their terminal in the repo root, prepend a space (so it's skipped by shell history if `HISTCONTROL=ignorespace`/`ignoreboth` is set), paste their key in place of `<paste-your-key-here>`, and run:

```bash
 python3 .claude/skills/nod-nodeshub-api/scripts/save_openrouter_key.py "<paste-your-key-here>"
```

This saves the key to `.claude/settings.local.json` under `env.OPENROUTER_API_KEY` and runs a quick verification call.

If their shell doesn't respect `ignorespace`, they can run `history -d <n>` afterwards to wipe that line.

**Option B — edit the file manually:**

Tell the user to open `.claude/settings.local.json` in their editor and add/merge:

```json
{
  "env": {
    "OPENROUTER_API_KEY": "<paste-your-key-here>"
  }
}
```

**Reply "done" (not the key) when saved.**

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
