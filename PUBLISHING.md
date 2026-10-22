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

- **Source:** **GitHub Actions**.

The workflow **Build and publish** (step 6) builds the site and hands it to Pages. The address is
shown on the same settings page, e.g. `https://OWNER.github.io/Weather-Days/`.

(Before October 2026 this repository used "Deploy from a branch". That no longer works, because
the data and reports are not stored in the branch any more.)

**Visibility note.**
- On a free personal account, GitHub Pages works only for **public** repositories.
- Private repositories can publish Pages only on paid plans (Pro, Team, Enterprise), so check
  ONC's plan.
- Either way, the published site itself can be opened by anyone who has the address. The
  `noindex` line in `index.html` asks search engines not to list it, but it is not access control.

## 6. The weekly build ("Build and publish")

The workflow `.github/workflows/update-data.yml` runs every Monday, after every push to `main`, and
whenever you start it by hand. It:
1. downloads fresh buoy data;
2. builds the dashboard data and the PDF reports;
3. publishes the result to GitHub Pages.

It does **not** commit anything back to the repository, so it needs no write permission.

- **Run it by hand:** **Actions** tab (top row of the repository page, not Settings) → **Build and
  publish** in the left list → **Run workflow** → **Run workflow**.
- **Success:** both jobs (*build*, *deploy*) get green ticks. The site updates when *deploy*
  finishes, about 2–3 minutes in total.
- **Failure:** nothing is published, and the previous site stays online. GitHub emails you. Open
  the failed run to see which step failed. A data-server outage usually clears up by the next run.
- **Inactivity:** GitHub may pause scheduled workflows in a repository that has had no activity for
  60 days. If that happens, re-enable it from the Actions tab.

## 7. Updating the site (the routine)

Start with `git pull`. It brings in any commits made on GitHub, for example edits made in the
browser. The weekly build no longer commits, but pulling first is a good habit.

```
cd /Users/smihaly/Analysis/Claude/wave_dashboard
git pull                                    # bring in any commits from GitHub
# ... make the changes ...
git status                                  # which files changed
git diff                                    # optional: the changed lines (q to quit)
git add -A                                  # stage all changes (or name files: git add stations.json)
git commit -m "Short description"           # save a snapshot locally
git push                                    # upload to GitHub
```

Each push starts **Build and publish**; the site updates 2–3 minutes later. To check your change
locally first, run `python scripts/build_site.py` and open `index.html`.

### Useful extras

| Situation | Command | What it does |
|---|---|---|
| See the history | `git log --oneline` | One line per commit, newest first (q to quit) |
| See what one commit changed | `git show <commit-id> --stat` | The files that commit changed |
| Throw away an uncommitted edit | `git restore <file>` | Puts the file back as it was at the last commit. This can't be undone. |
| Unstage a file added by mistake | `git restore --staged <file>` | Takes it out of the next commit; the edit itself stays |
| Behind or ahead of GitHub? | `git status` (first line) | E.g. "Your branch is behind 'origin/main' by 1 commit" |
| Refresh the live site now | Actions → Build and publish → Run workflow | Fresh data and reports, no commit needed |
| Build locally to preview | `python scripts/build_site.py` | Data, reports and `_site/`; then open `index.html` |

### If `git push` is refused

A message like *"Updates were rejected because the remote contains work that you do not have
locally"* means GitHub has a commit you haven't pulled. Run:

```
git pull
git push
```

If `git pull` opens an editor with a message such as "Merge branch 'main'", save and close it. In
the default editor (vim), type `:wq` and press Enter.

### When your token expires

`git push` asks for a username and password again. Create a new fine-grained token as before
(Weather-Days only; Contents and Workflows read and write), enter `sfmihaly` as the username and
paste the token as the password. The macOS keychain saves it again.

## 8. Moving to ONC later

**Moving a repository from your account to the ONC organisation:** Settings → General → Danger Zone
→ **Transfer ownership**. The history moves with it. The Pages address changes to
`https://ONC-ORG.github.io/Weather-Days/`, so share the new link. Afterwards, update this
folder's link with:

```
git remote set-url origin https://github.com/ONC-ORG/Weather-Days.git
```

## Still to decide (ONC)

- **Code licence:** add a `LICENSE` file once ONC has chosen one.
- **Search engines:** whether the page should be searchable. If so, remove the `noindex` line
  in `index.html`.
- **Branding:** any ONC branding or logo.
