# Deploy Kinetic API to Railway

Step-by-step guide for deploying `packages/api` to Railway.

---

## Prerequisites

- Railway account at [railway.app](https://railway.app)
- GitHub repo connected to Railway (or you can deploy from CLI)
- All env vars from your local `.env` ready to paste

---

## Step 1: Create a New Project in Railway

1. Go to **railway.app/dashboard**
2. Click **"New Project"**
3. Select **"Deploy from GitHub Repo"**
4. Pick the **kinetic** repo
5. Railway will ask which directory — set the **root directory** to `packages/api`

> If Railway doesn't ask for a root directory during setup, you'll set it in Step 2.

---

## Step 2: Configure Build Settings

1. In your new service, click **Settings** (gear icon)
2. Under **Source**:
   - **Root Directory**: `packages/api`
   - **Branch**: `main` (or your deploy branch)
3. Under **Build**:
   - Railway should auto-detect the `railway.toml` and use the Dockerfile
   - If it says "Nixpacks", click the dropdown and select **Dockerfile**

---

## Step 3: Set Environment Variables

1. Click the **Variables** tab
2. Add each of these (copy values from your local `.env`):

| Variable | Description |
|---|---|
| `ENVIRONMENT` | Set to `production` |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key |
| `SUPABASE_ANON_KEY` | Supabase anon/public key |
| `SUPABASE_JWT_SECRET` | Supabase JWT secret |
| `API_KEY_ENCRYPTION_KEY` | 32-byte base64-encoded AES key |
| `CORS_ORIGINS` | Comma-separated allowed origins (e.g., `https://kinetic.app,https://www.kinetic.app`) |
| `ADMIN_PORTAL_URL` | Your frontend URL (e.g., `https://kinetic.app`) |

**Do NOT set** `LOCAL_DEV_AUTH_BYPASS` — it defaults to `False`.

**Do NOT set** `PORT` — Railway injects this automatically.

---

## Step 4: Deploy

1. Click **Deploy** (or push to your deploy branch if auto-deploy is on)
2. Watch the build logs — the Docker build takes 3-5 minutes on first deploy (installs system deps for `unstructured`)
3. Once deployed, Railway shows a green checkmark

---

## Step 5: Verify

1. Railway assigns a URL like `https://kinetic-api-production-XXXX.up.railway.app`
2. Open that URL + `/health` in your browser:
   ```
   https://kinetic-api-production-XXXX.up.railway.app/health
   ```
3. You should see:
   ```json
   {"status": "ok"}
   ```
4. Open `/docs` to see the Swagger UI:
   ```
   https://kinetic-api-production-XXXX.up.railway.app/docs
   ```

---

## Step 6: Custom Domain (Optional)

1. In Railway, go to **Settings > Networking > Custom Domain**
2. Add your domain (e.g., `api.kinetic.app`)
3. Railway gives you a CNAME record — add it in your DNS provider
4. Update `CORS_ORIGINS` and `ADMIN_PORTAL_URL` to include the new domain

---

## Troubleshooting

**Build fails on `unstructured[all-docs]`:**
The Dockerfile installs system deps (poppler, tesseract, libreoffice). If Railway's build times out, try increasing the build timeout in Settings, or temporarily remove `unstructured[all-docs]` from `requirements.txt` to get a minimal deploy running first.

**App crashes on startup with "Missing required environment variables":**
Check the Variables tab — you're missing one of the required env vars listed in Step 3.

**"Production configuration issue: CORS_ORIGINS contains localhost":**
You set `ENVIRONMENT=production` but left localhost in `CORS_ORIGINS`. Update it to your real domain.

**Health check fails:**
The `railway.toml` configures `/health` with a 300s timeout. If the app takes longer to start, increase `healthcheckTimeout` in `railway.toml`.
