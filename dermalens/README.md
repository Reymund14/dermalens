# DermaLens

AI-based mobile skin image pre-screening and skincare information system for ICONIC Aesthetic Clinic, built from the *DermaLens — Full Development Roadmap*.

> DermaLens provides general skincare information and a visual pre-screening of cosmetic skin concerns. It does not diagnose, treat, or rule out any disease.

## What is here

| Path | What it is | Status |
| --- | --- | --- |
| `apps/mobile` | React Native app (Expo SDK 58, TypeScript). Patients: onboarding, boundary, consent, profile, 5-step intake, guided capture, results, routine, referral, PDF summary, history, settings. Clinic staff, dermatologists and admins: their own workspaces (see below) | Working; typechecks; all four roles run in a browser |
| `apps/web` | Desktop web app (React + Vite, TypeScript) for all four roles: patients run checks and see results; clinic staff work the inbox; dermatologists review cases, sign off rules and see agreement; admins run the dashboard, accounts, catalog, rules, models, jobs and audit log | Working; typechecks; every role runs in a browser |
| `services/api` | FastAPI core API: auth (argon2id, 15-min JWT, rotating refresh tokens, email verification, password reset, lockout, rate limits), consent, intake, capture sessions with signed upload URLs, triage, routines, PDF summary, clinic, dermatologist and admin endpoints, notifications, audit log, security headers, health check | Working; 32 tests on SQLite **and** PostgreSQL 16 |
| `services/inference` | Inference service: server-side quality re-check, EXIF stripping, calibration / thresholds / uncertainty band / OOD flag, ONNX Runtime loader with checksum check | Working with a **stub model** (see below); 9 tests |
| `packages/rules` | Pure-function rules package: 7-rule triage cascade and deterministic AM/PM recommendation engine with allergen, contraindication and conflict checks | Working; 38 tests incl. 400 property-based cases |
| `services/api/migrations/001_init.sql` | PostgreSQL 16 schema (37 tables), generated from the ORM; `002_accounts.sql` upgrades a database made by v0.1 (`start.sh` does this automatically) | Applied cleanly to PostgreSQL 16 |
| `ml/evaluate.py` | Level 2 evaluation: per-label P/R/F1, AUROC, AUPRC, ECE, QWK, Hamming loss, exact match, refer-out recall, Fitzpatrick fairness gap, bootstrap CIs by person, pass/fail against roadmap targets | Working; 3 tests |
| `e2e/web_flow.py`, `e2e/roles_flow.py`, `e2e/webapp_flow.py` | Playwright scripts: the mobile app's web build (patient, then staff, dermatologist, admin) and the desktop web app (all four roles) | Pass |
| `infra/docker-compose.yml` | PostgreSQL + inference + API | Written, not built here (no Docker daemon available) |

## Two things that are placeholders on purpose

1. **The AI model is a stub.** `StubClassifier` scores images from simple colour and texture statistics so the app, triage and routines can be built and demoed (roadmap build step 6). It is **not** a trained model and must not be used with real patients. Train the ConvNeXt model from the roadmap, export it to ONNX with the graph contract in `services/inference/dermalens_inference/classifier.py` (`images [V,3,384,384]` → `presence [4]`, `grades [4,2]`, `refer_out [1]`, optional `embedding`), register it in `model_versions` with its evaluation report, and set `DERMALENS_MODEL_PATH`, `DERMALENS_MODEL_CONFIG` and `DERMALENS_MODEL_SHA256`. Nothing downstream changes.
2. **The product catalog is fictional.** The 22 seed products are "Sample Catalog" items with `SAMPLE-0001`-style numbers so the engine can be tested. Replace them with real products whose Philippine FDA cosmetic notification you have looked up on the FDA verification portal, using `POST /api/v1/admin/products` then `POST /api/v1/admin/products/{id}/verify` with the evidence file. Products with drug-regulated actives (tretinoin, adapalene, hydroquinone, clindamycin and others) are refused at ingest, and any INCI term not in the synonym table blocks listing until a reviewer maps it.

## Deploy it

See [DEPLOY.md](DEPLOY.md): Supabase (database + private Storage bucket), Render (API, desktop web app and the Expo web build) and Expo EAS (Android app), all on free plans.

## Run it

Requirements: Python 3.12+, Node 22.13+ (Expo SDK 58).

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
./test.sh                     # all Python suites
./dev.sh                      # API on http://localhost:8000, OpenAPI docs at /docs
```

`dev.sh` generates throwaway secrets for the run, seeds the database and prints three development accounts (admin, clinic staff and dermatologist). Patients sign up in the app.

Mobile app:

```bash
cd apps/mobile
npm install
EXPO_PUBLIC_API_URL=http://<your-computer's-LAN-IP>:8000 npx expo start   # scan with Expo Go
npx expo start --web                                                       # browser demo (choose photos instead of camera)
EXPO_PUBLIC_API_URL=https://api.your-clinic.example eas build -p android --profile production
```

A native release build refuses to start without `EXPO_PUBLIC_API_URL`, and that URL must be HTTPS. Set it as an EAS environment variable for the `production` profile in `eas.json`; never ship `http://localhost`.

Desktop web app (all roles):

```bash
cd apps/web
npm install
VITE_API_URL=http://localhost:8000 npm run dev      # http://localhost:5173
```

With PostgreSQL instead of SQLite, set `DATABASE_URL=postgresql+psycopg://user:pass@host/dermalens`, apply `services/api/migrations/001_init.sql` then `002_accounts.sql` (or let `python -m app.schema_upgrade` add the new columns), then create the first admin and seed with `ADMIN_EMAIL=you@clinic.example ADMIN_PASSWORD='a-long-password' python -m app.seed`. Regenerate the SQL after model changes with `python -m app.dump_schema > migrations/001_init.sql`.

End-to-end browser check (API on :8000, `npx expo export --platform web` served on :8081):

```bash
python e2e/web_flow.py --images <dir with front.jpg left45.jpg right45.jpg> --shots ./shots
python e2e/roles_flow.py --shots ./shots      # staff, dermatologist, admin; run after web_flow.py
python e2e/webapp_flow.py --app http://localhost:4173 --images <dir> --shots ./shots   # desktop web app, all roles (npm run build && npx vite preview)
```

## User accounts and what each can do

Everyone signs in on the same screen; the app opens the home screen for the account's role. The API enforces every rule below, not just the app.

| Role | Gets an account by | Home screen | Can do |
| --- | --- | --- | --- |
| Patient | Signing up in the app | Check history | Run checks, see results and routines, make and share a PDF summary, export or delete their data |
| Clinic staff | Admin creates it | Clinic inbox | See summaries patients shared with ICONIC (initials only, plus the photos), open a QR link, track follow-up (new, contacted, booked, no response, closed), add a staff note, mark reviewed, download the PDF |
| Dermatologist | Admin creates it | Review queue | Everything clinic staff can see, plus an independent review of each case (own route, agree or not with each finding, note), the agreement figures (route agreement, missed referrals, referral sensitivity, per-concern agreement), and sign-off of the current triage and rule-set version |
| Admin | Admin creates it | Dashboard | Usage counts, staff accounts (create, disable, reset password, change role; never their own), product catalog (FDA verification, delisting), rules (adding one bumps the version and voids the sign-off), model versions, retention and re-verification jobs, audit log |

Disabled accounts cannot log in or refresh, and requests with an existing token are refused at once. Staff never see a patient's name or email; the audit log shows patients only as "patient". The per-role roadmap is in the *DermaLens Role-Based Access Roadmap* document.

Development accounts (created only when `SEED_DEV_ACCOUNTS=1`; `./dev.sh` sets it, and it must stay off in production):

| Role | Email | Password |
| --- | --- | --- |
| Admin | admin.dev@example.com | AdminPass!2026 |
| Clinic staff | staff.dev@example.com | StaffPass!2026 |
| Dermatologist | derm.dev@example.com | DermPass!2026 |

## Running it day to day

These are built in so the system can run without a developer watching it:

| Feature | What it does |
| --- | --- |
| Forgot password | "Forgot your password?" on the sign-in page emails a link that works once, for 30 minutes. Using it signs out every device. The answer is the same whether or not the email has an account. |
| Email verification | New patients get a confirmation link (valid 7 days) and see a banner until they use it. Staff accounts made by an admin count as confirmed. |
| My account | Every role can change their password; other devices are signed out. |
| Lockout and rate limits | 5 wrong passwords lock an account for 15 minutes (an admin password reset unlocks it, and the Staff accounts page shows "Locked"). Sign-in, sign-up and email endpoints are rate limited per address and per email (HTTP 429 with `Retry-After`). Limits are kept in memory, per API process. |
| Notifications | Sidebar counters: new cases in the clinic inbox (orange when one is urgent), cases waiting in the dermatologist's queue, products due for FDA re-verification and locked accounts for admins. With `CLINIC_NOTIFY_EMAIL` set, the clinic also gets an email when a patient shares a summary; it contains no patient details. |
| Progress | A patient's second and later checks show "Since your last check": each concern looks better, about the same or more noticeable, with a reminder that photo-based changes are estimates. |
| Safer startup | With `DERMALENS_ENV=production` the API refuses to start on missing secrets, Supabase not configured, CORS `*`, or SQLite, and names what to fix. |
| Health check | `/health` checks the database and returns 503 when it is unreachable, so the host restarts or alerts. |
| Security headers | nosniff, no framing, no referrer, `Cache-Control: no-store` on API answers, HSTS in production, a request id on every response; unexpected errors return a plain message instead of a stack trace. |
| Error pages | Unknown addresses show "Page not found"; a page that crashes shows a recovery message instead of a blank screen. |

Email goes out through any SMTP provider (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM`). Without `SMTP_HOST`, each email is written to the API log, which is how development and the e2e test read the links. Only the fact that an email was sent is stored (`email_log`), never its body. The phone app has no forgot-password screen; patients can use the web app's link, and the reset applies to both.

## How a check works

1. The app records intake (concerns, every red-flag question, allergies, current routine, lifestyle). An urgent "yes" shows the urgent-care screen at once.
2. It opens a capture session and gets three signed upload URLs (5-minute expiry). Each photo is re-encoded on the phone (drops EXIF), uploaded, re-encoded again on the server, and quality-checked immediately so the user can retake.
3. Submit runs inference, then the triage cascade (`packages/rules/dermalens_rules/triage.py`), then the routine builder (`recommend.py`). If server quality fails, the user gets one retake; a second failure routes to a dermatologist.
4. Every inference, triage decision and routine is stored with the model version, rule-set version, catalog snapshot time and an input hash that proves the routine is reproducible.
5. The patient can download a two-page PDF summary or, with the "share with ICONIC" consent, send it to clinic staff. Staff open it via the QR code only after logging in, and every view is written to `audit_log`.

## Differences from the roadmap

- **Live capture checks.** The roadmap's six live checks with auto-shutter need `react-native-vision-camera` frame processors and MediaPipe Face Mesh in a development build. This version uses Expo's camera (runs in Expo Go) and checks each photo on the server right after it is taken, with plain-language retake tips. The server checks are resolution, face/skin presence, sharpness, exposure and even lighting; head pose is not checked yet.
- **Background jobs** use FastAPI `BackgroundTasks` instead of Celery + Redis. Swap in Celery when load requires it; `pipeline.process_session` is the task body.
- **Object storage** is local disk in development, or a private Supabase Storage bucket when `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are set. Both are exposed through the same `app/storage.py` (put/get/delete) functions.
- **Ingredient and product ids** are readable slugs (`niacinamide`, `p-se-vitc`) instead of UUIDs, which makes rule tables reviewable.
- **Clinic portal.** The roadmap's optional web portal is `apps/web`, which also lets patients run checks from a computer. Staff, dermatologists and admins can use either it or the phone app.
- **Rate limits** live in each API process's memory. With more than one instance, move them to Redis or the proxy.
- **Grad-CAM heat maps** need the trained model; the summary says they are not available for the stub.
- **MFA for staff** has a column (`users.mfa_secret_enc`) but no enrolment flow yet. It is phase 2 in the role roadmap.

## Before any pilot

- Train and evaluate the real model; `python ml/evaluate.py predictions.csv` reports every Level 2 metric against the roadmap targets.
- Have the consulting dermatologist sign off the red-flag list and triage rules, and the pharmacist or cosmetic chemist sign off the conflict and contraindication tables in `packages/rules/dermalens_rules/seed.py`.
- Replace the sample catalog with verified products.
- Set `DERMALENS_ENV=production` and real secrets: `JWT_SECRET` and `DATA_KEY` (Fernet key). Startup fails if either is missing; both are required in every environment; there are no default secrets.
- Set `PUBLIC_BASE_URL` to the public HTTPS origin (share QR links carry a token), `PUBLIC_WEB_URL` to the web app's HTTPS origin (emailed reset and verification links point here), and `CORS_ORIGINS` to the app's explicit HTTPS origin(s); production startup refuses wildcards or HTTP. Run uvicorn with `--proxy-headers` so auth rate limiting sees each client IP, not the proxy's. Run one API instance: the rate limiters are in process memory.
- Configure SMTP (`SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM`) so password resets and verification links reach people; without it, links only appear in the API log.
- Create a private Supabase Storage bucket (default name `dermalens`) and set `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` and optionally `SUPABASE_STORAGE_BUCKET`. Production startup fails without the first two; local development keeps using `./storage`.
- Keep `SEED_DEV_ACCOUNTS=0`, and keep the database port firewalled (the compose file no longer publishes it).
- Complete the DPIA, and get a written opinion on whether the app is a medical device under FDA Philippines rules.
