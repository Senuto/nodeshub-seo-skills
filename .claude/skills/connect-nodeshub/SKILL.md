---
name: connect-nodeshub
description: |
  Step-by-step guide to connect NodesHub API so you can use all nod- skills
  (SERP analysis, keyword research, rank tracking, content briefs, etc.). Use when
  user says "connect NodesHub," "set up NodesHub," "NodesHub setup," "API key
  NodesHub," or "how to connect to NodesHub." No API cost — setup only.
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

Then walk the user through connecting the NodesHub API so they can use all nod- skills (SERP analysis, keyword research, rank tracking, content briefs, and more). Do it **step by step**, asking for confirmation before continuing.

## ⛔ CRITICAL SECURITY RULE — NEVER ASK THE USER TO PASTE THE API KEY INTO CHAT

Anything the user types into the chat leaves their machine — it's sent to the LLM provider, written to local session logs (`~/.claude/projects/<slug>/*.jsonl`) in plain text, and may appear in telemetry, backups, or IDE sync. **A secret that touches the chat context is a leaked secret.**

You MUST:
- Never write "paste it here," "paste the key," "send me the key," or similar.
- Never offer to save a key the user pastes.
- If the user pastes a key anyway, stop, refuse to use it, tell them the key is now compromised and they should rotate it at nodeshub.io, then re-run the setup with the new key saved locally.

The user saves the key themselves (see Step 2). You only read the file afterwards to verify.

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

Tell the user — **do not** ask them to paste anything here:

1. Open **[nodeshub.io](https://nodeshub.io)**.
2. Scroll to the **API Playground** section.
3. Click **"Copy to clipboard"** to copy the API key. No account or email verification required.

Then say: "Copy the key to your clipboard. **Do not paste it into this chat.** Go to Step 2."

---

## Step 2: The user saves the key locally (NOT via chat)

Give the user these two options. They run one themselves — you never see the key.

**Option A — one-line terminal command (recommended):**

```bash
python3 .claude/skills/nod-nodeshub-api/scripts/save_key.py "<paste-your-key-here>"
```

Tell the user:
- Open their terminal, prepend a space before the command (so it won't land in shell history if `HISTCONTROL=ignorespace`/`ignoreboth` is set), paste their key in place of `<paste-your-key-here>`, and run it.
- If their shell doesn't respect `ignorespace`, they can run `history -d <n>` afterwards to wipe that line.

**Option B — edit the file manually:**

Tell the user to open `.claude/settings.local.json` in their editor and add/merge:

```json
{
  "env": {
    "NODESHUB_API_KEY": "<paste-your-key-here>"
  }
}
```

If the file already has other content (e.g. `permissions`), keep it and just add/update the `env.NODESHUB_API_KEY` field.

**Reply "done" (not the key) when saved.**

Remind them: `.claude/settings.local.json` is in `.gitignore`, so the key will not be committed. **Do not make the repo public** — it now contains private data.

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
