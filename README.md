# Airgap.AI — redesign wired to a real backend

A circuit breaker / firewall for autonomous AI agents. The polished Claude
Design console (the redesign) now gets every ALLOW / APPROVE / BLOCK decision
from a real **stateless Flask service** instead of deciding in the browser.

```
airgap-project/
├── backend/
│   ├── app.py              # Flask policy service  (GET / , POST /evaluate)
│   ├── requirements.txt
│   └── tests/test_app.py   # 14 tests, all passing
├── frontend/
│   ├── airgap-console.html # the redesign (editable Claude Design source) — WIRED
│   └── support.js          # Claude Design runtime (renders the console)
├── run.sh                  # starts both with one command
└── README.md
```

---

## Run it

```bash
./run.sh
# then open  http://localhost:8000/airgap-console.html
```

Or manually, in two terminals:

```bash
# terminal 1 — backend
cd backend && pip install -r requirements.txt && python app.py

# terminal 2 — frontend
cd frontend && python -m http.server 8000
#   open http://localhost:8000/airgap-console.html
```

A small badge in the bottom-left shows **● BACKEND LIVE** (green) when the
console is talking to Flask. Stop the backend and it flips to **● BACKEND
OFFLINE · local fallback** (amber) — the console keeps running on an in-browser
copy of the rules so a live demo never dies.

> The frontend loads React from unpkg via `support.js`, so it needs internet in
> the browser. The decision logic is your backend; only the UI framework is CDN.

---

## How the wiring works

The redesign already had the policy rules running in the browser. The change is
small and surgical — the decision now crosses the network:

```js
// frontend/airgap-console.html  (inside the dc-script)
async function evaluate(a){
  try{
    const r = await fetch(API_BASE + '/evaluate', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ action: a, context: buildContext() })
    });
    if(!r.ok) throw new Error('HTTP ' + r.status);
    setBackend(true); return await r.json();   // { verdict, reason, tags, hi }
  }catch(e){ setBackend(false); return evaluateLocal(a); }  // offline fallback
}
// context = { tokensSpent, apiCalls, recentTargets:[...] }
```

`process()` and the approval-card **Re-evaluate** handler now `await` it. Nothing
else in the UI changed — the stream, fleet, rings, approvals drawer, kill switch
and theme toggle all behave exactly as designed.

Point the console at a deployed backend by setting `window.AIRGAP_API` (or the
component's `apiBase` prop) instead of `http://localhost:5000`.

---

## The backend (matches the airgap.plain spec)

`GET /` → `{"status":"ok","service":"airgap"}`

`POST /evaluate` body:
```json
{ "action":  {"type":"DB_QUERY","target":"analytics_read","payload":{},"tokens":120},
  "context": {"tokensSpent":200,"apiCalls":3,"recentTargets":["analytics_read"]} }
```
→ `{"verdict":"ALLOW","reason":"Within policy.","tags":[],"hi":false}`

**Rules, first match wins:** destructive-on-prod → loop/runaway → token budget →
API budget → deny-list → default allow. Limits are constants at the top of
`app.py` (`TOKEN_LIMIT`, `API_LIMIT`, `LOOP_THRESHOLD`). Stateless: the frontend
owns the meters and sends them as context every call.

Run the tests:
```bash
cd backend && python -m unittest discover -v   # 14 passing
```

Verified end-to-end — each demo button maps to the right verdict:

| Button | Verdict |
|--------|---------|
| Destructive write | **BLOCK** (destructive on prod) |
| Runaway loop | **BLOCK** (loop pattern) |
| Spike token budget | **APPROVE** (budget threshold) |
| normal stream | **ALLOW** |

---

## Where we are / what's next

1. ✅ Backend built, tested (14/14), spec-complete.
2. ✅ Redesign wired to the backend with offline fallback + live status badge.
3. ⬜ **Deploy the backend** (Render / Railway / Fly), set `window.AIRGAP_API` to its URL.
4. ⬜ Optional hardening: auth on `/evaluate`, per-client rate limiting, and
   audit-logging every verdict (the redesign already has an Audit Log view to feed).
