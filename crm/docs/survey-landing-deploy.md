# SEO Survey Landing Page — Deploy Note

The **Shutters vs burglar bars** survey landing page is a linkable-asset lead
capture: an anonymous page that collects a short survey + contact details into
the CRM, with the promise that results get published once enough responses come
in (the digital-PR hook).

Two pieces ship to production:

## 1. Static landing page (`survey-shutters.html`)

Source file: `crm/frontend/public/survey-shutters.html`

Vite copies everything in `frontend/public/` verbatim into the build output
(`dist/`) — no bundling, no transform. So the file lands at
`dist/survey-shutters.html`.

Deployment: run the existing frontend deploy script (as today):

```bash
/root/deploy-crm-frontend.sh
```

That script runs `npm run build` and rsyncs `dist/` to `/var/www/crm-frontend/`.
Because nginx uses `try_files $uri $uri/ /index.html`, a real file at the web
root is served as-is — no nginx change is required. The page will be available
at `https://dashboard.fortressblinds.co.za/survey-shutters.html`.

## 2. Backend route (`POST /api/survey/submit`)

Source: `crm/backend/routes/survey.py` (registered in `backend/app.py` under
prefix `/api`).

- **No external auth** — the client is resolved server-side (looks up `House of
  Supreme`, falls back to the first client), so the client API key never appears
  in page code.
- Reuses the shared capture pipeline (`backend/lead_capture.capture_lead`) that
  `/api/leads/public` also uses: dedupe → merge/create → history → auto-assign →
  notify.
- `source=WEBSITE`; `source_detail` holds the survey summary, e.g.
  `SEO Survey: shutters-vs-bars — concern=heat, windows=aluminium`; `location`
  is the suburb; UTM params pass through.
- Light in-process rate limit (per IP, sliding 5s window, max ~5 sends).

This ships with the container image — the same way every backend route ships.
The image build + deploy is handled by the existing Coolify redeploy workflow
(`deploy-container.yml`), which verifies `/health` before finishing. No extra
deploy step, no nginx change.

## How to extend the survey questions later

Everything is data-driven and decoupled:

1. **Add a question** → edit `survey-shutters.html`:
   - Add a `<div class="question">` + `<div class="options">` block with radio
     inputs named like `name="myquestion"`.
   - Add the key to the `['concern', 'windows', 'hometype', 'current']` array in
     the inline `answers` collection in the `<script>`.
2. **Backend needs no change** — the route accepts an arbitrary `answers` dict
   and folds every key/value into the `source_detail` summary string. Keys map
   to human labels in `_build_source_detail` via `key=value`.
3. **Redeploy** the frontend (step 1 deployment script) and the backend image.
4. Optionally change the page copy — the CTA, footer promise, and the
   "publish results" hook are all plain HTML/JS in the one file.

## Gotchas

- The page is fully self-contained (inline CSS/JS, no external fonts or CDNs),
  so it works offline and behind the same nginx `try_files` setup.
- The survey is deliberately neutral on bars-vs-shutters. If you change the
  questions later, keep that tone — the asset stays credible as SEO linkable
  content and respects SA home-security realities.
