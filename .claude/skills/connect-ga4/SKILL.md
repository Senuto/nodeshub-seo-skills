---
name: connect-ga4
description: |
  Step-by-step guide to connect Google Analytics 4 so you can use fetch-ga4.js
  and GA4 data (pageviews, sessions, events, traffic sources). Use when user says
  "connect GA4," "set up Google Analytics," "GA4 setup," "connect Analytics,"
  or "how to connect to GA4." No API cost — setup only.
license: MIT
compatibility: "Requires Node.js 18+, googleapis npm package, and Google Cloud Console access"
metadata:
  author: nodeshub
  version: "0.1.0"
allowed-tools: Bash Read Write
---

# Connect with GA4

**First action:** Run the banner so the blue logo and skill name appear in the terminal:
```bash
python3 -c "import sys; sys.path.insert(0,'.claude/skills/nod-nodeshub-api/scripts'); from banner import print_banner; print_banner('Connect GA4')"
```

Then walk the user through connecting Google Analytics 4 so they can run `npm run fetch-ga4` and use analytics data. Do it **step by step**, and at each step ask for a paste or confirmation before continuing.

**Privacy:** Credentials (e.g. GA4 key file in `local/`) are stored in the repo in gitignored paths. **Tell the user: do not make this repo public** if it contains API keys or credential files — keep the repo private or ensure sensitive files stay out of version control.

---

## Step 0: Check if GA4 is already connected

**First**, check whether the GA4 credentials file exists:

- **If `local/ga4-credentials.json` exists**: GA4 is already set up for this repo. **Ask the user:** "GA4 is already connected (credentials file present). Do you want to **change** the current integration (replace with a different Service Account) or **add another** GA4 property/credentials? (Reply: change / add another / no, I'm done.)"
  - If they say **change** → continue with Step 1 (they will create a new Service Account and replace `local/ga4-credentials.json`).
  - If they say **add another** → explain that the current script uses one credentials file; adding another property usually means using the same Service Account and updating the property ID, or they can replace the file to point at a different project. Then continue from Step 4 or Step 5 as needed.
  - If they say **no, I'm done** → confirm and stop.
- **If the file does not exist**: no integration yet → continue with Step 1.

---

## Step 1: Google Cloud project and API

1. Ask the user to open **[Google Cloud Console](https://console.cloud.google.com/)** (not Analytics).
2. Tell them: create or select a project (top bar).
3. In the left menu: **APIs & Services** → **Library**. Search for **Google Analytics Data API** → open it → **Enable**.

**Ask:** "Have you enabled the Google Analytics Data API? Reply yes when done."

---

## Step 2: Service Account

1. In Google Cloud Console: **APIs & Services** → **Credentials**.
2. **Create Credentials** → **Service Account**.
3. **Service account name:** e.g. `ga4-reader`. Click **Create and Continue**. (No role needed — skip optional steps, then **Done**.)
4. Open the new Service Account (click its name). Go to the **Keys** tab.
5. **Add Key** → **Create new key** → **JSON** → **Create**. A JSON file will download.

**Ask:** "Have you downloaded the JSON key file? Reply yes when done."

---

## Step 3: Save the key file in the repo

1. Tell the user to create the folder `local/` in the repo root if it does not exist.
2. Save the downloaded JSON file as:
   ```
   local/ga4-credentials.json
   ```
3. Remind them: `local/` is in `.gitignore`, so the file will not be committed. **Do not make the repo public** — it now contains a private credentials file (even though it is gitignored, keeping the repo private is safer).

**Ask:** "Have you saved the file as `local/ga4-credentials.json`? Reply yes when done."

---

## Step 4: Service Account email — paste here

1. Tell the user to open `local/ga4-credentials.json` and find the field **`client_email`**. It looks like: `something@project-id.iam.gserviceaccount.com`.
2. **Ask them to paste the Service Account email here** (they can redact the middle part if they prefer, but you need the full email for the next step).

When they paste it, confirm and go to Step 5.

---

## Step 5: Add the Service Account in Google Analytics

1. Ask the user to open **[Google Analytics](https://analytics.google.com/)** (analytics.google.com, not Cloud Console).
2. Select the **property** (GA4 property) they want to connect.
3. Open **Admin** (gear icon, bottom left) → **Property access management**.
4. Click the **+** button → **Add users**.
5. They should paste the **Service Account email** (the one from Step 4) into the email field.
6. Role: **Viewer** (sufficient for read-only data access).
7. Click **Add**.

**Ask:** "Have you added the Service Account as a user in GA4? Reply yes when done."

---

## Step 6: Get the GA4 Property ID

1. Ask the user to stay in **[Google Analytics](https://analytics.google.com/)**.
2. Open **Admin** → **Property settings** → **Property details**.
3. Copy the **Property ID** (a numeric ID, e.g. `1234567890`).
4. **Ask them to paste the Property ID here.**

When they paste it, update `scripts/fetch-ga4.js` → `CONFIG.propertyId` with the value.

---

## Step 7: Verify

Run:

```bash
npm install
npm run fetch-ga4
```

If they use a different property or paths, point them to edit `scripts/fetch-ga4.js` (`CONFIG.propertyId`, `CONFIG.outputDir`). Data is written to `knowledge/metrics/analytics/` by default.

**Ask:** "Did `npm run fetch-ga4` run without errors? If you see any error, paste it here."

---

## Summary

- **Google Cloud Console** (console.cloud.google.com): enable Google Analytics Data API, create Service Account, download JSON key.
- **Google Analytics** (analytics.google.com): add the Service Account email as a Viewer, note the Property ID.
- Key file in repo: `local/ga4-credentials.json` (gitignored). **Keep the repo private** — do not publish it publicly when it contains credentials.

For more detail (e.g. metrics, dimensions, filters), see the `scripts/fetch-ga4.js` script or the [Google Analytics Data API docs](https://developers.google.com/analytics/devguides/reporting/data/v1).
