---
name: connect-nodeshub
description: |
  Step-by-step guide to connect NodesHub API so you can use all nod- skills
  (SERP analysis, keyword research, rank tracking, content briefs, etc.). Use when
  user says "connect NodesHub," "set up NodesHub," "NodesHub setup," "API key
  NodesHub," or "how to connect to NodesHub." No API cost — setup only.
license: MIT
compatibility: "Requires internet access for NodesHub API key registration"
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Connect with NodesHub

**First action:** Run the banner so the blue logo and skill name appear in the terminal:
```bash
python3 -c "import sys; sys.path.insert(0,'.claude/skills/nod-nodeshub-api/scripts'); from banner import print_banner; print_banner('Connect NodesHub')"
```

Then walk the user through connecting the NodesHub API so they can use all nod- skills (SERP analysis, keyword research, rank tracking, content briefs, and more). Do it **step by step**, and at each step ask for a paste or confirmation before continuing.

**Privacy:** The API key is stored in the repo in `.claude/settings.local.json` (that file is in `.gitignore`). **Tell the user: do not make this repo public** if it contains the API key — keep the repo private.

---

## Step 0: Check if NodesHub is already connected

**First**, run:

```bash
python3 .claude/skills/nod-nodeshub-api/scripts/check_setup.py
```

- **If the script reports "Setup OK"** (and shows balance): NodesHub is already connected. **Ask the user:** "NodesHub is already connected. Do you want to **change** the current API key or **add another** key/integration? (Reply: change / add another / no, I'm done.)"
  - If they say **change** or **add another** → continue with Step 1 (get new key, then save; for "change", overwrite the existing key; for "add another", clarify that this repo stores one key per file — adding a second key would mean a different config approach, or they can replace the key).
  - If they say **no, I'm done** → confirm and stop.
- **If the script fails or reports no key**: no integration yet → continue with Step 1.

---

## Step 1: Get your API key

1. Ask the user to open **[nodeshub.io](https://nodeshub.io)**.
2. Tell them: scroll to the **API Playground** section.
3. Click **"Copy to clipboard"** to copy the API key. No account or email verification is required.

**Ask:** "Have you copied your API key? Paste it here when ready (you can redact the middle part if you prefer; I need the full key to save it)."

---

## Step 2: Save the key in the repo

When the user pastes the API key:

1. Save it to `.claude/settings.local.json` in the repo. If the file already exists (e.g. with `permissions`), add or update the `env.NODESHUB_API_KEY` field. The file should look like:
   ```json
   {
     "env": {
       "NODESHUB_API_KEY": "the-key-they-pasted"
     }
   }
   ```
   If they already have other keys in the file (e.g. `permissions`), merge: keep existing content and set `env.NODESHUB_API_KEY`.

2. **Alternatively**, run the helper script for them:
   ```bash
   python3 .claude/skills/nod-nodeshub-api/scripts/save_key.py "PASTE_THE_KEY_HERE"
   ```
   (Replace `PASTE_THE_KEY_HERE` with the key they pasted.)

3. Remind them: `.claude/settings.local.json` is in `.gitignore`, so the key will not be committed. **Do not make the repo public** — it now contains private data.

**Ask:** "I've saved your key. Have you restarted Claude Code (or the terminal) if needed? Reply yes to continue to verification."

---

## Step 3: Verify

Run:

```bash
python3 .claude/skills/nod-nodeshub-api/scripts/check_setup.py
```

Expected output includes something like:
```
API Key: xxxxxxxx...
Balance: 100 / 100 tokens
Setup OK.
```

**Ask:** "Did you see 'Setup OK' and your token balance? If you see any error, paste it here."

---

## Summary

- **Get key:** [nodeshub.io](https://nodeshub.io) → API Playground → Copy to clipboard.
- **Save in repo:** `.claude/settings.local.json` under `env.NODESHUB_API_KEY`, or run `save_key.py` with the key. File is gitignored.
- **Keep the repo private** — do not publish it publicly when it contains the API key.

For more detail (security, token costs, user-level config), see `.claude/skills/nod-nodeshub-api/setup/README.md`.
