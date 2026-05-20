# Deploy Kinetic Frontend to Vercel

Step-by-step guide for deploying `packages/web/` (Next.js) to Vercel.

---

## Prerequisites

- Vercel account at [vercel.com](https://vercel.com)
- GitHub repo with `packages/web/` containing the Next.js app
- Railway backend already deployed (need the URL for `NEXT_PUBLIC_API_BASE_URL`)
- Supabase project URL and anon key

---

## Step 1: Import the Repo

1. Go to **vercel.com/dashboard**
2. Click **"Add New" → "Project"**
3. Select the **kinetic** GitHub repo
4. **Root Directory**: set to `packages/web`
5. **Framework Preset**: confirm it says **Next.js** (if not, change it in Settings after import)
6. Click **Deploy**

> If the Framework Preset can't be set during import, change it after in **Settings → General → Build & Development Settings**.

---

## Step 2: Set Environment Variables

1. Go to **Settings → Environment Variables**
2. Add each of these:

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Your Supabase project URL (e.g., `https://xxxx.supabase.co`) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon/public key |
| `NEXT_PUBLIC_API_BASE_URL` | Railway backend URL (e.g., `https://kinetic-production-b568.up.railway.app`) |
| `NEXT_PUBLIC_ALLOW_REMOTE_API` | `true` |

**Do NOT set** `NODE_ENV` — Vercel sets this automatically.

---

## Step 3: Verify Build

1. After setting env vars, trigger a redeploy: **Deployments → three-dot menu on latest → Redeploy**
2. Watch the build log — `next build` should complete without errors
3. Vercel assigns a URL like `https://<project>.vercel.app`
4. Open it — the login page should render

---

## Step 4: Update Supabase Auth Redirect URLs

1. Go to **Supabase Dashboard → Authentication → URL Configuration**
2. Add the Vercel URL to **Redirect URLs**: `https://<project>.vercel.app/**`
3. Update **Site URL** to the Vercel URL if this is the production frontend

---

## Step 5: Verify Google OAuth

1. Open the Vercel URL in a browser
2. Click **"Sign in with Google"**
3. Complete the Google consent flow
4. Confirm you're redirected back to the Vercel URL (not localhost)
5. Confirm you land on the authenticated dashboard

---

## Step 6: Update Railway CORS

After the frontend is live, update the Railway backend to accept requests from it:

1. Go to **railway.app** → Kinetic API service → **Variables**
2. Set `CORS_ORIGINS` to include the Vercel URL (e.g., `https://kinetic-ashy-beta.vercel.app`)
3. Set `ADMIN_PORTAL_URL` to the Vercel URL
4. Railway auto-redeploys on variable change

**Verify:** Open browser dev tools → Network tab, load the Vercel app, and log in. No CORS errors on API calls = working.

---

## Redeploying

Vercel auto-deploys on push to the default branch. To manually redeploy:

1. Go to **Deployments** tab
2. Click the three-dot menu on the latest deployment
3. Click **Redeploy**

To deploy a different branch: **Settings → Git → Production Branch**.

---

## Custom Domain (Optional)

1. Go to **Settings → Domains**
2. Add your domain (e.g., `app.kinetic.app`)
3. Vercel gives you DNS records — add them in your DNS provider
4. Update Railway `CORS_ORIGINS` and `ADMIN_PORTAL_URL` to include the new domain
5. Update Supabase Redirect URLs to include the new domain

---

## Troubleshooting

**Build fails with "No Output Directory named public found":**
Framework Preset is wrong. Go to **Settings → General → Build & Development Settings** and set Framework Preset to **Next.js**.

**Google OAuth redirects to localhost:**
Supabase Site URL is still set to `localhost:3000`. Update it in **Supabase Dashboard → Authentication → URL Configuration**.

**API calls fail silently (CORS errors in console):**
Railway `CORS_ORIGINS` doesn't include the Vercel URL. Update it in Railway Variables — must match exactly including `https://`.

**Build fails on missing env vars:**
Check that all four env vars from Step 2 are set. Redeploy after adding them.
