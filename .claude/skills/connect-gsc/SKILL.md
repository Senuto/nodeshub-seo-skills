---
name: connect-gsc
description: |
  Step-by-step guide to connect Google Search Console so you can use fetch-gsc.js
  and GSC data (queries, impressions, clicks). Use when user says "connect GSC,"
  "set up Google Search Console," "GSC setup," "connect Search Console," or
  "how to connect to GSC." No API cost — setup only.
compatibility: "Requires Node.js 18+, googleapis npm package, and Google Cloud Console access"
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Connect with GSC

**First action:** Run the banner so the blue logo and skill name appear in the terminal:
```bash
python3 -c "import sys; sys.path.insert(0,'.claude/skills/nod-nodeshub-api/scripts'); from banner import print_banner; print_banner('Connect GSC')"
```

Then walk the user through connecting Google Search Console so they can run `npm run fetch-gsc` and use search performance data. Do it **step by step**, asking for confirmation before continuing.

## ⛔ CRITICAL SECURITY RULE — NEVER ASK THE USER TO PASTE CREDENTIALS INTO CHAT

Anything the user types into the chat leaves their machine — it's sent to the LLM provider, written to local session logs (`~/.claude/projects/<slug>/*.jsonl`) in plain text, and may appear in telemetry, backups, or IDE sync. This applies to the **contents of the JSON key file** (private key inside it is a secret). It also applies to the Service Account `client_email` — while that email alone is not critical, combined with the private key in logs/backups it lets the holder call Google APIs under the user's project.

You MUST:
- Never ask the user to paste the contents of `gsc-credentials.json` into chat.
- Never ask the user to paste the `client_email` into chat. Read it yourself from `local/gsc-credentials.json` once the user saves the file there (see Step 4).
- If the user pastes the key file contents anyway, stop, refuse to use it, tell them to revoke that Service Account key in Google Cloud Console (IAM & Admin → Service Accounts → Keys → delete the leaked key) and create a new one before continuing.

**Privacy:** The key file `local/gsc-credentials.json` is stored in a gitignored path. **Tell the user: do not make this repo public** if it contains the file — keep the repo private or ensure sensitive files stay out of version control.

---

## Step 0: Check if GSC is already connected

**First**, check whether the GSC credentials file exists:

- **If `local/gsc-credentials.json` exists**: GSC is already set up for this repo. **Ask the user:** "GSC is already connected (credentials file present). Do you want to **change** the current integration (replace with a different Service Account) or **add another** GSC property/credentials? (Reply: change / add another / no, I'm done.)"
  - If they say **change** → continue with Step 1 (they will create a new Service Account and replace `local/gsc-credentials.json`).
  - If they say **add another** → explain that the current script uses one credentials file; adding another property usually means using the same Service Account and adding it as a user in the other GSC property, or they can replace the file to point at a different project. Then continue from Step 4 or Step 5 as needed.
  - If they say **no, I'm done** → confirm and stop.
- **If the file does not exist**: no integration yet → continue with Step 1.

---

## Step 1: Google Cloud project and API

1. Ask the user to open **[Google Cloud Console](https://console.cloud.google.com/)** (not Search Console).
2. Tell them: create or select a project (top bar).
3. In the left menu: **APIs & Services** → **Library**. Search for **Google Search Console API** → open it → **Enable**.

**Ask:** "Have you enabled the Google Search Console API? Reply yes when done."

---

## Step 2: Service Account

1. In Google Cloud Console: **APIs & Services** → **Credentials**.
2. **Create Credentials** → **Service Account**.
3. **Service account name:** e.g. `gsc-reader`. Click **Create and Continue**. (No role needed — skip optional steps, then **Done**.)
4. Open the new Service Account (click its name). Go to the **Keys** tab.
5. **Add Key** → **Create new key** → **JSON** → **Create**. A JSON file will download.

**Ask:** "Have you downloaded the JSON key file? Reply yes when done."

---

## Step 3: Save the key file in the repo

1. Tell the user to create the folder `local/` in the repo root if it does not exist.
2. Save the downloaded JSON file as:
   ```
   local/gsc-credentials.json
   ```
3. Remind them: `local/` is in `.gitignore`, so the file will not be committed. **Do not make the repo public** — it now contains a private credentials file (even though it is gitignored, keeping the repo private is safer).

**Ask:** "Have you saved the file as `local/gsc-credentials.json`? Reply yes when done."

---

## Step 4: Read the Service Account email from the file

Once the user confirms the key file is at `local/gsc-credentials.json`, **read the `client_email` yourself** — do not ask the user to paste it:

```bash
python3 -c "import json; print(json.load(open('local/gsc-credentials.json'))['client_email'])"
```

Show the email to the user and tell them they will paste it into Google Search Console in the next step (that's a Google UI field, not this chat).

---

## Step 5: Add the Service Account in Google Search Console

1. Ask the user to open **[Google Search Console](https://search.google.com/search-console)** (search.google.com, not Cloud Console).
2. Select the **property** (domain or URL prefix) they want to connect.
3. Open **Settings** (gear icon, bottom left) → **Users and permissions** → **Add user**.
4. They should paste the **Service Account email** (the one from Step 4) into the email field.
5. Role: **Owner** or **Full** (GSC has no read-only role; Full is fine for data access).
6. Click **Add**.

**Ask:** "Have you added the Service Account as a user in GSC? Reply yes when done."

---

## Step 6: Verify

Run:

```bash
npm install
npm run fetch-gsc
```

If they use a different site or paths, point them to edit `scripts/fetch-gsc.js` (`CONFIG.siteUrl`, `CONFIG.outputDir`). Data is written to `knowledge/metrics/seo/` by default.

**Ask:** "Did `npm run fetch-gsc` run without errors? If you see any error, paste it here."

---

## Summary

- **Google Cloud Console** (console.cloud.google.com): enable API, create Service Account, download JSON key.
- **Google Search Console** (search.google.com/search-console): add the Service Account email as a user.
- Key file in repo: `local/gsc-credentials.json` (gitignored). **Keep the repo private** — do not publish it publicly when it contains credentials.

For more detail (e.g. filters, dimensions), see `tools/integrations/google-search-console.md`.
