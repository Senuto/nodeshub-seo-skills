---
name: connect-genuino
description: |
  Step-by-step guide to connect Genuino AI Detection API so you can check if content
  is AI-generated or human-written. Use when user says "connect Genuino," "set up Genuino,"
  "Genuino setup," "Genuino API key," or "how to connect to Genuino." No API cost — setup only.
license: MIT
compatibility: "Requires internet access for Genuino API key registration"
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Connect with Genuino

**First action:** Run the banner:
```bash
python3 -c "import sys; sys.path.insert(0,'.claude/skills/nod-nodeshub-api/scripts'); from banner import print_banner; print_banner('Connect Genuino')"
```

Walk the user through connecting Genuino API so they can use the `ai-score` skill to detect AI-generated content. Do it **step by step**, asking for confirmation before continuing.

## ⛔ CRITICAL SECURITY RULE — NEVER ASK THE USER TO PASTE THE API KEY INTO CHAT

Anything the user types into the chat leaves their machine — it's sent to the LLM provider, written to local session logs (`~/.claude/projects/<slug>/*.jsonl`) in plain text, and may appear in telemetry, backups, or IDE sync. **A secret that touches the chat context is a leaked secret.**

You MUST:
- Never write "paste it here," "paste the key," "send me the key," or similar.
- Never offer to save a key the user pastes.
- If the user pastes a key anyway, stop, refuse to use it, tell them the key is now compromised and they should rotate it in the Genuino dashboard, then re-run setup with the new key saved locally.

The user saves the key themselves (Step 2). You only read the file afterwards to verify.

**Privacy:** The API key is stored in `.claude/settings.local.json` (gitignored).

---

## Step 0: Check if Genuino is already connected

Run:

```bash
python3 -c "
import json
from pathlib import Path

candidates = [
    Path('.claude/settings.local.json'),
    Path.home() / '.claude' / 'settings.local.json',
]
for p in candidates:
    if p.is_file():
        data = json.loads(p.read_text())
        key = data.get('env', {}).get('GENUINO_API_KEY')
        if key:
            print(f'Genuino key found in {p}')
            print(f'Key: {key[:12]}...')
            print('Already connected.')
            break
else:
    print('No Genuino key found.')
"
```

- **If key found:** Ask the user: "Genuino is already connected. Do you want to **change** the key or are you done?"
- **If no key:** Continue with Step 1.

---

## Step 1: Get your API key

Tell the user — **do not** ask them to paste anything here:

1. Open **[genuino.ai](https://genuino.ai)**.
2. Sign up / log in to the dashboard.
3. Navigate to the API keys section.
4. Create a new API key and copy it to the clipboard.

Then say: "Copy the key to your clipboard. **Do not paste it into this chat.** Go to Step 2."

---

## Step 2: The user saves the key locally (NOT via chat)

Give the user these two options. They run one themselves — you never see the key.

**Option A — one-line terminal command (recommended):**

Tell the user to open their terminal in the repo root, prepend a space (so it's skipped by shell history if `HISTCONTROL=ignorespace`/`ignoreboth` is set), paste their key in place of `<paste-your-key-here>`, and run:

```bash
 python3 -c "import json; from pathlib import Path; p = Path('.claude/settings.local.json'); d = json.loads(p.read_text()) if p.is_file() else {}; d.setdefault('env', {})['GENUINO_API_KEY'] = '<paste-your-key-here>'; p.write_text(json.dumps(d, indent=2) + '\n'); print('Saved.')"
```

If their shell doesn't respect `ignorespace`, they can run `history -d <n>` afterwards to wipe that line.

**Option B — edit the file manually:**

Tell the user to open `.claude/settings.local.json` in their editor and add/merge:

```json
{
  "env": {
    "GENUINO_API_KEY": "<paste-your-key-here>"
  }
}
```

If the file already has other content, keep it and just add/update the `env.GENUINO_API_KEY` field.

**Reply "done" (not the key) when saved.**

---

## Step 3: Verify

```bash
python3 -c "
import json, urllib.request
from pathlib import Path

path = Path('.claude/settings.local.json')
key = json.loads(path.read_text())['env']['GENUINO_API_KEY']

req = urllib.request.Request('https://api.genuino.ai/v1/health/basic')
req.add_header('X-API-Key', key)
req.add_header('User-Agent', 'genuino-claude-skill/0.1')
resp = urllib.request.urlopen(req, timeout=10)
data = json.loads(resp.read())
print(f'Status: {data[\"status\"]}')
print(f'Message: {data[\"message\"]}')
print('Setup OK.')
"
```

Expected output:
```
Status: ok
Message: API is running
Setup OK.
```

**Ask:** "Did you see 'Setup OK'? If you see any error, paste it here."

---

## Summary

- **Get key:** [genuino.ai](https://genuino.ai) → Dashboard → API keys → Create.
- **Save:** `.claude/settings.local.json` under `env.GENUINO_API_KEY` (gitignored).
- **Auth:** Header `X-API-Key` on all `/v1` endpoints.
- **Used by:** `ai-score` skill (AI content detection).
