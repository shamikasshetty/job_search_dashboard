# Shamika · Job Search Dashboard

Live at: `https://YOUR-GITHUB-USERNAME.github.io/job-search-dashboard`

## Files
- `index.html` — the dashboard app
- `jobs.json` — job data (updated daily by Apify automation)
- `transform.py` — converts Apify raw data to dashboard format
- `.github/workflows/update-jobs.yml` — GitHub Action that runs daily at 7am CST

---

## Deploy in 10 minutes

### 1. Create the repository
1. Go to github.com → sign in → click **New repository**
2. Name: `job-search-dashboard`
3. Set to **Public** (required for free GitHub Pages)
4. Check **Add a README**
5. Click **Create repository**

### 2. Upload the files
1. In your new repo, click **Add file → Upload files**
2. Upload: `index.html`, `jobs.json`, `transform.py`
3. Create folder `.github/workflows/` and upload `update-jobs.yml` into it
4. Click **Commit changes**

### 3. Enable GitHub Pages
1. Go to **Settings** (top of repo)
2. Click **Pages** in the left sidebar
3. Under Source: select **Deploy from a branch**
4. Branch: **main** / Folder: **/ (root)**
5. Click **Save**
6. Wait ~2 minutes — your URL will appear at the top of the Pages settings

### 4. Add your Apify API secrets
1. In your repo, go to **Settings → Secrets and variables → Actions**
2. Click **New repository secret**
3. Add: `APIFY_API_TOKEN` = your Apify API token (from console.apify.com → Settings → Integrations)
4. Add: `APIFY_DATASET_ID` = the dataset ID from your scraper actor run

### 5. Test the GitHub Action manually
1. Go to **Actions** tab in your repo
2. Click **Update Jobs Feed**
3. Click **Run workflow → Run workflow**
4. Watch it run — if green, your jobs.json will update automatically every weekday at 7am CST

---

## Daily workflow (once live)
- Apify runs at 7am → pushes to dataset
- GitHub Action fetches dataset → transforms → commits jobs.json
- Your dashboard at github.io refreshes automatically
- Open dashboard → review top matches → apply via Cowork

## Manual update
To manually add/edit jobs: edit `jobs.json` directly in GitHub and commit.
The dashboard reads it on every page load.
