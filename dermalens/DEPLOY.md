# Deploying DermaLens

This guide puts DermaLens online for a capstone demo or a small pilot, at no cost:

| Part | Where | Cost |
| --- | --- | --- |
| Database and private file storage | [Supabase](https://supabase.com) free plan | Free, no card. PostgreSQL plus a private Storage bucket |
| API (FastAPI, Docker) | [Render](https://render.com) free web service | Free. Sleeps after 15 minutes idle; first request after that takes about a minute |
| Web app for all roles (`apps/web`, desktop browsers) | Render static site | Free |
| Mobile app's browser version (`apps/mobile`) | Render static site | Free |
| Android app | [Expo EAS Build](https://expo.dev) free plan, as an APK you install directly | Free, limited number of builds per month |
| iPhone app | EAS Build + TestFlight | Needs a paid Apple Developer account |

Photos and PDFs go into a **private Supabase Storage bucket**, because Render's free disk is wiped on every restart. Patient names, notes, photos and PDFs are encrypted with `DATA_KEY` before they are stored.

Before you start, put the code in a GitHub repository (Render deploys from GitHub). From the repository root — the folder containing `render.yaml` and `dermalens/`:

```bash
git init && git add -A && git commit -m "DermaLens" && git branch -M main
# create an empty repo on github.com, then:
git remote add origin https://github.com/<you>/dermalens.git
git push -u origin main
```

## 1. Create the database (Supabase)

1. Sign up at supabase.com and create a project. Pick the region closest to your clinic (Singapore for the Philippines).
2. In **Project Settings → Database → Connection strings**, choose the **Session pooler** and copy its URL. Change the scheme to `postgresql+psycopg://`, e.g.
   `postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`.
   Keep it private.

You do not need to create tables. `start.sh` runs the schema upgrade on every API start.

In the same Supabase project, create a **private** Storage bucket named `dermalens`. In Project Settings → API, copy the project URL (`SUPABASE_URL`) and the service role key (`SUPABASE_SERVICE_ROLE_KEY`). Keep the service key secret; it bypasses row-level security.

## 2. Make two secrets

On your own computer (with the project's Python environment active, or any Python that has `cryptography`):

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

That is your **DATA_KEY**. It encrypts patient names, notes, photos and PDFs. Store it somewhere safe: if you lose it, that data cannot be read again. Also choose an **admin password** of at least 10 characters.

## 3. Deploy the API and the web app (Render)

1. Sign up at render.com with your GitHub account.
2. Click **New → Blueprint**, pick your `dermalens` repository. Render reads `render.yaml` at the repository root and proposes three services: `dermalens-api`, `dermalens-app` (the desktop web app) and `dermalens-web` (the mobile app's browser version). You can delete `dermalens-web` if you only want the desktop web app plus the phone app.
3. Fill in the values it asks for:

   | Variable | Value |
   | --- | --- |
   | `DATABASE_URL` | the Supabase session pooler URL from step 1 |
   | `DATA_KEY` | the key from step 2 |
   | `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | the project URL and service key from step 1; the bucket is `dermalens` |
   | `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_NAME` | your real admin login |
   | `CORS_ORIGINS` | `https://dermalens-app.onrender.com,https://dermalens-web.onrender.com` (both web addresses, comma-separated; fix them after step 4 if Render gave different ones) |
   | `PUBLIC_BASE_URL` | the API's own HTTPS address; share QR links in patient PDFs point here |
   | `CLINIC_CONTACT` | ICONIC's address, phone and booking link, as it should appear on the PDF |
   | `EXPO_PUBLIC_API_URL` and `VITE_API_URL` | `https://dermalens-api.onrender.com` (the API's address, for each web app; fix it after step 4 if different) |
   | `PUBLIC_WEB_URL` | `https://dermalens-app.onrender.com` (the web app's address; password-reset and verification emails link here) |
   | `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM` | Your email provider's SMTP details, for password resets and email confirmation. Any provider works, for example Brevo's free plan, or Gmail with an app password (`smtp.gmail.com`). Leave `SMTP_HOST` empty to skip email: links then appear only in the API's log on Render. |
   | `CLINIC_NOTIFY_EMAIL` | Optional. The clinic address that gets a short "new summary shared" email (no patient details). |

   Set `JWT_SECRET` and `DATA_KEY` yourself — there are no development defaults. `DERMALENS_ENV` is `production`, which makes the API refuse to start if a setting is unsafe (missing secrets, Supabase not configured, `CORS_ORIGINS` left as `*`, or SQLite); the Render log names the setting to fix. `SEED_DEV_ACCOUNTS` is `0`; create staff accounts from the admin dashboard.
4. Click **Apply**. The API build takes several minutes the first time. When both services show **Live**, note their addresses. If they differ from the ones you typed, update `CORS_ORIGINS` (on the API) and `VITE_API_URL` / `EXPO_PUBLIC_API_URL` (on the web apps), then redeploy the web apps so the new address is built in.
5. Check it:
   - `https://<api-address>/health` shows `"ok":true` and `"database":"ok"`. Render also uses it to restart the API if the database becomes unreachable.
   - On the sign-in page, use **Forgot your password?** with your admin email. The email should arrive (or, without SMTP, the link appears in the API's log on Render).
   - `https://<api-address>/docs` shows the API documentation.
   - The `dermalens-app` address opens the DermaLens web app. Sign in with your admin email; you should land on the admin dashboard. Clinic staff, dermatologists and patients use the same address and land on their own pages.

The web version must be served over HTTPS for the camera to work in a phone's browser. Render does this for you.

## 4. Build the Android app (Expo EAS)

1. Set `EXPO_PUBLIC_API_URL` for the EAS build profile (release builds refuse to start without it, and it must be HTTPS):
   ```bash
   npx eas-cli env:add -e production EXPO_PUBLIC_API_URL=https://dermalens-api.onrender.com
   ```
2. Then:

   ```bash
   cd apps/mobile
   npm install
   npx eas-cli login            # free Expo account
   npx eas-cli build:configure  # links the project to your Expo account
   npx eas-cli build --platform android --profile preview
   ```

3. When the build finishes, Expo shows a link and a QR code. Open it on an Android phone, download the APK and install it (allow "install from unknown sources" when asked). That APK is what you hand to testers or show at your defense.

For the Google Play Store, use `--profile production` (it builds an AAB) and upload it in the Play Console; that needs a one-time Google Play developer registration fee. For iPhone, `npx eas-cli build --platform ios` needs a paid Apple Developer account, and testers install through TestFlight.

## 5. After deploying

- **First request is slow on the free plan.** The API sleeps after 15 minutes without traffic. Open `/health` a minute before a demo to wake it. A paid Render plan keeps it awake.
- **Updating.** Push to GitHub; Render redeploys both services automatically. The API adds any new database columns itself when it starts (`python -m app.schema_upgrade`), so an existing Supabase database keeps its data. Rebuild the APK only when the app's code changes.
- **Staff accounts.** Create real clinic staff and dermatologist accounts in the admin screen (Staff accounts → Add an account).
- **Locked out?** Five wrong passwords lock an account for 15 minutes. An admin can reset a staff password in Staff accounts, which also unlocks it; anyone can use Forgot your password.
- **Uptime.** Point a free uptime monitor (for example UptimeRobot) at `/health`. It warns you when the API or database is down, and on the free plan its pings also keep the API awake.
- **Backups.** Free plans keep little or no backup history. If this runs a real pilot, export the database regularly (Supabase's backup tools, or `pg_dump` with the session pooler URL) or move to a paid plan. Keep `DATA_KEY` with the backup: without it, encrypted photos and PDFs cannot be read.
- **Creating or resetting an admin later.** From your computer, in the project folder with its Python environment active:
  `cd services/api && DATABASE_URL='<Supabase session pooler URL>' ADMIN_PASSWORD='new password here' PYTHONPATH=../../packages/rules:../../services/inference:. python -m app.create_admin someone@clinic.ph "Name"`

## Before real patients

The hosting above is fine for a capstone demo. Before ICONIC uses it with real patients, the "Before any pilot" list in README.md still applies: a trained and evaluated model in place of the stub, a verified product catalog, dermatologist sign-off of the rules, `SEED_DEV_ACCOUNTS=0`, and the data-privacy steps (DPIA, NPC registration if required). Patient photos are health-related personal information under the Data Privacy Act, so confirm with the clinic where the data may be hosted; Supabase's region choice and the private bucket policy matter here.

## Other hosts

The API is a standard Docker image (`services/api/Dockerfile`, build from the repository root) that reads its settings from environment variables and listens on `$PORT`, so it also runs on Railway, Fly.io, Google Cloud Run, Azure Container Apps or a plain VPS. On a VPS, `infra/docker-compose.yml` runs PostgreSQL, the API and the inference service together. Both web apps are plain static files (`apps/web`: `npm run build` → `dist/`, with `VITE_API_URL` set; `apps/mobile`: `npx expo export --platform web --clear` → `dist/`). The desktop web app uses `#/` links, so it needs no rewrite rules at all. The mobile app's browser version can go on Netlify or Cloudflare Pages (a `_redirects` file for both is already included) or Vercel (add a rewrite of all paths to `/index.html`).
