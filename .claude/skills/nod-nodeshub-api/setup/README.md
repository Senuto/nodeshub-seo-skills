# NodesHub API Setup

For a step-by-step guided setup with prompts to paste your key, use the **/connect-nodeshub** skill.

## Get Your API Key

1. Go to [nodeshub.io](https://nodeshub.io)
2. Scroll to the **API Playground** section
3. Click **"Copy to clipboard"** to copy your API key
4. No account or email verification required

## Configure in Claude Code

**Option A — One file in repo (ignored by git):**  
Use `.claude/settings.local.json` for both API key and project settings (e.g. permissions). The client looks there first. This file is in `.gitignore`.

**Important:** When you store the API key in the repo (this file or any local config), **do not make the repo public** — it contains private data. Keep the repo private or ensure sensitive files are never committed.

```json
{
  "env": {
    "NODESHUB_API_KEY": "your-api-key-here"
  }
}
```

**Option B — User config (outside repo):**  
Add to `~/.claude/settings.json` on your machine. Key is never in the project.

Restart Claude Code after adding the key.

## Security

- **Never commit the API key** to the repo or put it in any file under the project (e.g. `.env`, `settings.json` in the workspace).
- Use **environment variables only**: `~/.claude/settings.json` is in your home directory and is not part of git, so the key stays local.
- The repo uses `.claude/settings.local.json` for local config (key, permissions); it is in `.gitignore`. Do not commit it.

## Verify

```bash
python3 .claude/skills/nod-nodeshub-api/scripts/check_setup.py
```

Expected output:
```
API Key: xxxxxxxx...
Balance: 100 / 100 tokens
Setup OK.
```

## Token Costs

| Endpoint | Cost per request |
|----------|-----------------|
| SERPdata (search) | 1 token |
| Query Fan-out (standard) | 7.5 tokens |
| Query Fan-out (reasoning) | 30 tokens |
| Intent Classifier | 2 tokens |
| Balance / Products / Params | 0 (free) |

## Buy More Tokens

Visit [nodeshub.io](https://nodeshub.io) — credits never expire, no subscription required.
