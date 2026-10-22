# Publishing the dashboard on GitHub

A step-by-step guide for putting this folder on GitHub and turning on GitHub Pages, so the dashboard
is available at a web address. Steps 1–2 are done once. Steps 3–5 are done once per repository.

## 1. GitHub account (once)

1. Sign up at <https://github.com>. Use your work email, or add it to the account later.
2. Turn on two-factor authentication: Settings → Password and authentication. Many organisations
   require it before they will add you.
3. Use the same email address that git uses for your commits:
   `git config --global user.email`.

## 2. Let your Mac push to GitHub (once)

GitHub does not accept your account password for `git push`. The simplest options are:

- **GitHub Desktop** (<https://desktop.github.com>). Sign in once; it then handles authentication,
  and you can commit and push with buttons. Good while learning.
- **GitHub CLI**. Install the macOS package from <https://cli.github.com>, then run
  `gh auth login` in Terminal once, choosing GitHub.com → HTTPS → log in with a web browser. After
  that, ordinary `git push` works.

## 3. Create an empty repository on GitHub

On GitHub: **+** (top right) → **New repository**.

- **Owner:** your account (to practise) or the ONC organisation (once you are a member with
  permission to create repositories). A repository can be moved later (step 7).
- **Name:** e.g. `wave-weather-days`.
- **Visibility:** see the note on GitHub Pages below.
- **Do not** tick "Add a README", ".gitignore" or "licence". This folder already has its own
  history, and an initialised repository would conflict with it.

## 4. Connect this folder and push

In Terminal, replacing `OWNER` with your GitHub username or the organisation name:

```
cd /Users/smihaly/Analysis/Claude/wave_dashboard
git remote add origin https://github.com/OWNER/wave-weather-days.git
git push -u origin main
```

Refresh the repository page on GitHub. The files and the commit history should be there.

## 5. Turn on GitHub Pages

Repository → **Settings** → **Pages** → Build and deployment:

- **Source:** Deploy from a branch.
- **Branch:** `main`, folder `/ (root)` → **Save**.

After a minute or two the page shows the address, e.g.
`https://OWNER.github.io/wave-weather-days/`.

**Visibility note.**
- On a free personal account, GitHub Pages works only for **public** repositories.
- Private repositories can publish Pages only on paid plans (Pro, Team, Enterprise), so check
  ONC's plan.
- Either way, the published site itself can be opened by anyone who has the address. The
  `noindex` line in `index.html` asks search engines not to list it, but it is not access control.

## 6. Turn on the weekly data update

The workflow `.github/workflows/update-data.yml` refreshes the buoy data every Monday and commits it.

1. Repository → **Settings** → **Actions** → **General** → Workflow permissions → **Read and write
   permissions** → Save. In an organisation this may be set, or locked, by an administrator.
2. Test it: **Actions** tab → **Update buoy data** → **Run workflow**. A green tick and a new
   "Update buoy data" commit mean it works. The published page updates a minute or two later.
3. GitHub may pause scheduled workflows in a repository that has had no activity for 60 days. If
   that happens, re-enable it from the Actions tab.

## 7. Day-to-day, and moving to ONC later

After changing anything (or after I change something):

```
git status
git add -A
git commit -m "Short description of the change"
git push
```

GitHub Pages republishes automatically after each push.

**Moving a repository from your account to the ONC organisation:** Settings → General → Danger Zone
→ **Transfer ownership**. The history moves with it. The Pages address changes to
`https://ONC-ORG.github.io/wave-weather-days/`, so share the new link. Afterwards, update this
folder's link with:

```
git remote set-url origin https://github.com/ONC-ORG/wave-weather-days.git
```

## Still to decide (ONC)

- **Code licence:** add a `LICENSE` file once ONC has chosen one.
- **Search engines:** whether the page should be searchable. If so, remove the `noindex` line
  in `index.html`.
- **Branding:** any ONC branding or logo.
