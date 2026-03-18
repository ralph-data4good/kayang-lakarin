# Deploy: Kayang Lakarin?

~15 minutes. One checkbox per action. Take a break between sections if you need to.

---

## Prerequisites

Skip any you already have.

- [ ] **Git** — [git-scm.com/downloads](https://git-scm.com/downloads)
- [ ] **Python 3.9+** — [python.org/downloads](https://python.org/downloads) (check "Add to PATH" during install)
- [ ] **GitHub account** — [github.com/signup](https://github.com/signup)

Verify in terminal:
```
git --version
python --version
```
Both should print a version number.

---

## 1. Test locally

- [ ] Unzip `lakad-mnl.zip` somewhere you'll find it
- [ ] Open terminal, cd into the folder:
```
cd path/to/lakad-mnl
```
- [ ] Install dependencies:
```
pip install -r requirements.txt
```
- [ ] Run:
```
streamlit run app.py
```
- [ ] Browser opens at `localhost:8501`. Check: map loads, cards appear, sidebar filters work, click-to-pin works.

`Ctrl+C` to stop when done.

---

## 2. Create GitHub repo

- [ ] Go to [github.com/new](https://github.com/new)
- [ ] Name: `kayang-lakarin`
- [ ] Public
- [ ] Do NOT check "Add a README" (we have one)
- [ ] Create repository
- [ ] Leave the page open — you need the URL

---

## 3. Push code

In terminal, inside your `lakad-mnl` folder. One line at a time:

```
git init
```
```
git add .
```
```
git commit -m "Kayang Lakarin v5.0"
```
```
git branch -M main
```
```
git remote add origin https://github.com/YOUR_USERNAME/kayang-lakarin.git
```
Replace `YOUR_USERNAME` with your GitHub username.

```
git push -u origin main
```

If it asks for a password and you have 2FA, you need a personal access token instead: [create one here](https://github.com/settings/tokens/new) (check `repo` scope).

Refresh your GitHub repo page. All 7 files should be there.

---

## 4. Deploy on Streamlit Cloud

- [ ] Go to [share.streamlit.io](https://share.streamlit.io)
- [ ] Sign in with GitHub
- [ ] Click **New app**
- [ ] Fill in:
  - Repository: `YOUR_USERNAME/kayang-lakarin`
  - Branch: `main`
  - Main file: `app.py`
- [ ] Click **Deploy**

Takes 2–3 minutes. Go stretch.

You'll get a URL like `https://kayang-lakarin-xxxxx.streamlit.app`. That's your live app.

---

## 5. Set a clean URL (optional)

- [ ] Streamlit Cloud → your app → Settings (gear icon) → General → Custom subdomain
- [ ] Type: `kayang-lakarin`
- [ ] Save

App is now at `https://kayang-lakarin.streamlit.app`

---

## Updating

Push to main. Streamlit auto-redeploys in ~30 seconds.

```
git add .
git commit -m "what changed"
git push
```

---

## Community submissions

The app has a built-in submission form. Users fill it out, and submissions save to `submissions.json`.

### The filesystem problem

Streamlit Cloud's disk resets on every redeploy. Three options for persistence:

**A. Google Sheets (recommended)**

Zero infrastructure. Create a sheet, connect via service account, write rows from the form.

1. Make a Google Sheet with columns: `name, lat, lng, city, type, area_ha, activities, air_quality_user, aq_reason, evidence_url, notes, email, submitted_at, status`
2. Create a GCP service account, share the sheet with it
3. Add `gspread` and `oauth2client` to `requirements.txt`
4. Replace the JSON write block in `app.py` with:
```python
import gspread
from oauth2client.service_account import ServiceAccountCredentials
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
client = gspread.authorize(creds)
sheet = client.open("Kayang Lakarin Submissions").sheet1
sheet.append_row([sub_name, sub_lat, sub_lng, ...])
```
5. Put service account JSON in Streamlit Cloud → Settings → Secrets

**B. GitHub Issues (zero code)**

Change the success message to show a pre-filled GitHub Issue link. Review submissions as Issues.

**C. Local only (development)**

Works on your machine. Run `python review_submissions.py` to approve/reject. Approved entries merge into `outdoor_areas_data.json`. Commit and push.

---

## Reviewing submissions locally

```
python review_submissions.py
```

Shows each pending submission with a Google Maps link and algorithmic AQ score. You approve, reject, or skip. Approved entries go into the dataset with the computed AQ (not the user's self-assessment). Then:

```
git add .
git commit -m "Add community submissions"
git push
```

---

## Files

| File | What | Touch often? |
|------|------|-------------|
| `app.py` | Streamlit app (651 lines) | When adding features |
| `outdoor_areas_data.json` | 97 areas — the dataset | When approving submissions |
| `generate_data.py` | Rebuilds dataset with AQ scoring | If changing raw data |
| `review_submissions.py` | CLI to approve/reject submissions | Just run it |
| `submissions.json` | Pending submissions (runtime) | Auto-managed |
| `requirements.txt` | Python deps | When adding libraries |
| `README.md` | GitHub docs | Whenever |
| `DEPLOY.md` | This file | Once |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `pip install` fails | Try `pip install -r requirements.txt --break-system-packages` or use a venv: `python -m venv venv && source venv/bin/activate` |
| `streamlit: command not found` | `python -m streamlit run app.py` |
| Map blank | Try a different browser or disable ad blockers |
| OSRM spinner hangs | Toggle "Road-based routing" off in sidebar — falls back to distance estimates |
| Datatype font not loading | It loads from GitHub raw. Falls back to Outfit. Cosmetic only |
| `git push` password fails | Need a personal access token with `repo` scope, not your password |
| Streamlit build fails | Check build logs — usually a typo in `requirements.txt` |
| Submissions vanish after deploy | Streamlit Cloud disk is ephemeral — use Google Sheets (Option A) |
| Want to add parks manually | Edit `generate_data.py` → add to `RAW_AREAS` → run `python generate_data.py` → push |

---

## Next steps if you want to go further

- **Real-time AQI** — Swap static scores for [IQAir API](https://www.iqair.com/commercial/air-quality-monitors/air-quality-api) calls
- **Self-hosted OSRM** — Docker instructions in `README.md`, uses Philippines OSM extract
- **PWA wrapper** — Streamlit is mobile-responsive out of the box; wrap the URL for home screen install
- **Accept PRs** — Let contributors submit changes to `outdoor_areas_data.json` directly via GitHub pull requests
