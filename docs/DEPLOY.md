# Deploying CourtroomAI

The live demo must stay up, free to use, until judging ends (15 Dec 2026).

| Part | Host | Why |
|---|---|---|
| API (FastAPI, retrieval models, Chroma) | **Railway**, Docker, with a 1 GB volume at `/data` | Needs about 2.5 GB RAM, which rules out free tiers. Railway bills only for what is used, roughly $40–50 up to 15 Dec |
| Website (React) | **Vercel** (free) | Static site plus a CDN |
| Models | Nebius Token Factory (already in use) | Nothing to host |
| Data archive (225 MB) | GitHub Release asset on the public repo | Keeps data out of git; the API downloads it once into the volume |

Hugging Face Spaces was ruled out because free Spaces go to sleep and the build is too heavy. A Nebius Serverless Endpoint would also work, but it is in public preview and costs about the same, so it is only worth adding as an extra.

## 1. Public GitHub repo

1. Create an **empty** public repo on github.com, with no README and no licence, because both already exist here.
2. Push:
   ```bash
   git remote add origin https://github.com/<you>/courtroomai.git
   git push -u origin main
   ```
3. In the repo's About section (gear icon), add the description and the demo link. Check that it shows "MIT license".
4. **Releases → Draft a new release**, tag `data-v1`. Attach `dist/courtroomai-data.tgz`, made by `sh scripts/pack_data.sh`, then publish. Copy the asset's download URL.

## 2. API on Railway

1. railway.com, then **New Project → Deploy from GitHub repo**, and pick the repo. Railway reads `railway.toml` and builds the `Dockerfile`.
2. On the service, open **Settings → Volumes → Add volume** and set the mount path to `/data`.
3. Under **Variables**, add these. Paste the values yourself; never put them in git.
   - `TOKEN_FACTORY_API_KEY`, `TOKEN_FACTORY_BASE_URL`
   - `NEMOTRON_NANO_MODEL`, `NEMOTRON_SUPER_MODEL`, `NEMOTRON_ULTRA_MODEL`
   - `TAVILY_API_KEY`
   - `DATA_URL`: the release asset URL from step 1.4.
   - Optional guards: `DAILY_TOKEN_CAP`, `RATE_LIMIT_PER_MIN`
4. **Settings → Networking → Generate domain**. On the first start, the API downloads the data into the volume, which takes about a minute. After that, `/api/health` shows `ok`.

## 3. Website on Vercel

1. vercel.com, then **Add New → Project**, and import the repo.
2. Set **Root directory** to `frontend`. Vercel detects the framework as Vite.
3. Add the environment variable `VITE_API_URL` = the Railway domain from step 2.4, with `https://` and no trailing slash. Then deploy.

## 4. Check it

```bash
.venv/bin/python scripts/smoke_test.py --api https://<railway-domain> --web https://<vercel-domain> --full
```

Then put both links in the README and on Devpost.

## Keeping it up until 15 Dec

- Keep a balance on Token Factory and Tavily. The daily token cap (`DAILY_TOKEN_CAP`) stops one visitor from draining it.
- Railway: set a usage limit under **Account → Usage** so a spike cannot run up a bill.
- Every push to `main` redeploys both hosts. Do not push during judging unless it is a fix.

## Test the image locally first

```bash
docker build --platform linux/amd64 -t courtroomai-backend:local .
docker run --rm -p 8001:8000 --env-file .env -v "$PWD/data:/data" courtroomai-backend:local
.venv/bin/python scripts/smoke_test.py --api http://localhost:8001
```
