# Deploying Airgap.AI on Vercel

One project, one domain. Vercel serves the console (`index.html`) as static files
and runs the policy engine (`api/evaluate.py`) as a serverless function at
`/api/evaluate` — same origin, no CORS, **no dependencies** (pure Python stdlib,
so the build can't fail on packages).

```
airgap-vercel/
├── index.html        # the console (served at / )
├── support.js        # Claude Design runtime
└── api/
    └── evaluate.py   # the policy engine  →  /api/evaluate
```

There is **nothing to put in Environment Variables** — no API keys, no secrets.

---

## Easiest: deploy from the Vercel website

### Step 1 — Put these files at the ROOT of a GitHub repo
This is the mistake that broke the Render build: the files must be at the repo
**root**, not inside a sub-folder. So `index.html` and the `api/` folder must sit
directly at the top of the repo.

- New repo: https://github.com/new  → name it `airgap` → Create.
- **Add file → Upload files**, then drag in **the contents** of `airgap-vercel/`:
  `index.html`, `support.js`, and the **`api`** folder. Commit.
- Sanity check: the repo's front page should show `index.html` and `api/` at the
  top level (not an `airgap-vercel/` folder wrapping them).

### Step 2 — Import into Vercel
1. https://vercel.com → sign in with GitHub.
2. **Add New… → Project** → pick the `airgap` repo → **Import**.
3. Leave everything at defaults. Framework Preset: **Other**. No build command,
   no output dir, no env vars.
4. Click **Deploy**.

### Step 3 — Open it
Vercel builds in ~30–60s and gives you a URL like
`https://airgap.vercel.app`. Open it — the console loads and the bottom-left
badge should read **● BACKEND LIVE**. Click **Destructive write** / **Runaway
loop** to see the deployed function intercept actions.

---

## Alternative: Vercel CLI (also gives you local dev)

```bash
npm i -g vercel
cd airgap-vercel
vercel            # first run: links the project, then deploys a preview
vercel --prod     # promote to production

# local dev that mirrors prod exactly (UI + /api/evaluate together):
vercel dev        # serves on http://localhost:3000
```

---

## Verify

- `https://<your-url>/` → the console.
- `https://<your-url>/api/evaluate` (GET) → `{"status":"ok","service":"airgap"}`.
- Badge says **BACKEND LIVE**; demo buttons get intercepted.

---

## Notes

- **If `/api/evaluate` ever 404s:** make sure the file is at `api/evaluate.py` at
  the repo root. Vercel auto-detects any `.py` in `/api` as a Python function —
  no `vercel.json` needed.
- **Point the UI at a different backend** (not needed here) by setting
  `window.AIRGAP_API="https://other-host"`; it will then call
  `https://other-host/evaluate`.
- The console loads React from unpkg via `support.js`, so the browser needs
  internet — but the *decisions* are 100% your Vercel function.
